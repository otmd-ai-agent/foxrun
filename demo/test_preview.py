"""Exercise preview requests, request guards, and startup on a selected port."""
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import server
import start


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_preview_query_loads_page(self):
        for path in ['/', '/?vscodeBrowserReqId=1730743200000', '/?other=value&vscodeBrowserReqId=123']:
            with self.subTest(path=path):
                code, headers, body = self.request('GET', path)
                self.assertEqual(code, 200)
                self.assertIn(b'Give a task a memory.', body)
                self.assertEqual(headers['Content-Type'], 'text/html; charset=utf-8')

    def test_api_query_and_unknown_path(self):
        code, _, body = self.request('GET', '/api/health?vscodeBrowserReqId=123')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['application'], 'foxrun-demo')
        with patch.object(server, 'status', return_value={'ready': False}):
            self.assertEqual(self.request('GET', '/api/state?preview=1')[0], 200)
        self.assertEqual(self.request('GET', '/missing?vscodeBrowserReqId=123')[0], 404)

    def test_preview_does_not_relax_post_request_guards(self):
        self.assertEqual(self.request('POST', '/api/new-chat', '{}', {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.request('POST', '/api/new-chat', '{}', {'X-Foxrun-Demo': '1', 'Content-Type': 'text/plain'})[0], 403)
        self.assertEqual(self.request('OPTIONS', '/api/new-chat')[0], 501)
        with patch.object(server, 'status', return_value={'ready': True}):
            code, _, body = self.request('POST', '/api/new-chat', '{}', {'X-Foxrun-Demo': '1', 'Content-Type': 'application/json'})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {'ok': True})


    def test_chat_acknowledges_before_model_and_recovers_result(self):
        entered, release = threading.Event(), threading.Event()
        result = {'answer': 'Saved proof', 'events': [], 'seconds': 1, 'completion_tokens': 2}

        def slow_chat(*args):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test model was not released')
            return result

        headers = {'Content-Type': 'application/json', 'X-Foxrun-Demo': '1'}
        body = json.dumps({'message': 'test', 'request_id': 'a' * 32})
        with patch.object(server, 'status', return_value={'ready': True}), \
             patch.object(server.agent, 'tasks', return_value=[]), \
             patch.object(server.agent, 'chat', side_effect=slow_chat) as model:
            try:
                code, _, data = self.request('POST', '/api/chat', body, headers)
                self.assertEqual(code, 202)
                self.assertTrue(entered.wait(1))
                self.assertEqual(json.loads(data)['status'], 'running')
                self.assertEqual(self.request('GET', '/api/health')[0], 200)
                state = json.loads(self.request('GET', '/api/state')[2])
                self.assertEqual(state['chat']['status'], 'running')
                self.assertEqual(self.request('POST', '/api/chat', body, headers)[0], 202)
                other = json.dumps({'message': 'another', 'request_id': 'b' * 32})
                self.assertEqual(self.request('POST', '/api/chat', other, headers)[0], 409)
                self.assertEqual(self.request('POST', '/api/new-chat', '{}', headers)[0], 409)
                self.assertEqual(self.request('POST', '/api/accept', '{}', headers)[0], 409)
            finally:
                release.set()
                acquired = server.LOCK.acquire(timeout=6)
                if acquired: server.LOCK.release()
                self.assertTrue(acquired)
            state = json.loads(self.request('GET', '/api/state')[2])
            self.assertEqual(state['chat']['status'], 'complete')
            self.assertEqual(state['chat']['result'], result)
            self.assertEqual(self.request('POST', '/api/chat', body, headers)[0], 200)
            self.assertEqual(model.call_count, 1)
            changed = json.dumps({'message': 'different', 'request_id': 'a' * 32})
            self.assertEqual(self.request('POST', '/api/chat', changed, headers)[0], 409)
            self.assertEqual(self.request('POST', '/api/new-chat', '{}', headers)[0], 200)
            self.assertIsNone(json.loads(self.request('GET', '/api/state')[2])['chat'])

    def test_chat_failure_is_recoverable_and_invalid_requests_do_not_run(self):
        headers = {'Content-Type': 'application/json', 'X-Foxrun-Demo': '1'}
        with patch.object(server, 'status', return_value={'ready': True}), \
             patch.object(server.agent, 'tasks', return_value=[]), \
             patch.object(server.agent, 'chat', side_effect=RuntimeError('Model unavailable')) as model:
            for body in [{'message': 'test'}, {'message': '', 'request_id': 'c' * 32}]:
                self.assertEqual(self.request('POST', '/api/chat', json.dumps(body), headers)[0], 400)
            model.assert_not_called()
            body = json.dumps({'message': 'test', 'request_id': 'c' * 32})
            self.assertEqual(self.request('POST', '/api/chat', body, headers)[0], 202)
            acquired = server.LOCK.acquire(timeout=3)
            if acquired: server.LOCK.release()
            self.assertTrue(acquired)
            state = json.loads(self.request('GET', '/api/state')[2])
            self.assertEqual(state['chat']['status'], 'failed')
            self.assertEqual(state['chat']['error'], 'Model unavailable')
            self.assertEqual(self.request('POST', '/api/new-chat', '{}', headers)[0], 200)

    def test_state_failure_returns_json(self):
        with patch.object(server, 'status', return_value={'ready': True}), \
             patch.object(server.agent, 'tasks', side_effect=OSError('Test database failure')):
            code, headers, body = self.request('GET', '/api/state')
        self.assertEqual(code, 500)
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertIn('Could not read demo state', json.loads(body)['error'])


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='foxrun-preview-start-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'demo').mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.processes = []
        self.addCleanup(self.stop_processes)
        popen = subprocess.Popen

        def spawn(*args, **kwargs):
            process = popen(*args, **kwargs)
            self.processes.append(process)
            return process

        for context in [patch.multiple(start, SOURCE=self.root, ROOT=self.root / 'runtime', PORT=self.port),
                        patch.dict(os.environ, PORT=str(self.port)),
                        patch.object(start.subprocess, 'Popen', side_effect=spawn)]:
            context.start()
            self.addCleanup(context.stop)

    def stop_processes(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)

    def test_alternate_port_start_and_second_start(self):
        # Use the real HTTP handler without starting installation or a model download.
        (self.root / 'demo/server.py').write_text(
            f'import sys\nsys.path.insert(0, {str(Path(server.__file__).parent)!r})\n'
            'from server import Handler, ThreadingHTTPServer, PORT\n'
            'ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()\n'
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(start.main(), 0)
            self.assertTrue(start.healthy())
            self.assertEqual(start.main(), 0)
        self.assertEqual(len(self.processes), 1)
        self.assertIn(f'http://127.0.0.1:{self.port}', output.getvalue())
        self.assertIn(f'already running on port {self.port}', output.getvalue())

    def test_failed_listener_is_reported(self):
        (self.root / 'demo/server.py').write_text('raise RuntimeError("Test listener failure")\n')
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(start.main(), 1)
        self.assertIn(f'did not become healthy on port {self.port}', error.getvalue())
        self.assertIn('Test listener failure', (self.root / 'runtime/server.log').read_text())


if __name__ == '__main__':
    unittest.main()
