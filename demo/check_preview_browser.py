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


def check_chat(browser, local):
    """Recover one model run after a lost acknowledgement, reload, and bad state responses."""
    from playwright.sync_api import expect
    import json
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    release = threading.Event()
    context = browser.new_context()
    failures = {'state': None}

    def slow_chat(*args):
        if not release.wait(15):
            raise TimeoutError('Test model was not released')
        return {'answer': 'Recovered model result', 'events': [], 'seconds': 1, 'completion_tokens': 2}

    try:
        page = context.new_page()

        def lost_ack(route):
            request = route.request
            req = urllib.request.Request(local + '/api/chat', method='POST',
                                         data=request.post_data_buffer, headers=request.headers)
            with opener.open(req, timeout=3) as response:
                assert response.status == 202
                assert json.load(response)['status'] == 'running'
            # Simulate a forwarding connection that drops the acknowledgement.
            route.fulfill(status=502, content_type='application/json', body='')

        def state_route(route):
            if failures['state'] == 'empty':
                route.fulfill(status=200, content_type='application/json', body='')
            elif failures['state'] == 'html':
                route.fulfill(status=502, content_type='text/html', body='<h1>Gateway error</h1>')
            else:
                route.continue_()

        page.route('**/api/chat', lost_ack)
        page.route('**/api/state', state_route)
        with patch.object(server.agent, 'chat', side_effect=slow_chat) as model:
            page.goto(local)
            page.get_by_role('button', name='Use a sample task').click()
            page.get_by_role('button', name='Send to local Gemma').click()
            expect(page.locator('#metrics')).to_contain_text('Running on CPU', timeout=6000)
            expect(page.get_by_role('button', name='Send to local Gemma')).to_be_disabled()
            page.reload()
            expect(page.locator('#metrics')).to_contain_text('Running on CPU', timeout=6000)
            expect(page.locator('.message.user')).to_have_count(1)
            release.set()
            expect(page.locator('#chat')).to_contain_text('Recovered model result', timeout=6000)
            expect(page.locator('.message.assistant')).to_have_count(1)
            expect(page.get_by_role('button', name='Send to local Gemma')).to_be_enabled()
            assert model.call_count == 1
            print('PASS: lost acknowledgement and page reload recover one model run without resubmission')

            for failure, expected in [('empty', 'empty response'), ('html', 'page instead of demo data')]:
                failures['state'] = failure
                page.reload()
                expect(page.locator('#error')).to_contain_text(expected, timeout=6000)
                expect(page.get_by_role('button', name='Send to local Gemma')).to_be_disabled()
                failures['state'] = None
                expect(page.get_by_role('button', name='Send to local Gemma')).to_be_enabled(timeout=6000)
                expect(page.locator('.message.assistant')).to_have_count(1)
                assert model.call_count == 1
                print(f'PASS: clear {failure} response error and automatic state recovery')

        page.unroute('**/api/chat', lost_ack)
        page.get_by_role('button', name='New chat · keep tasks').click()
        with patch.object(server.agent, 'chat', side_effect=RuntimeError('Model connection failed')):
            page.get_by_role('button', name='Use a sample task').click()
            page.get_by_role('button', name='Send to local Gemma').click()
            expect(page.locator('#error')).to_contain_text('Model connection failed', timeout=6000)
            expect(page.locator('#metrics')).to_have_text('The model request stopped.')
            expect(page.get_by_role('button', name='Send to local Gemma')).to_be_enabled()
            print('PASS: model failure is displayed and controls recover')
    finally:
        release.set()
        acquired = server.LOCK.acquire(timeout=16)
        if acquired:
            server.LOCK.release()
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
                check_chat(browser, local)
            finally:
                browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


if __name__ == '__main__':
    main()
