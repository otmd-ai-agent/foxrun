"""Check editor embedding with Playwright and Chromium; no model is needed.

Run with a Python environment containing playwright and its Chromium browser:
    python demo/check_preview_browser.py
Optionally set PLAYWRIGHT_CHROMIUM_EXECUTABLE to an existing Chromium binary.
The browser routes simulate editor origins; the demo responses come from the
real HTTP handler. This does not exercise GitHub's authentication proxy.
"""
import os
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from unittest.mock import patch

from playwright.sync_api import sync_playwright
import server

APP = 'https://demo-8081.app.github.dev'
EDITOR = 'https://demo.github.dev'


def check(browser, local, webview, outer=EDITOR, allowed=True):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    context = browser.new_context()
    try:
        page = context.new_page()

        def route(request_route):
            request = request_route.request
            url = urlsplit(request.url)
            origin = f'{url.scheme}://{url.netloc}'
            if origin == APP:
                target = local + url.path + ('?' + url.query if url.query else '')
                req = urllib.request.Request(target, method=request.method,
                                             data=request.post_data_buffer,
                                             headers=request.headers)
                try:
                    response = opener.open(req, timeout=5)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    request_route.fulfill(status=response.status,
                                          headers=dict(response.headers),
                                          body=response.read())
            elif origin == webview:
                request_route.fulfill(content_type='text/html',
                                      body=f'<iframe src="{APP}/?vscodeBrowserReqId=123"></iframe>')
            elif origin == outer:
                request_route.fulfill(content_type='text/html',
                                      body=f'<iframe src="{webview}/"></iframe>')
            else:
                request_route.abort()

        page.route('**/*', route)
        if allowed:
            page.goto(outer)
            content = page.frame_locator('iframe').frame_locator('iframe')
            content.get_by_role('heading', name='Give a task a memory.').wait_for(timeout=5000)
            content.get_by_role('button', name='Use a sample task').click()
            assert content.locator('textarea').input_value(), 'Sample task did not populate the message.'
            print(f'PASS: preview page and sample button through {webview}')
        else:
            with page.expect_console_message(
                predicate=lambda message: 'frame-ancestors' in message.text,
                timeout=5000,
            ):
                page.goto(outer)
            print(f'PASS: blocked untrusted ancestor ({outer}, {webview})')
    finally:
        context.close()


def main():
    httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    local = f'http://127.0.0.1:{httpd.server_port}'
    try:
        with patch.object(server, 'status', return_value={'ready': True, 'stage': 'Ready', 'detail': 'Browser test'}), \
             patch.object(server.agent, 'tasks', return_value=[]), sync_playwright() as playwright:
            options = {'headless': True}
            if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'):
                options['executable_path'] = os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE']
            browser = playwright.chromium.launch(**options)
            try:
                for webview in ['https://preview.vscode-webview.net', 'https://preview.vscode-cdn.net']:
                    check(browser, local, webview)
                check(browser, local, 'https://preview.vscode-webview.net',
                      outer='https://untrusted.example', allowed=False)
                check(browser, local, 'https://preview.vscode-webview.net.untrusted.example', allowed=False)
            finally:
                browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


if __name__ == '__main__':
    main()
