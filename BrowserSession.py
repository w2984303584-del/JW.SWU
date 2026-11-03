"""Browser-owned authentication and same-origin transport; no cookie export."""
from dataclasses import dataclass
import json
from urllib.parse import urlencode, urljoin, urlsplit


class PortalError(RuntimeError):
    """Actionable portal failure, without credentials or response bodies."""


class AuthenticationRequired(PortalError):
    pass


class SubmissionUnknown(PortalError):
    pass


class SelectionClosed(PortalError):
    """Authenticated, but the official selection window is closed."""


def browser_available():
    """Quiet launcher preflight: missing browser is a normal install condition."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, timeout=10000)
            browser.close()
        return True
    except Exception:
        return False


@dataclass
class Response:
    text: str
    status_code: int

    def json(self):
        try:
            return json.loads(self.text)
        except (ValueError, TypeError) as exc:
            raise PortalError('接口未返回 JSON；请检查登录状态和选课页面。') from exc


FETCH = """async ({url, method, body, timeout}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const headers = {'X-Requested-With': 'XMLHttpRequest'};
    if (method === 'POST') headers['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8';
    const response = await fetch(url, {
      method, body: method === 'POST' ? body : undefined,
      credentials: 'same-origin', headers, redirect: 'follow', signal: controller.signal
    });
    return {status: response.status, url: response.url, text: await response.text()};
  } finally { clearTimeout(timer); }
}"""


def origin(url):
    parsed = urlsplit(url)
    return f'{parsed.scheme}://{parsed.netloc}'


class BrowserSession:
    def __init__(self, frame, context=None, playwright=None, *, timeout=20000):
        self.frame = frame
        self.context = context
        self.playwright = playwright
        self.timeout = timeout
        self.base_url = origin(frame.url)
        self.closed = False

    def request(self, method, url, data=None, **_ignored):
        absolute = urljoin(self.base_url + '/', url)
        if origin(absolute) != self.base_url or urlsplit(absolute).scheme not in ('http', 'https'):
            raise PortalError('接口必须与当前教务页面同源。')
        if origin(self.frame.url) != self.base_url:
            raise AuthenticationRequired('页面已离开教务系统，请重新登录。')
        try:
            result = self.frame.evaluate(FETCH, {
                'url': absolute, 'method': method, 'body': urlencode(data or {}),
                'timeout': self.timeout,
            })
        except Exception as exc:
            error = SubmissionUnknown if method == 'POST' else PortalError
            raise error('请求未取得明确结果；请到网页核对，程序没有自动重试。') from exc
        text = result['text']
        lower = text.lower()
        if origin(result['url']) != self.base_url or '/cas/login' in result['url'] or (
            '<html' in lower and ('type="password"' in lower or "type='password'" in lower)
        ):
            raise AuthenticationRequired('登录已过期，请在浏览器重新登录后重启工具。')
        if result['status'] in (401, 403):
            raise AuthenticationRequired('学校要求重新认证，请回到浏览器处理。')
        if not 200 <= result['status'] < 300:
            error = SubmissionUnknown if method == 'POST' else PortalError
            raise error(f"接口 HTTP {result['status']}；请在网页核对状态。")
        if '<html' in lower and ('document.cookie' in lower or '验证码' in text):
            raise AuthenticationRequired('浏览器需要完成验证，请回到学校页面处理。')
        return Response(text, result['status'])

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, data=None, **kwargs):
        return self.request('POST', url, data, **kwargs)

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                if self.context:
                    self.context.close()
            finally:
                if self.playwright:
                    self.playwright.stop()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
