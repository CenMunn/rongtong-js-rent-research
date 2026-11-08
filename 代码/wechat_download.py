"""下载公开微信文章。可读的页面直接下载，其他页面在本机浏览器中等待正文。"""
from contextlib import ExitStack
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup


class ArticleDownloader:
    def __init__(self, session, stack: ExitStack, wait_seconds=180, browser=True):
        self.session = session
        self.stack = stack
        self.wait_seconds = wait_seconds
        self.browser = browser
        self.context = None

    def get(self, url):
        try:
            response = self.session.get(url, timeout=(6, 20))
            response.raise_for_status()
            body = BeautifulSoup(response.content, "html.parser", from_encoding="utf-8").select_one("#js_content")
            if (urlsplit(response.url).hostname == "mp.weixin.qq.com" and body
                    and (body.get_text(strip=True) or body.select_one("img"))):
                return response.content, "直接下载"
            reason = "微信要求验证" if "captcha" in response.url else "未取得正文"
        except requests.RequestException as exc:
            reason = type(exc).__name__
        if not self.browser:
            raise ValueError(reason)
        print(f"直接下载未取得正文（{reason}），正在用浏览器打开原文。", flush=True)
        return self.from_browser(url), "浏览器下载"

    def from_browser(self, url):
        try:
            from playwright.sync_api import sync_playwright, Error, TimeoutError
        except ImportError as exc:
            raise ValueError("浏览器下载需要 playwright，请用同目录的启动器运行。") from exc
        try:
            if self.context is None:
                engine = self.stack.enter_context(sync_playwright())
                for channel in ("msedge", "chrome", None):
                    try:
                        browser = engine.chromium.launch(channel=channel, headless=False)
                        break
                    except Error:
                        continue
                else:
                    raise ValueError("未能启动 Edge 或 Chrome。请检查本机浏览器，或用同一 Python 执行 playwright install chromium。")
                self.stack.callback(browser.close)
                self.context = browser.new_context()
            page = self.context.new_page()
            try:
                print(f"如微信提示验证，请在新打开的窗口完成；脚本最多等待 {self.wait_seconds} 秒。", flush=True)
                page.goto(url, wait_until="commit", timeout=30000)
                try:
                    page.wait_for_function("""() => {
                      const body=document.querySelector('#js_content');
                      return location.hostname==='mp.weixin.qq.com' && body &&
                        (body.textContent.trim() || body.querySelector('img')) &&
                        document.querySelector('#js_name, #js_profile_qrcode .profile_nickname')?.textContent.trim();
                    }""",timeout=self.wait_seconds*1000)
                except TimeoutError as exc:
                    path=urlsplit(page.url).path
                    raise ValueError(f"等待正文超时（浏览器路径 {path}）；未把此页存为文章。") from exc
                return page.content().encode("utf-8")
            finally:
                if not page.is_closed():
                    page.close()
        except Error as exc:
            raise ValueError(f"浏览器下载未完成：{str(exc).splitlines()[0]}") from exc
