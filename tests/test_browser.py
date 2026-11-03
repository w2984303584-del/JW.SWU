"""Real Chromium, but ALL requests intercepted. Never accesses the university."""
import json
import time
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import sync_playwright

import Login as login
from BrowserSession import AuthenticationRequired, BrowserSession
from Course_Selection import CS
from conftest import COURSE, FIELDS, GROUP


@pytest.fixture
def portal():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        calls = []
        state = {'expired': False, 'enrolled': False}
        fields = ''.join(f'<input type="hidden" name="{k}" value="{v}">' for k, v in FIELDS.items())
        def handler(route):
            req = route.request
            path = urlsplit(req.url).path
            calls.append((path, req.method, parse_qs(req.post_data or '')))
            if path == '/cas/login':
                html = '<html><input type="password"><p>模拟站：请人工确认认证</p><button onclick="document.cookie=\'fixture_auth=ok; path=/\';location.href=\'/jwglxt/xsxk/index.html?su=sample\'">模拟人工登录</button></html>'
                return route.fulfill(content_type='text/html; charset=utf-8', body=html)
            if path == '/jwglxt/xsxk/index.html':
                return route.fulfill(content_type='text/html; charset=utf-8', body='<html>' + fields + '</html>')
            if state['expired'] or 'fixture_auth=ok' not in req.headers.get('cookie', ''):
                return route.fulfill(status=401, body='login required')
            if 'PartDisplay' in path:
                body = {'tmpList': [COURSE]}
            elif 'cxJxbWithKch' in path:
                body = [GROUP, dict(GROUP, do_jxb_id='OTHER')]
            elif 'xkBcZy' in path:
                assert parse_qs(req.post_data)['jxb_ids'] == ['G2']
                state['enrolled'] = True
                body = {'flag': '1'}
            elif path == '/fixture/selected':
                body = {'selected': ['G2'] if state['enrolled'] else []}
            else:
                return route.fulfill(status=404, body='unexpected fixture path')
            route.fulfill(content_type='application/json', body=json.dumps(body))
        context.route('**/*', handler)
        yield NS(pw=pw, browser=browser, context=context, calls=calls, state=state)
        browser.close()


def test_actual_login_query_choose_submit_verify(portal, monkeypatch):
    # Only launcher is injected; production Login, frame discovery, DOM extraction,
    # fetch JS, browser cookie handling, CS parsing and submission execute unchanged.
    import playwright.sync_api as api
    fake_pw = NS(chromium=NS(launch=lambda **_: NS(new_context=lambda: portal.context)), stop=lambda: None)
    monkeypatch.setattr(api, 'sync_playwright', lambda: NS(start=lambda: fake_pw))
    monkeypatch.setattr(login, 'DEFAULT_URL', 'http://jw.swu.edu.cn/cas/login')
    count = 0
    def person(_prompt):
        nonlocal count
        count += 1
        if count == 1:
            return ''  # SSO page alone must not be accepted.
        page = portal.context.pages[0]
        page.get_by_role('button', name='模拟人工登录').click()
        page.wait_for_url('**/jwglxt/xsxk/**')
        return ''
    session, num = login.Login(input_fn=person)
    with session:
        assert count == 2 and num == 'sample'
        cs = CS(session, num)
        courses = cs.GetCourses('课程二')
        groups = cs.groups(courses[0])
        assert len(groups) == 2
        assert cs.SelectCourse(courses[0], groups[0], confirmed=True)
        assert session.get('/fixture/selected').json() == {'selected': ['G2']}
        portal.state['expired'] = True
        with pytest.raises(AuthenticationRequired):
            cs.GetCourses()
    assert sum('xkBcZy' in path for path, _, _ in portal.calls) == 1


def test_browser_iframe_and_live_fields(portal):
    page = portal.context.new_page()
    page.goto('http://jw.swu.edu.cn/jwglxt/xsxk/index.html')
    page.evaluate("document.querySelector('[name=firstKklxdm]').value='99'")
    assert login.read_fields(page).values['firstKklxdm'] == '99'
    page.evaluate("document.body.innerHTML='<iframe src=\"/jwglxt/xsxk/index.html\"></iframe>'")
    page.frame_locator('iframe').locator('input').first.wait_for(state='attached')
    assert len(login.course_frames(portal.context)) == 1
    assert '/xsxk/' in login.course_frames(portal.context)[0].url


def test_real_browser_auth_cookie_required(portal):
    page = portal.context.new_page()
    page.goto('http://jw.swu.edu.cn/jwglxt/xsxk/index.html')
    with pytest.raises(AuthenticationRequired):
        CS(BrowserSession(page)).GetCourses()
    assert not portal.state['enrolled']


def test_manual_navigation_during_terminal_input_is_discovered(portal):
    """Browser changes independently, exactly as a user acts while input() blocks."""
    page = portal.context.new_page()
    page.goto('http://jw.swu.edu.cn/cas/login')
    fields = ''.join(f'<input name="{k}" value="{v}">' for k, v in FIELDS.items())
    page.evaluate('''fields => setTimeout(() => {
      history.replaceState(null, '', '/jwglxt/xsxk/index.html?su=sample');
      document.body.innerHTML = fields;
    }, 20)''', fields)
    # Intentional blocking: test the production input() seam, not a Playwright click.
    time.sleep(0.25)
    found = login.course_frames(portal.context)
    # The following call is deliberately AFTER discovery: it proves the browser
    # had changed but cannot accidentally pump events before the code under test.
    assert page.evaluate('location.pathname') == '/jwglxt/xsxk/index.html'
    assert found == [page.main_frame]


def test_manual_popup_during_terminal_input_is_discovered(portal):
    page = portal.context.new_page()
    page.goto('http://jw.swu.edu.cn/cas/login')
    fields = ''.join(f'<input name="{k}" value="{v}">' for k, v in FIELDS.items())
    page.evaluate('''fields => setTimeout(() => {
      const child = window.open('about:blank');
      child.document.open();
      child.document.write('<html><body>' + fields + '</body></html>');
      child.document.close();
      child.history.replaceState(null, '', '/jwglxt/xsxk/index.html');
    }, 20)''', fields)
    time.sleep(0.25)
    found = login.course_frames(portal.context)
    assert len(portal.context.pages) == 2
    assert portal.context.pages[1].evaluate('location.pathname') == '/jwglxt/xsxk/index.html'
    assert len(found) == 1 and found[0] != page.main_frame


def test_real_browser_closed_period_cli_has_zero_posts(portal, monkeypatch, capsys):
    import Course_Selection as course
    notice = '对不起，当前不属于选课阶段，如有需要，请与管理员联系！'
    portal.context.route('**/jwglxt/xsxk/**', lambda route: route.fulfill(
        content_type='text/html; charset=utf-8',
        body='<html><input id="sessionUserKey" value="fixture"><input name="csrftoken" value="fixture"><div class="nodata"><span>' + notice + '</span></div></html>'))
    page = portal.context.new_page()
    page.goto('http://jw.swu.edu.cn/jwglxt/xsxk/zzxkyzb_cxZzxkYzbIndex.html')
    assert login.page_state(page) == 'selection_closed'
    assert login.course_frames(portal.context) == []
    assert login.course_frames(portal.context, include_closed=True) == [page.main_frame]
    session = BrowserSession(page)
    monkeypatch.setattr(course, 'Login', lambda **_: (session, ''))
    monkeypatch.setattr('builtins.input', lambda _: '')
    assert course.main([]) == 0
    assert '选课未开放' in capsys.readouterr().out
    assert not any(method == 'POST' for _, method, _ in portal.calls)


def test_real_login_only_continues_on_teaching_home(portal, monkeypatch):
    import playwright.sync_api as api
    portal.context.route('**/jwglxt/xtgl/index_initMenu.html', lambda route: route.fulfill(
        content_type='text/html; charset=utf-8', body='<html><input id="sessionUserKey" value="fixture-user">教务主页</html>'))
    fake_pw = NS(chromium=NS(launch=lambda **_: NS(new_context=lambda: portal.context)), stop=lambda: None)
    monkeypatch.setattr(api, 'sync_playwright', lambda: NS(start=lambda: fake_pw))
    monkeypatch.setattr(login, 'DEFAULT_URL', 'http://jw.swu.edu.cn/cas/login')
    def person(_):
        portal.context.pages[0].goto('http://jw.swu.edu.cn/jwglxt/xtgl/index_initMenu.html')
        return ''
    session, _ = login.Login(require_selection=False, input_fn=person)
    with session:
        assert login.page_state(session.frame) == 'teaching_home'
    assert not any(method == 'POST' for _, method, _ in portal.calls)
