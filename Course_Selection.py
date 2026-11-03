"""Interactive course selection with browser SSO and bounded, explicit submission."""
import argparse
import json
import sys
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from BrowserSession import PortalError, SelectionClosed
from Login import Inputs, Login, read_fields, page_state

TARGETS = []
COMMON = ('rwlx xkly bklx_id xqh_id zyh_id zyfx_id njdm_id bh_id xbm xslbdm ccdm '
          'xsbj sfkknj sfkkzy kzybkxy sfznkx zdkxms sfkxq sfkcfx kkbk kkbkdj '
          'sfkgbcx sfrxtgkcxd tykczgxdcs xkxnm xkxqm rlkz xkzgbj jxbzb').split()


def CheckName(name: str):
    return any(target and target in name for target in TARGETS)


class CS:
    def __init__(self, session, num=''):
        self.session = session
        self.num = num
        self.status = 0
        if page_state(session.frame) == 'selection_closed':
            self.status = -1
            raise SelectionClosed('已登录教务系统，当前选课未开放；没有发送查询或选课提交。')
        self.params = read_fields(session.frame).values
        query = parse_qs(urlsplit(session.frame.url).query)
        self.module = query.get('gnmkdm', ['N253512'])[0]
        p = self.params
        p['firstXkkzId'] = p.get('xkkz_id') or p.get('firstXkkzId', '')
        p['firstKklxdm'] = p.get('kklxdm') or p.get('firstKklxdm', '')
        if not p['firstXkkzId']:
            raise PortalError('未进入选课批次，请在网页打开自主选课和选课类别。')
        if not p.get('xkxnm') or not p.get('xkxqm') or not p.get('firstKklxdm'):
            html = session.post(self.url('zzxkyzb_cxZzxkYzbDisplay.html'), data={
                'xkkz_id': p['firstXkkzId'], 'xszxzt': p.get('xszxzt', ''), 'kspage': 0, 'jspage': 0,
            }).text
            p.update(Inputs(html).values)
            p['firstKklxdm'] = p.get('kklxdm') or p.get('firstKklxdm', '')
        missing = [key for key in ('xkxnm', 'xkxqm', 'firstKklxdm') if not p.get(key)]
        if missing:
            raise PortalError('当前页面缺少选课参数：' + ', '.join(missing) + '。请打开具体选课类别。')

    def url(self, endpoint):
        query = {'gnmkdm': self.module}
        if self.num:
            query['su'] = self.num
        return '/jwglxt/xsxk/' + endpoint + '?' + urlencode(query)

    def common(self):
        p = {k: self.params[k] for k in COMMON if k in self.params}
        p.update(jg_id=self.params.get('jg_id_1', self.params.get('jg_id', '')),
                 kklxdm=self.params['firstKklxdm'], xkkz_id=self.params['firstXkkzId'])
        p.update({k: v for k, v in self.params.items() if 'csrf' in k.lower()})
        return p

    def assert_current_batch(self):
        fields = read_fields(self.session.frame)
        if page_state(self.session.frame, fields) == 'selection_closed':
            raise SelectionClosed('选课未开放或已结束，已停止后续查询和提交。')
        if fields.has_password:
            raise PortalError('登录已过期，请重新打开选课页面。')
        live = fields.values
        batch = live.get('xkkz_id') or live.get('firstXkkzId')
        category = live.get('kklxdm') or live.get('firstKklxdm')
        if not batch or batch != self.params['firstXkkzId'] or (category and category != self.params['firstKklxdm']):
            raise PortalError('浏览器中的选课批次或类别已切换，请重启工具重新读取，尚未提交。')

    def GetCourses(self, condition=None, *, max_pages=100):
        self.assert_current_batch()
        if max_pages < 1:
            raise ValueError('max_pages 必须大于零')
        result, seen = [], set()
        for page in range(max_pages):
            data = self.common()
            data.update(kspage=page * 10 + 1, jspage=(page + 1) * 10)
            body = self.session.post(self.url('zzxkyzb_cxZzxkYzbPartDisplay.html'), data=data).json()
            if not isinstance(body, dict) or not isinstance(body.get('tmpList'), list):
                raise PortalError('课程列表接口结构已变化，请停止并反馈接口结构。')
            rows = body['tmpList']
            if not rows:
                return result
            for item in rows:
                if not isinstance(item, dict) or not item.get('kch_id') or not item.get('kcmc'):
                    raise PortalError('课程数据缺少课程 ID 或名称。')
                identity = (str(item['kch_id']), str(item.get('jxb_id', '')))
                if identity in seen:
                    raise PortalError('课程分页返回重复数据，已停止以避免无限循环。')
                seen.add(identity)
                if not condition or condition in item['kcmc']:
                    result.append(item)
            if len(rows) < 10:
                return result
            time.sleep(0.5)
        raise PortalError('课程分页超过上限，请缩小范围或在网页查询。')

    def groups(self, course):
        self.assert_current_batch()
        data = self.common()
        data.update({k: course[k] for k in ('kch_id', 'cxbj', 'fxbj') if k in course})
        groups = self.session.post(self.url('zzxkyzbjk_cxJxbWithKchZzxkYzb.html'), data=data).json()
        if not isinstance(groups, list) or not groups or any(not isinstance(g, dict) or not g.get('do_jxb_id') for g in groups):
            raise PortalError('没有可选教学班或教学班接口结构已变化。')
        return groups

    def subgroups(self, course, group):
        """Load official child-class choices; never silently pick the first child."""
        self.assert_current_batch()
        if str(course.get('jxbzls')) != '2':
            return []
        data = self.common()
        data.update({k: course.get(k, '') for k in ('jxb_id', 'jxbzls', 'fxbj', 'cxbj')})
        data.update(do_jxb_id=group['do_jxb_id'], jxb_id=course.get('jxb_id', ''),
                    rlzlkz=self.params.get('rlzlkz', ''), syqz='100')
        # The first endpoint initializes the child-class selection view.
        self.session.post(self.url('zzxkyzb_xkZyZzxkYzbZjxb.html'), data=data)
        data.update(jxb_id=group['do_jxb_id'], xh_id=self.num, zh='')
        rows = self.session.post(self.url('zzxkyzb_xkZyDisplayZzxkYzbZjxb.html'), data=data).json()
        if not isinstance(rows, list) or any(not isinstance(g, dict) or not g.get('do_jxb_id') for g in rows):
            raise PortalError('子教学班接口结构已变化，请在网页核对。')
        rows = [g for g in rows if g['do_jxb_id'] != group['do_jxb_id']]
        if not rows:
            raise PortalError('没有可选子教学班，本次尚未提交。')
        return rows

    def prepare(self, course, group, subgroup=None):
        self.assert_current_batch()
        if str(course.get('jxbzls')) == '2' and (not subgroup or not subgroup.get('do_jxb_id')):
            raise PortalError('此课程需要明确选择实践/子教学班，尚未提交。')
        required = ('kch_id', 'kcmc', 'kch', 'xf', 'cxbj', 'xxkbj')
        if any(key not in course for key in required) or not group.get('do_jxb_id'):
            raise PortalError('课程或教学班参数不完整，尚未提交。')
        data = self.common()
        data.update({k: self.params.get(k, '') for k in ('rlzlkz', 'xklc')})
        data.update(jxb_ids=group['do_jxb_id'], kch_id=course['kch_id'],
                    kcmc=f"({course['kch']}){course['kcmc']}+-+{course['xf']}+学分",
                    sxbj='1', xxkbj=course['xxkbj'], qz='0', cxbj=course['cxbj'],
                    kklxdm=course.get('kklxdm', self.params['firstKklxdm']))
        if str(course.get('jxbzls')) == '2':
            if subgroup['do_jxb_id'] == group['do_jxb_id']:
                raise PortalError('子教学班不能与主教学班相同。')
            data['jxb_ids'] += ',' + subgroup['do_jxb_id']
        return data

    def SelectCourse(self, course, group, *, confirmed=False, subgroup=None):
        if not confirmed:
            raise PortalError('尚未确认教学班；没有发送选课提交。')
        data = self.prepare(course, group, subgroup)
        result = self.session.post(self.url('zzxkyzbjk_xkBcZyZzxkYzb.html'), data=data).json()
        if not isinstance(result, dict) or 'flag' not in result:
            raise PortalError('提交返回结构不明；请在网页核对已选课程，切勿直接重试。')
        flag = str(result['flag'])
        if flag == '1':
            return True
        if flag == '-1':
            raise PortalError('该教学班已满员，本次已停止。')
        raise PortalError('学校未接受此次选课，请在网页查看冲突、限制或选课时段提示。')


def pick(items, input_fn=input):
    answer = input_fn('输入序号（q 退出）：').strip()
    if answer.lower() == 'q':
        return None
    try:
        index = int(answer) - 1
        if 0 <= index < len(items):
            return items[index]
    except ValueError:
        pass
    raise PortalError('序号无效；本次没有提交选课。')


def show_groups(groups):
    for index, g in enumerate(groups, 1):
        print(f"{index}. 教师 {g.get('jsxx', g.get('jsxm', '?'))} | 时间 {g.get('sksj', '?')} | 地点 {g.get('jxdd', '?')} | 余量 {g.get('syrs', '?')} | 班号 {g.get('jxbmc', g['do_jxb_id'])}")


def main(argv=None):
    parser = argparse.ArgumentParser(description='西南大学选课助手：浏览器登录、课程查询、逐次确认选课')
    parser.add_argument('--browser', choices=('msedge', 'chrome', 'chromium'), default='msedge')
    parser.add_argument('--profile', help='可选：独立浏览器数据目录；默认临时会话')
    parser.add_argument('--login-only', action='store_true')
    parser.add_argument('--diagnose', action='store_true', help='仅输出参数名和可用性，不输出学号/Cookie/页面内容')
    args = parser.parse_args(argv)
    try:
        session, num = Login(channel=None if args.browser == 'chromium' else args.browser, profile=args.profile,
                             require_selection=not (args.login_only or args.diagnose))
        with session:
            if args.login_only:
                input('已识别教务登录状态；未发送选课请求。按回车关闭浏览器：')
                return 0
            state = page_state(session.frame)
            if args.diagnose:
                fields = read_fields(session.frame).values
                print(json.dumps({'course_page': state in ('selection_ready', 'selection_closed'),
                                  'page_state': state, 'logged_in': state in ('selection_ready', 'selection_closed', 'teaching_home'),
                                  'selection_open': True if state == 'selection_ready' else False if state == 'selection_closed' else None,
                                  'parameter_names': sorted(fields)}, ensure_ascii=False))
                input('诊断完成。按回车关闭浏览器：')
                return 0
            if state == 'selection_closed':
                print('已登录教务系统，当前选课未开放。未发送课程查询或选课提交；开放后重新启动即可。')
                input('按回车关闭浏览器：')
                return 0
            cs = CS(session, num)
            while True:
                keyword = input('输入课程名称关键词（q 退出）：').strip()
                if keyword.lower() == 'q':
                    return 0
                if not keyword:
                    continue
                courses = cs.GetCourses(keyword)
                if not courses:
                    print('当前选课类别未找到匹配课程。')
                    continue
                for index, c in enumerate(courses, 1):
                    print(f"{index}. {c['kcmc']} | 课程代码 {c.get('kch', '')} | {c.get('xf', '?')} 学分")
                course = pick(courses)
                if course is None:
                    return 0
                groups = cs.groups(course)
                show_groups(groups)
                group = pick(groups)
                if group is None:
                    return 0
                children = cs.subgroups(course, group)
                subgroup = None
                if children:
                    print('请选择实践/子教学班：')
                    show_groups(children)
                    subgroup = pick(children)
                    if subgroup is None:
                        return 0
                cs.prepare(course, group, subgroup)
                if input('核对上方课程、教师、时间。输入 确认选课 才提交一次：').strip() != '确认选课':
                    print('已取消，没有提交。')
                    continue
                if cs.SelectCourse(course, group, confirmed=True, subgroup=subgroup):
                    print('服务器返回选课成功。请在浏览器【已选课程】确认课程、教学班及课表。')
                    input('网页核对完成后按回车继续：')
    except KeyboardInterrupt:
        print('\n已退出；若中断发生在提交期间，请在网页核对结果。')
        return 130
    except SelectionClosed as exc:
        print(str(exc))
        return 0
    except PortalError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print('浏览器或页面未准备好。请检查依赖、学校网络及浏览器状态后重启。', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
