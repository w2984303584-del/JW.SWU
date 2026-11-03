import json
from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest

import Course_Selection as course
import Login as login
from BrowserSession import AuthenticationRequired, BrowserSession, PortalError, Response, SubmissionUnknown
from conftest import Frame, Session


@pytest.mark.parametrize('available', [True, False])
def test_browser_preflight(available, monkeypatch):
    import playwright.sync_api as api
    from BrowserSession import browser_available
    def launch(**_):
        if not available:
            raise RuntimeError('missing browser')
        return NS(close=lambda: None)
    @contextmanager
    def fake():
        yield NS(chromium=NS(launch=launch))
    monkeypatch.setattr(api, 'sync_playwright', fake)
    assert browser_available() is available


def test_flexible_html_and_live_values():
    parsed = login.Inputs("<input value='x&amp;y' id='a'><input type='password' name='password' value='secret'><select name='k'><option selected value='2'>B</option></select>")
    assert parsed.values == {'a': 'x&y', 'k': '2'}
    assert parsed.has_password
    frame = Frame({'xkxqm': '12'})
    frame.html = '<input name="xkxqm" value="3">'
    assert login.read_fields(frame).values['xkxqm'] == '12'


@pytest.mark.parametrize('url,good', [
    ('https://jw.swu.edu.cn/jwglxt/xsxk/index.html', True),
    ('https://jw.swu.edu.cn.attacker.invalid/jwglxt/xsxk/index.html', False),
    ('https://uaaap.swu.edu.cn/cas/login', False),
    ('https://jw.swu.edu.cn/jwglxt/index.html', False),
])
def test_frame_discovery(url, good):
    f = Frame(url=url)
    context = NS(pages=[NS(frames=[f], wait_for_timeout=lambda _: None)])
    assert bool(login.course_frames(context)) is good
    f.html = '<input type="password">'
    assert login.course_frames(context) == []


def test_get_info():
    assert login.GetInfo(Session()) == {'authenticated_course_page': True}


def test_legacy_password_not_accepted():
    with pytest.raises(PortalError, match='浏览器'):
        login.Login('sample', 'do-not-save')


@pytest.mark.parametrize('response', ['html', '<html>challenge</html>', ''])
def test_response_json_error(response):
    with pytest.raises(PortalError, match='JSON'):
        Response(response, 200).json()


def transport(result=None, error=None):
    calls = []
    def evaluate(script, args):
        calls.append(args)
        if error:
            raise error
        return result or {'url': 'https://jw.swu.edu.cn/api', 'status': 200, 'text': '{"ok":true}'}
    f = Frame()
    f.evaluate = evaluate
    return BrowserSession(f), calls


def test_browser_transport_and_form_encoding():
    session, calls = transport()
    assert session.post('/api', {'jxb_ids': 'a,b', 'kcmc': '中文+课'}).json()['ok']
    assert calls[0]['body'] == 'jxb_ids=a%2Cb&kcmc=%E4%B8%AD%E6%96%87%2B%E8%AF%BE'
    assert session.get('/api').status_code == 200


@pytest.mark.parametrize('url', ['https://evil.invalid/api', '//evil.invalid/api', 'javascript:alert(1)'])
def test_cross_origin_is_not_sent(url):
    session, calls = transport()
    with pytest.raises(PortalError):
        session.post(url)
    assert not calls


@pytest.mark.parametrize('result', [
    {'url': 'https://uaaap.swu.edu.cn/cas/login', 'status': 200, 'text': ''},
    {'url': 'https://jw.swu.edu.cn/cas/login', 'status': 200, 'text': ''},
    {'url': 'https://jw.swu.edu.cn/api', 'status': 200, 'text': '<html><input type="password"></html>'},
    {'url': 'https://jw.swu.edu.cn/api', 'status': 401, 'text': ''},
    {'url': 'https://jw.swu.edu.cn/api', 'status': 403, 'text': ''},
    {'url': 'https://jw.swu.edu.cn/api', 'status': 200, 'text': '<html><script>document.cookie="test"</script></html>'},
])
def test_authentication_expiry(result):
    session, calls = transport(result)
    with pytest.raises(AuthenticationRequired):
        session.get('/api')
    assert len(calls) == 1


def test_frame_navigated_away():
    session, calls = transport()
    session.frame.url = 'https://uaaap.swu.edu.cn/cas/login'
    with pytest.raises(AuthenticationRequired):
        session.get('/api')
    assert not calls


@pytest.mark.parametrize('method,error_type', [('post', SubmissionUnknown), ('get', PortalError)])
def test_timeout_never_retries(method, error_type):
    session, calls = transport(error=TimeoutError())
    with pytest.raises(error_type):
        getattr(session, method)('/api')
    assert len(calls) == 1


@pytest.mark.parametrize('method,error_type', [('post', SubmissionUnknown), ('get', PortalError)])
def test_http_error(method, error_type):
    session, calls = transport({'url': 'https://jw.swu.edu.cn/api', 'status': 502, 'text': ''})
    with pytest.raises(error_type, match='502'):
        getattr(session, method)('/api')
    assert len(calls) == 1


def test_context_closes_once_even_on_error():
    counts = []
    session = BrowserSession(Frame(), NS(close=lambda: counts.append('context')), NS(stop=lambda: counts.append('pw')))
    with pytest.raises(ValueError):
        with session:
            raise ValueError()
    session.close()
    assert counts == ['context', 'pw']


def test_missing_batch():
    with pytest.raises(PortalError, match='批次'):
        course.CS(Session(fields={}))


def test_missing_fields_can_load_display(sample):
    fields = {'firstXkkzId': 'batch'}
    html = ''.join(f'<input value="{v}" name="{k}">' for k, v in sample.fields.items())
    s = Session([html], fields)
    cs = course.CS(s)
    assert cs.params['xkxnm'] == '2026'
    assert len(s.calls) == 1


def test_missing_display_fields_reports_names():
    with pytest.raises(PortalError, match='xkxnm'):
        course.CS(Session(['<html>not selection time</html>'], {'firstXkkzId': 'batch'}))


def test_selected_category_dynamic_module_csrf(sample):
    sample.fields.update(kklxdm='99', xkkz_id='current-batch', csrf_token='sample-token')
    cs = course.CS(Session(fields=sample.fields), 'sample student')
    assert cs.common()['kklxdm'] == '99'
    assert cs.common()['xkkz_id'] == 'current-batch'
    assert cs.common()['csrf_token'] == 'sample-token'
    assert 'gnmkdm=N42' in cs.url('list') and 'su=sample+student' in cs.url('list')


def test_full_page_followed_by_empty(sample, monkeypatch):
    monkeypatch.setattr(course.time, 'sleep', lambda _: None)
    rows = [dict(sample.course, kch_id=f'C{i}') for i in range(10)]
    s = Session([{'tmpList': rows}, {'tmpList': []}])
    assert len(course.CS(s).GetCourses()) == 10
    assert s.calls[1][1]['kspage'] == 11


def test_course_keyword_filter(sample):
    s = Session([{'tmpList': [sample.course, dict(sample.course, kcmc='其他课程', kch_id='C3')]}])
    assert course.CS(s).GetCourses('课程二') == [sample.course]


@pytest.mark.parametrize('body', [[], {}, {'tmpList': {}}, {'tmpList': [{}]}, {'tmpList': ['bad']}])
def test_bad_course_schema(body):
    with pytest.raises(PortalError):
        course.CS(Session([body])).GetCourses()


def test_repeated_page_stops(sample, monkeypatch):
    monkeypatch.setattr(course.time, 'sleep', lambda _: None)
    rows = [dict(sample.course, kch_id=f'C{i}') for i in range(10)]
    s = Session([{'tmpList': rows}] * 2)
    with pytest.raises(PortalError, match='重复'):
        course.CS(s).GetCourses()
    assert len(s.calls) == 2


def test_page_limit(sample, monkeypatch):
    monkeypatch.setattr(course.time, 'sleep', lambda _: None)
    s = Session([{'tmpList': [dict(sample.course, kch_id=str(i)) for i in range(10)]}])
    with pytest.raises(PortalError, match='上限'):
        course.CS(s).GetCourses(max_pages=1)
    with pytest.raises(ValueError):
        course.CS(Session()).GetCourses(max_pages=0)


@pytest.mark.parametrize('body', [[], {}, [{}], ['bad']])
def test_bad_group_schema(sample, body):
    with pytest.raises(PortalError):
        course.CS(Session([body])).groups(sample.course)


def test_groups_preserved(sample):
    groups = [sample.group, dict(sample.group, do_jxb_id='G3')]
    assert course.CS(Session([groups])).groups(sample.course) == groups


def test_unconfirmed_never_submits(sample):
    s = Session()
    with pytest.raises(PortalError, match='确认'):
        course.CS(s).SelectCourse(sample.course, sample.group)
    assert not s.calls


@pytest.mark.parametrize('flag,ok', [('1', True), (1, True), ('-1', False), ('0', False), ('new', False)])
def test_selection_flags(sample, flag, ok):
    s = Session([{'flag': flag}])
    cs = course.CS(s)
    if ok:
        assert cs.SelectCourse(sample.course, sample.group, confirmed=True)
    else:
        with pytest.raises(PortalError):
            cs.SelectCourse(sample.course, sample.group, confirmed=True)
    assert len(s.calls) == 1
    assert s.calls[0][1]['jxb_ids'] == 'G2'


@pytest.mark.parametrize('result', [{}, [], 'not json'])
def test_unknown_selection_result_no_retry(sample, result):
    s = Session([result])
    with pytest.raises(PortalError):
        course.CS(s).SelectCourse(sample.course, sample.group, confirmed=True)
    assert len(s.calls) == 1


def test_incomplete_plan_never_submits(sample):
    s = Session()
    with pytest.raises(PortalError):
        course.CS(s).SelectCourse({}, sample.group, confirmed=True)
    assert not s.calls


def test_compound_child_explicit_selection(sample):
    sample.course.update(jxbzls='2', jxb_id='parent')
    child = dict(sample.group, do_jxb_id='CHILD')
    s = Session(['view', [sample.group, child], {'flag': '1'}])
    cs = course.CS(s)
    assert cs.subgroups(sample.course, sample.group) == [child]
    with pytest.raises(PortalError, match='子教学班'):
        cs.prepare(sample.course, sample.group)
    with pytest.raises(PortalError, match='相同'):
        cs.prepare(sample.course, sample.group, sample.group)
    assert cs.SelectCourse(sample.course, sample.group, subgroup=child, confirmed=True)
    assert s.calls[-1][1]['jxb_ids'] == 'G2,CHILD'


@pytest.mark.parametrize('children', [[], {}, ['bad'], [{}]])
def test_bad_subgroup_schema(sample, children):
    sample.course['jxbzls'] = '2'
    with pytest.raises(PortalError):
        course.CS(Session(['view', children])).subgroups(sample.course, sample.group)


def test_regular_course_no_child_query(sample):
    s = Session()
    assert course.CS(s).subgroups(sample.course, sample.group) == []
    assert not s.calls


@pytest.mark.parametrize('answer,expected', [('1', 'a'), ('2', 'b'), ('q', None)])
def test_pick(answer, expected):
    assert course.pick(['a', 'b'], lambda _: answer) == expected


@pytest.mark.parametrize('answer', ['0', '-1', '3', 'bad'])
def test_pick_bad(answer):
    with pytest.raises(PortalError):
        course.pick(['a', 'b'], lambda _: answer)


def test_cli_flow_single_submit(sample, monkeypatch, capsys):
    s = Session([{'tmpList': [sample.course]}, [sample.group], {'flag': '1'}])
    monkeypatch.setattr(course, 'Login', lambda **_: (s, 'sample'))
    answers = iter(['课程二', '确认选课', '', 'q'])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    monkeypatch.setattr(course, 'pick', lambda rows: rows[0])
    assert course.main([]) == 0
    assert s.closed
    assert sum('xkBcZy' in url for url, _ in s.calls) == 1
    assert '服务器返回选课成功' in capsys.readouterr().out


def test_cli_cancel_never_submits(sample, monkeypatch):
    s = Session([{'tmpList': [sample.course]}, [sample.group]])
    monkeypatch.setattr(course, 'Login', lambda **_: (s, 'sample'))
    answers = iter(['课程二', '取消', 'q'])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    monkeypatch.setattr(course, 'pick', lambda rows: rows[0])
    assert course.main([]) == 0
    assert not any('xkBcZy' in url for url, _ in s.calls)


def test_diagnostic_redacts_values(sample, monkeypatch, capsys):
    s = Session(fields=dict(sample.fields, csrf_token='private-token', xh_id='private-id'))
    monkeypatch.setattr(course, 'Login', lambda **_: (s, 'sample'))
    monkeypatch.setattr('builtins.input', lambda _: '')
    assert course.main(['--diagnose']) == 0
    text = capsys.readouterr().out
    assert 'csrf_token' in text and 'private-token' not in text and 'private-id' not in text


@pytest.mark.parametrize('error,exit_code', [(PortalError('test'), 2), (ValueError(), 3), (KeyboardInterrupt(), 130)])
def test_cli_errors_close_session(error, exit_code, monkeypatch):
    s = Session()
    monkeypatch.setattr(course, 'Login', lambda **_: (s, 'sample'))
    def fail(_):
        raise error
    monkeypatch.setattr('builtins.input', fail)
    assert course.main([]) == exit_code
    assert s.closed
