"""Single-visitor Codespaces demo UI. Keep the forwarded port private."""
import json
import re
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from settings import *
import agent

LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
HISTORY = []
EVENTS = []
JOBS = {}
CURRENT_JOB = None


def status():
    try:
        return json.loads((ROOT / 'status.json').read_text())
    except (OSError, ValueError):
        return {'stage': 'Starting', 'detail': 'Preparing the disposable demo.', 'ready': False, 'model': MODEL}


def record_event(event):
    with STATE_LOCK:
        EVENTS.append(event)


def run_chat(job):
    try:
        result = agent.chat(job['message'], HISTORY, record_event)
        with STATE_LOCK:
            job.update(status='complete', result=result)
    except Exception as error:
        traceback.print_exc()
        with STATE_LOCK:
            job.update(status='failed', error=str(error) or type(error).__name__)
    finally:
        LOCK.release()


class Handler(BaseHTTPRequestHandler):
    def send_body(self, body, content_type, code=200, extra_headers=None):
        try:
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # A disconnected visitor can recover the job through the state endpoint.
            self.log_message('Client disconnected while reading %s', self.path)

    def reply(self, data, code=200):
        self.send_body(json.dumps(data).encode(), 'application/json', code)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.reply({'application': 'foxrun-demo'})
        if path == '/api/state':
            try:
                setup = status()
                rows = agent.tasks() if setup.get('ready') else []
                with STATE_LOCK:
                    snapshot = {'setup': setup, 'tasks': rows, 'events': EVENTS[-12:],
                                'chat': dict(JOBS[CURRENT_JOB]) if CURRENT_JOB else None}
                return self.reply(snapshot)
            except Exception:
                traceback.print_exc()
                return self.reply({'error': 'Could not read demo state. Check server.log in the Codespaces terminal.'}, 500)
        if path != '/':
            return self.reply({'error': 'Not found'}, 404)
        body = (SOURCE / 'demo/index.html').read_bytes()
        policy = ("default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                  "connect-src 'self'; frame-ancestors 'self' https://*.github.dev https://github.dev "
                  "https://*.vscode-cdn.net https://*.vscode-webview.net; base-uri 'none'")
        self.send_body(body, 'text/html; charset=utf-8', extra_headers={'Content-Security-Policy': policy})

    def start_chat(self, body):
        global CURRENT_JOB
        text = body.get('message')
        ident = body.get('request_id')
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            return self.reply({'error': 'Enter 1–2000 characters.'}, 400)
        if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{32}', ident):
            return self.reply({'error': 'Missing chat request ID. Reload the page and try again.'}, 400)
        with STATE_LOCK:
            previous = JOBS.get(ident)
            if previous:
                snapshot = dict(previous)
            else:
                snapshot = None
        if snapshot:
            if snapshot['message'] != text:
                return self.reply({'error': 'This request ID belongs to a different message.'}, 409)
            return self.reply(snapshot, 202 if snapshot['status'] == 'running' else 200)
        if not LOCK.acquire(blocking=False):
            return self.reply({'error': 'A request is already running. Wait for it to finish.'}, 409)
        # Another request may have completed between the first lookup and lock acquisition.
        with STATE_LOCK:
            previous = JOBS.get(ident)
            snapshot = dict(previous) if previous else None
        if snapshot:
            LOCK.release()
            if snapshot['message'] != text:
                return self.reply({'error': 'This request ID belongs to a different message.'}, 409)
            return self.reply(snapshot, 202 if snapshot['status'] == 'running' else 200)
        try:
            with STATE_LOCK:
                job = {'id': ident, 'message': text, 'status': 'running'}
                JOBS[ident] = job
                CURRENT_JOB = ident
                # Retain recent request IDs so a repeated submission does not repeat tool calls.
                while len(JOBS) > 20:
                    del JOBS[next(iter(JOBS))]
                snapshot = dict(job)
            threading.Thread(target=run_chat, args=(job,), daemon=True).start()
        except Exception:
            with STATE_LOCK:
                JOBS.pop(ident, None)
                CURRENT_JOB = None
            LOCK.release()
            traceback.print_exc()
            return self.reply({'error': 'Could not start the model request.'}, 500)
        return self.reply(snapshot, 202)

    def do_POST(self):
        global CURRENT_JOB
        # Cross-origin forms cannot supply this header; we grant no CORS preflight.
        if self.headers.get('X-Foxrun-Demo') != '1' or self.headers.get('Content-Type') != 'application/json':
            return self.reply({'error': 'Expected a same-site JSON request'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 12000:
                raise ValueError('Request too large or empty')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('Expected JSON object')
        except ValueError as error:
            return self.reply({'error': str(error)}, 400)
        if not status().get('ready'):
            return self.reply({'error': 'Setup is not ready yet.'}, 503)
        path = urlsplit(self.path).path
        if path == '/api/chat':
            return self.start_chat(body)
        if not LOCK.acquire(blocking=False):
            return self.reply({'error': 'A request is already running. Wait for it to finish.'}, 409)
        try:
            if path == '/api/new-chat':
                HISTORY.clear()
                with STATE_LOCK:
                    CURRENT_JOB = None
                result = {'ok': True}
            elif path == '/api/accept':
                ident = agent.task_id(body.get('task_id'))
                if body.get('reviewed') is not True:
                    raise ValueError('Read the proof before accepting.')
                result = agent.work('accept', ident, '--by', 'visitor')
                record_event({'tool': 'human_accept', 'result': result})
            else:
                return self.reply({'error': 'Not found'}, 404)
            self.reply(result)
        except Exception as error:
            traceback.print_exc()
            self.reply({'error': str(error)}, 400)
        finally:
            LOCK.release()


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    # Bind first: an occupied port must not start a second preparation process.
    httpd = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    with (ROOT / 'prepare.log').open('a') as log:
        subprocess.Popen([sys.executable, str(SOURCE / 'demo/prepare.py')], stdout=log, stderr=log)
    httpd.serve_forever()


if __name__ == '__main__':
    main()
