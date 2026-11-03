import runpy
from pathlib import Path

import pytest

import Course_Selection as course
from BrowserSession import PortalError
from conftest import Session


@pytest.mark.parametrize('change', [{'xkkz_id': 'another'}, {'kklxdm': 'another'}, {'firstXkkzId': ''}])
def test_page_changed_before_submit(sample, change):
    s = Session()
    cs = course.CS(s)
    s.frame.fields.update(change)
    with pytest.raises(PortalError, match='切换'):
        cs.SelectCourse(sample.course, sample.group, confirmed=True)
    assert not s.calls


def test_page_logged_out_before_submit(sample):
    s = Session()
    cs = course.CS(s)
    s.frame.html = '<input type="password">'
    with pytest.raises(PortalError, match='过期'):
        cs.SelectCourse(sample.course, sample.group, confirmed=True)
    assert not s.calls


def run_cli(monkeypatch, s, answers, picks):
    monkeypatch.setattr(course, 'Login', lambda **_: (s, 'sample'))
    answer_iter = iter(answers)
    pick_iter = iter(picks)
    monkeypatch.setattr('builtins.input', lambda _: next(answer_iter))
    monkeypatch.setattr(course, 'pick', lambda rows: next(pick_iter))
    return course.main([])


def test_empty_keyword_and_no_courses(monkeypatch):
    s = Session([{'tmpList': []}])
    assert run_cli(monkeypatch, s, ['', 'missing', 'q'], []) == 0


def test_quit_at_course(sample, monkeypatch):
    s = Session([{'tmpList': [sample.course]}])
    assert run_cli(monkeypatch, s, ['课程二'], [None]) == 0


def test_quit_at_group(sample, monkeypatch):
    s = Session([{'tmpList': [sample.course]}, [sample.group]])
    assert run_cli(monkeypatch, s, ['课程二'], [sample.course, None]) == 0


@pytest.mark.parametrize('child_choice', [None, {'do_jxb_id': 'CHILD'}])
def test_compound_cli(sample, monkeypatch, child_choice):
    sample.course['jxbzls'] = '2'
    child = {'do_jxb_id': 'CHILD'}
    replies = [{'tmpList': [sample.course]}, [sample.group], 'view', [child], {'flag': '1'}]
    s = Session(replies)
    answers = ['课程二', '确认选课', '', 'q']
    assert run_cli(monkeypatch, s, answers, [sample.course, sample.group, child_choice]) == 0
    assert sum('xkBcZy' in url for url, _ in s.calls) == (child_choice is not None)


def test_login_only(monkeypatch):
    s = Session()
    monkeypatch.setattr(course, 'Login', lambda **_: (s, 'sample'))
    monkeypatch.setattr('builtins.input', lambda _: '')
    assert course.main(['--login-only']) == 0
    assert not s.calls and s.closed


def test_chrome_entrypoint(monkeypatch):
    monkeypatch.setattr(course, 'main', lambda argv: 0 if argv == ['--login-only'] else 1)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(course.__file__).with_name('ChromeLogin.py')), run_name='__main__')
    assert exc.value.code == 0
