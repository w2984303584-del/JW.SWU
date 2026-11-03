import json
from types import SimpleNamespace

import pytest

from BrowserSession import Response

FIELDS = {'firstXkkzId': 'batch', 'firstKklxdm': '10', 'xkxnm': '2026',
          'xkxqm': '3', 'jg_id_1': 'faculty', 'rlzlkz': '1', 'xklc': '1'}
COURSE = {'kch_id': 'C2', 'kcmc': '课程二', 'kch': 'CODE2', 'xf': '2',
          'cxbj': '0', 'fxbj': '0', 'xxkbj': '0', 'jxbzls': '1', 'kklxdm': '10'}
GROUP = {'do_jxb_id': 'G2', 'jsxm': '示例教师', 'sksj': '周二', 'jxdd': '模拟教室'}


class Frame:
    def __init__(self, fields=None, url='https://jw.swu.edu.cn/jwglxt/xsxk/index.html?gnmkdm=N42&su=sample'):
        self.url = url
        self.fields = dict(FIELDS if fields is None else fields)
        self.html = ''

    def content(self):
        return self.html + ''.join(f'<input name="{k}" value="{v}">' for k, v in self.fields.items())

    def evaluate(self, _script, *_args):
        if 'document.body' in _script:
            return getattr(self, 'visible_text', '')
        return self.fields.copy()


class Session:
    def __init__(self, replies=(), fields=None):
        self.frame = Frame(fields)
        self.replies = list(replies)
        self.calls = []
        self.closed = False

    def post(self, url, data=None):
        self.calls.append((url, data))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Response(reply if isinstance(reply, str) else json.dumps(reply), 200)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True


@pytest.fixture
def sample():
    return SimpleNamespace(fields=FIELDS.copy(), course=COURSE.copy(), group=GROUP.copy())
