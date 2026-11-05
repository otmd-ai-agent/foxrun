"""Exercise cold and warm startup against a local Model Runner API fixture."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading
import unittest
import urllib.parse

import start


class ModelTransportTests(unittest.TestCase):
    def test_cold_and_warm_start_resolve_digest_configure_and_probe(self):
        state = {'cached': False, 'pulls': [], 'configs': [], 'probes': []}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, value, status=200):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = urllib.parse.unquote(self.path)
                if path == '/engines/status':
                    self.respond({})
                elif path == '/models/' + start.MODEL:
                    self.respond({'id': start.MODEL} if state['cached'] else {},
                                 200 if state['cached'] else 404)
                else:
                    self.respond({}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/models/create':
                    state['pulls'].append(body)
                    state['cached'] = True
                    self.respond({'status': 'complete'})
                elif self.path == '/engines/llama.cpp/_configure':
                    state['configs'].append(body)
                    self.respond({})
                elif self.path == '/engines/llama.cpp/v1/chat/completions':
                    state['probes'].append(body)
                    self.respond({'choices': [{'message': {'content': 'READY'}, 'finish_reason': 'stop'}]})
                else:
                    self.respond({}, 404)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {'MODEL_RUNNER_HOST': f'http://127.0.0.1:{server.server_port}'}
            with contextlib.redirect_stdout(io.StringIO()) as output:
                start.ensure_model(None, env)
                start.ensure_model(None, env)
            self.assertEqual(state['pulls'], [{'from': start.MODEL}])
            self.assertEqual(len(state['configs']), 2)
            self.assertEqual(len(state['probes']), 2)
            for config in state['configs']:
                self.assertEqual(config['model'], start.MODEL)
                self.assertEqual(config['context-size'], start.CONTEXT)
                self.assertIn('--jinja', config['runtime-flags'])
                self.assertIn('{"enable_thinking":false}', config['runtime-flags'])
            for probe in state['probes']:
                self.assertEqual(probe['model'], start.MODEL)
                self.assertEqual(probe['chat_template_kwargs'], {'enable_thinking': False})
            self.assertEqual(output.getvalue().count('"event": "model_ready"'), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
