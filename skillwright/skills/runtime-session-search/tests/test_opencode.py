"""Read-only native OpenCode API fixtures; no model calls or session writes."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.parse
from tests.support import search, stores


class OpenCodeSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.calls, self.status = [], 200
        self.sessions = [
            {'id': 'ses_TestAlpha', 'title': 'Workspace planning', 'directory': str(self.root), 'time': {'updated': time.time() * 1000}},
            {'id': 'ses_TestBeta', 'title': 'Older discussion', 'directory': str(self.root), 'time': {'updated': 1}},
        ]
        self.messages = [
            {'info': {'role': 'assistant', 'time': {'created': 3}}, 'parts': [
                {'type': 'reasoning', 'text': 'PRIVATE_REASONING_TOKEN'},
                {'type': 'tool', 'state': {'output': 'PRIVATE_TOOL_TOKEN'}},
                {'type': 'text', 'text': 'The sample checklist is ready.'}]},
            {'info': {'role': 'user', 'time': {'created': 2}}, 'parts': [{'type': 'text', 'text': 'Write a sample checklist.'}]},
            {'info': {'role': 'assistant', 'time': {'created': 1}}, 'parts': [{'type': 'text', 'text': 'An older reply.'}]},
        ]
        case = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                case.calls.append((self.command, self.path, self.headers.get('Authorization')))
                path = urllib.parse.urlsplit(self.path).path
                if case.status != 200:
                    self.send_response(case.status)
                    self.end_headers()
                    return
                body = case.sessions if path == '/session' else case.messages if path.endswith('/message') else next(
                    (row for row in case.sessions if path == '/session/' + row['id']), None)
                self.send_response(200 if body is not None else 404)
                self.end_headers()
                if body is not None:
                    self.wfile.write(json.dumps(body).encode())
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        environment = patch.dict(os.environ, {'FOXRUN_OPENCODE_URL': 'http://127.0.0.1:' + str(self.server.server_port),
            'FOXRUN_OPENCODE_DIRECTORY': str(self.root), 'FOXRUN_PORTFOLIO': str(self.root / 'portfolio'),
            'OPENCODE_SERVER_PASSWORD': 'labeled-fixture-password'})
        environment.start()
        self.addCleanup(environment.stop)

    def find(self, query):
        return search.find(query, stores=stores, stores_root=self.root, runtime='opencode', memex='off')

    def test_words_and_credentials(self):
        result = self.find('sample checklist')
        self.assertEqual(result['status'], 'found')
        self.assertEqual([hit['session_id'] for hit in result['hits']], ['ses_TestAlpha'])
        self.assertIn('opencode attach', result['hits'][0]['attach_or_resume_cmd'])
        self.assertIn('--dir', result['hits'][0]['attach_or_resume_cmd'])
        for method, path, auth in self.calls:
            self.assertEqual(method, 'GET')
            self.assertEqual(auth, 'Basic ' + base64.b64encode(b'opencode:labeled-fixture-password').decode())
        self.assertEqual(self.find('PRIVATE_REASONING_TOKEN')['status'], 'not_found')
        self.assertEqual(self.find('PRIVATE_TOOL_TOKEN')['status'], 'not_found')

    def test_id_search_ignores_age_and_distinguishes_case(self):
        result = self.find('ses_Test')
        self.assertEqual((result['status'], result['query_kind']), ('choice_required', 'id'))
        self.assertEqual({hit['session_id'] for hit in result['hits']}, {'ses_TestAlpha', 'ses_TestBeta'})
        self.assertEqual(self.find('ses_TestBeta')['hits'][0]['session_id'], 'ses_TestBeta')
        self.assertEqual(self.find('ses_testBeta')['status'], 'not_found')

    def test_latest_visible_reply_and_exact_id_read(self):
        result = search.read('ses_TestAlpha', stores=stores, stores_root=self.root, runtime='opencode')
        self.assertEqual(result['status'], 'read')
        self.assertEqual(result['task_success'], 'not_inferred')
        self.assertIn('The sample checklist is ready.', result['text'])
        self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertNotIn('An older reply.', result['text'])
        self.assertIn('--session ses_TestAlpha', result['resume_with'])
        self.assertIn('--dir', result['resume_with'])
        self.assertEqual(search.read('ses_Test', stores=stores, stores_root=self.root, runtime='opencode')['status'], 'not_found')

    def test_budget_exhaustion_reports_incomplete_results(self):
        hits, notes = stores.opencode_hits('checklist', {}, self.root, budget_seconds=0)
        self.assertEqual(hits, [])
        self.assertIn('results may be incomplete', notes[0])
        self.assertEqual(self.calls, [])

    def test_read_output_stays_bounded(self):
        self.messages[0]['parts'].append({'type': 'text', 'text': 'Long visible text. ' * 10000})
        result = search.read('ses_TestAlpha', stores=stores, stores_root=self.root, runtime='opencode')
        self.assertLessEqual(len(result['text'].encode()), stores.MAX_READ_BYTES)
        self.assertNotIn('PRIVATE_REASONING_TOKEN', result['text'])

    def test_server_error_is_explicit(self):
        self.status = 503
        self.assertIn('HTTP 503', self.find('checklist')['adapter_notes'][0])
        with self.assertRaisesRegex(stores.StoreError, 'HTTP 503'):
            search.read('ses_TestAlpha', stores=stores, stores_root=self.root, runtime='opencode')


if __name__ == '__main__':
    unittest.main()
