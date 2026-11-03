from types import SimpleNamespace as NS

import pytest
import playwright.sync_api as api

import Course_Selection as course
import Login as login
from BrowserSession import PortalError, SelectionClosed
from conftest import Frame, Session

NOTICE = '对不起，当前不属于选课阶段，如有需要，请与管理员联系！'


def closed_session():
    session = Session(fields={'sessionUserKey': 'fixture-user', 'csrftoken': 'fixture-private'})
    session.frame.visible_text = NOTICE
    session.frame.html = '<div class="nodata"><span>' + NOTICE + '</span></div>'
    return session


def attach(monkeypatch, frame):
    context = NS(pages=[NS(frames=[frame], goto=lambda *a, **k: None,
                           wait_for_timeout=lambda _: None)], close=lambda: None)
    pw = NS(chromium=NS(launch=lambda **k: NS(new_context=lambda: context)), stop=lambda: None)
    monkeypatch.setattr(api, 'sync_playwright', lambda: NS(start=lambda: pw))


def test_login_accepts_closed_period(monkeypatch):
    session = closed_session()
    attach(monkeypatch, session.frame)
    answers = iter(['', 'q'])
    connected, _ = login.Login(input_fn=lambda _: next(answers))
    assert connected.frame is session.frame
    connected.close()


def test_closed_period_cli_never_initializes_selection(monkeypatch, capsys):
    session = closed_session()
    monkeypatch.setattr(course, 'Login', lambda **_: (session, 'sample'))
    monkeypatch.setattr('builtins.input', lambda _: '')
    def forbidden(*_):
        raise AssertionError('closed-period mode must not initialize selection endpoints')
    monkeypatch.setattr(course, 'CS', forbidden)
    assert course.main([]) == 0
    assert '选课未开放' in capsys.readouterr().out
    assert session.closed and not session.calls


def test_diagnose_closed_period(monkeypatch, capsys):
    session = closed_session()
    monkeypatch.setattr(course, 'Login', lambda **_: (session, 'sample'))
    monkeypatch.setattr('builtins.input', lambda _: '')
    assert course.main(['--diagnose']) == 0
    text = capsys.readouterr().out
    assert 'selection_closed' in text and 'csrftoken' in text
    assert 'fixture-private' not in text and 'fixture-user' not in text
    assert not session.calls


def test_direct_cs_closed_period_never_requests():
    session = closed_session()
    with pytest.raises(PortalError, match='选课未开放'):
        course.CS(session)
    assert not session.calls


def test_get_info_recognizes_authenticated_closed_page():
    assert login.GetInfo(closed_session()) == {'authenticated_course_page': True}


def test_window_closes_after_ready_stops_next_query():
    session = Session()
    cs = course.CS(session)
    session.frame.visible_text = NOTICE
    with pytest.raises(SelectionClosed):
        cs.GetCourses()
    assert not session.calls


def test_window_close_during_cli_is_normal_exit(monkeypatch, capsys):
    session = Session()
    monkeypatch.setattr(course, 'Login', lambda **_: (session, 'sample'))
    def search(_):
        session.frame.visible_text = NOTICE
        return '课程'
    monkeypatch.setattr('builtins.input', search)
    assert course.main([]) == 0
    assert '选课未开放' in capsys.readouterr().out
    assert not session.calls and session.closed


@pytest.mark.parametrize('notice', ['当前不属于选课阶段', '不在选课时间内', '选课未开放'])
def test_closed_visible_notice_overrides_stale_batch(notice):
    frame = Frame()
    frame.visible_text = notice
    assert login.page_state(frame) == 'selection_closed'


@pytest.mark.parametrize('fields,expected', [({'sessionUserKey': 'fixture'}, 'teaching_home'),
                                           ({'sessionUserKey': ''}, 'unknown'), ({}, 'unknown')])
def test_teaching_home_requires_session_marker(fields, expected):
    frame = Frame(fields, url='http://jw.swu.edu.cn/jwglxt/xtgl/index_initMenu.html')
    assert login.page_state(frame) == expected


def test_password_form_and_foreign_host_are_not_authenticated():
    frame = Frame()
    frame.html = '<input type="password">'
    assert login.page_state(frame) == 'login_required'
    frame.html = ''
    frame.url = 'https://jw.swu.edu.cn/jwglxt/xtgl/login_slogin.html'
    assert login.page_state(frame) == 'login_required'
    frame.url = 'https://jw.swu.edu.cn.evil.invalid/jwglxt/xsxk/index.html'
    assert login.page_state(frame) == 'unknown'


def test_login_only_accepts_teaching_home(monkeypatch):
    frame = Frame({'sessionUserKey': 'fixture'}, url='http://jw.swu.edu.cn/jwglxt/xtgl/index_initMenu.html')
    attach(monkeypatch, frame)
    connected, _ = login.Login(require_selection=False, input_fn=lambda _: '')
    assert connected.frame is frame
    connected.close()


def test_normal_mode_does_not_mislabel_home_as_open_selection(monkeypatch):
    frame = Frame({'sessionUserKey': 'fixture'}, url='http://jw.swu.edu.cn/jwglxt/xtgl/index_initMenu.html')
    attach(monkeypatch, frame)
    answers = iter(['', 'q'])
    with pytest.raises(PortalError, match='退出'):
        login.Login(input_fn=lambda _: next(answers))


def test_selection_preferred_over_background_home(monkeypatch):
    session = closed_session()
    context = NS(pages=[NS(frames=[session.frame], goto=lambda *a, **k: None, wait_for_timeout=lambda _: None),
                        NS(frames=[Frame({'sessionUserKey': 'fixture'}, url='http://jw.swu.edu.cn/jwglxt/xtgl/index_initMenu.html')], wait_for_timeout=lambda _: None)], close=lambda: None)
    pw = NS(chromium=NS(launch=lambda **k: NS(new_context=lambda: context)), stop=lambda: None)
    monkeypatch.setattr(api, 'sync_playwright', lambda: NS(start=lambda: pw))
    connected, _ = login.Login(require_selection=False, input_fn=lambda _: '')
    assert connected.frame is session.frame
    connected.close()


@pytest.mark.parametrize('argument', ['--diagnose', '--login-only'])
def test_cli_readonly_modes_do_not_require_selection(monkeypatch, capsys, argument):
    session = Session(fields={'sessionUserKey': 'fixture-private-user'})
    session.frame.url = 'http://jw.swu.edu.cn/jwglxt/xtgl/index_initMenu.html'
    options = []
    def connect(**kwargs):
        options.append(kwargs)
        return session, 'fixture'
    monkeypatch.setattr(course, 'Login', connect)
    monkeypatch.setattr('builtins.input', lambda _: '')
    assert course.main([argument]) == 0
    assert options[0]['require_selection'] is False
    assert not session.calls and session.closed
    text = capsys.readouterr().out
    assert 'fixture-private-user' not in text
    if argument == '--diagnose':
        assert 'teaching_home' in text and '"selection_open": null' in text
