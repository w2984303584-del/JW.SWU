from types import SimpleNamespace as NS

import pytest
import playwright.sync_api as api

import Login as login
from BrowserSession import PortalError
from conftest import Frame


def setup_login(monkeypatch, *, navigate_error=False, launch_error=False):
    events = []
    frame = Frame()
    def goto(*_, **__):
        if navigate_error:
            raise TimeoutError()
    page = NS(frames=[frame], goto=goto, wait_for_timeout=lambda _: None)
    context = NS(pages=[page], close=lambda: events.append('close'))
    def launch(**kwargs):
        events.append(('launch', kwargs))
        if launch_error:
            raise RuntimeError('launch failed')
        return NS(new_context=lambda: context)
    def persistent(path, **kwargs):
        events.append(('profile', path))
        return context
    pw = NS(chromium=NS(launch=launch, launch_persistent_context=persistent), stop=lambda: events.append('stop'))
    monkeypatch.setattr(api, 'sync_playwright', lambda: NS(start=lambda: pw))
    return events, context


def test_login_and_resource_cleanup(monkeypatch):
    events, _ = setup_login(monkeypatch)
    session, num = login.Login(input_fn=lambda _: '')
    assert num == 'sample'
    session.close()
    assert events[-2:] == ['close', 'stop']


def test_profile_option(monkeypatch, tmp_path):
    events, _ = setup_login(monkeypatch)
    session, _ = login.Login(profile=tmp_path / 'dedicated', channel=None, input_fn=lambda _: '')
    session.close()
    assert events[0][0] == 'profile'


def test_user_quits(monkeypatch):
    events, _ = setup_login(monkeypatch)
    with pytest.raises(PortalError, match='退出'):
        login.Login(input_fn=lambda _: 'q')
    assert events[-2:] == ['close', 'stop']


def test_navigation_error_manual_recovery(monkeypatch):
    events, _ = setup_login(monkeypatch, navigate_error=True)
    session, _ = login.Login(input_fn=lambda _: '')
    session.close()
    assert events[-1] == 'stop'


def test_launch_failure_stops_playwright(monkeypatch):
    events, _ = setup_login(monkeypatch, launch_error=True)
    with pytest.raises(RuntimeError):
        login.Login()
    assert events[-1] == 'stop'


def test_multiple_pages_not_accepted(monkeypatch):
    events, context = setup_login(monkeypatch)
    context.pages *= 2
    answers = iter(['', 'q'])
    with pytest.raises(PortalError):
        login.Login(input_fn=lambda _: next(answers))
    assert events[-2:] == ['close', 'stop']


def test_all_browser_windows_closed():
    with pytest.raises(PortalError, match='窗口已关闭'):
        login.course_frames(NS(pages=[]))


def test_closed_page_and_detached_frame_skipped():
    def closed(_):
        raise api.Error('Target closed')
    frame = Frame()
    def detached():
        raise api.Error('Frame detached')
    bad_frame = Frame()
    bad_frame.content = detached
    context = NS(pages=[NS(wait_for_timeout=closed, frames=[]),
                        NS(wait_for_timeout=lambda _: None, frames=[bad_frame, frame])])
    assert login.course_frames(context) == [frame]


def test_default_entry_is_official_portal():
    assert login.DEFAULT_URL == 'https://ywtb.swu.edu.cn/'


def test_login_visits_official_portal(monkeypatch):
    _, context = setup_login(monkeypatch)
    visited = []
    context.pages[0].goto = lambda url, **_: visited.append(url)
    session, _ = login.Login(input_fn=lambda _: '')
    session.close()
    assert visited == ['https://ywtb.swu.edu.cn/']
