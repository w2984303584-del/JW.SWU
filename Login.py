"""Human completes SSO/captcha in a real browser. Passwords never enter Python."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from BrowserSession import BrowserSession, PortalError

# Start at the current official portal and let it construct its own SSO return
# parameters; do not hard-code the legacy teaching-system CAS service URL.
DEFAULT_URL = 'https://ywtb.swu.edu.cn/'
CLOSED_MARKERS = ('当前不属于选课阶段', '不在选课时间内', '选课未开放')


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.values = {}
        self.has_password = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input':
            if attrs.get('type', '').lower() == 'password':
                self.has_password = True
            name = attrs.get('name') or attrs.get('id')
            if name and attrs.get('type', '').lower() != 'password':
                self.values[name] = attrs.get('value', '')
        if tag == 'select':
            self.select_name = attrs.get('name') or attrs.get('id')
        if tag == 'option' and 'selected' in attrs and getattr(self, 'select_name', None):
            self.values[self.select_name] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'select':
            self.select_name = None


def read_fields(frame):
    """Read DOM properties as JS may change values without updating HTML attributes."""
    parsed = Inputs(frame.content())
    live = frame.evaluate("""() => Object.fromEntries(
      Array.from(document.querySelectorAll('input,select')).filter(e =>
        e.type !== 'password' && (e.name || e.id)
      ).map(e => [e.name || e.id, e.value])
    )""")
    parsed.values.update(live)
    return parsed


def page_state(frame, fields=None):
    """Classify the actual page, without treating a missing batch as failed login."""
    url = urlsplit(frame.url)
    if url.hostname != 'jw.swu.edu.cn' or not url.path.startswith('/jwglxt/'):
        return 'unknown'
    fields = fields or read_fields(frame)
    if fields.has_password or '/login_' in url.path:
        return 'login_required'
    if '/xsxk/' in url.path:
        text = frame.evaluate('() => document.body ? document.body.innerText : ""')
        if isinstance(text, str) and any(marker in text for marker in CLOSED_MARKERS):
            return 'selection_closed'
        if fields.values.get('firstXkkzId') or fields.values.get('xkkz_id'):
            return 'selection_ready'
    if url.path.endswith('/xtgl/index_initMenu.html') and fields.values.get('sessionUserKey'):
        return 'teaching_home'
    return 'unknown'


def course_frames(context, *, include_closed=False, include_home=False):
    from playwright.sync_api import Error

    # input() pauses the sync Playwright event loop. Flush queued navigation,
    # popup and frame events BEFORE reading cached context.pages/frame.url.
    # Zero is an event-loop checkpoint, not a guessed page-load delay.
    for page in list(context.pages):
        try:
            page.wait_for_timeout(0)
        except Error:
            pass  # A just-closed page can still be in the pre-checkpoint list.
    found = []
    pages = list(context.pages)
    if not pages:
        raise PortalError('浏览器窗口已关闭，请重启工具。')
    for page in pages:
        for frame in list(page.frames):
            try:
                url = urlsplit(frame.url)
                if url.hostname == 'jw.swu.edu.cn' and url.path.startswith('/jwglxt/'):
                    fields = read_fields(frame)
                    state = page_state(frame, fields)
                    if state == 'selection_ready' or (include_closed and state == 'selection_closed') or (include_home and state == 'teaching_home'):
                        found.append(frame)
            except Error:
                continue  # Navigation may detach a frame while it is inspected.
    return found


def Login(username=None, password=None, *, channel='msedge', profile=None, input_fn=input, require_selection=True):
    """Returns (BrowserSession, student_id). Legacy password arguments are rejected."""
    if password:
        raise PortalError('请移除代码中的密码，在浏览器页面亲自登录。')
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    context = None
    try:
        options = {'headless': False, 'channel': channel} if channel else {'headless': False}
        if profile:
            context = pw.chromium.launch_persistent_context(str(Path(profile).resolve()), **options)
        else:
            browser = pw.chromium.launch(**options)
            context = browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(DEFAULT_URL, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            print('自动打开登录页未完成。请在此浏览器手动打开学校办事大厅，再进入教务系统。')
        if require_selection:
            print('请登录新版办事大厅并进入【教务系统 → 自主选课】；未开放页面也可以识别。')
        else:
            print('请登录新版办事大厅并进入【教务系统】主页；此模式不要求选课开放。')
        print('校外访问：如教务系统打不开，先在办事大厅点【访问内网】，按学校指引连接无感 VPN。')
        while True:
            if input_fn('准备好后按回车检查；输入 q 退出：').strip().lower() == 'q':
                raise PortalError('已退出登录。')
            frames = course_frames(context, include_closed=True, include_home=not require_selection)
            # A user commonly leaves the teaching homepage open behind the
            # selection tab. Prefer the unique selection page over that homepage.
            selection = [f for f in frames if page_state(f) in ('selection_ready', 'selection_closed')]
            if selection:
                frames = selection
            if len(frames) != 1:
                print('尚未找到唯一的目标教务页。请保留一个自主选课页；登录/诊断模式也接受教务主页。')
                continue
            frame = frames[0]
            fields = read_fields(frame).values
            su = parse_qs(urlsplit(frame.url).query).get('su', [''])[0]
            num = fields.get('xh_id') or fields.get('xh') or su or username or ''
            return BrowserSession(frame, context, pw), num
    except BaseException:
        try:
            if context:
                context.close()
        finally:
            pw.stop()
        raise


def GetInfo(session, username=None):
    """Compatibility helper: no personal information scraping or logging."""
    return {'authenticated_course_page': page_state(session.frame) in ('selection_ready', 'selection_closed')}


if __name__ == '__main__':
    with Login()[0]:
        input('选课页已识别。按回车关闭浏览器。')
