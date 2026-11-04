"""Check the real OpenCode host and Foxrun lifecycle with a local model fixture.

This check installs Foxrun in temporary folders and runs the pinned OpenCode
binary. Its deterministic HTTP fixture does not test Gemma inference quality,
Docker Model Runner, Codespaces forwarding, or automatic browser launch.
"""
import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shlex
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

import start


REPLY = 'Foxrun lifecycle fixture response.'


class LocalModel(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.requests.append(request)
        usage = {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}
        if request.get('stream'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for delta, finish in (({'role': 'assistant', 'content': REPLY}, None), ({}, 'stop')):
                event = {'id': 'chatcmpl-fixture', 'object': 'chat.completion.chunk', 'created': 1,
                         'model': start.MODEL, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
                if finish:
                    event['usage'] = usage
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
        else:
            data = json.dumps({'id': 'chatcmpl-fixture', 'object': 'chat.completion', 'model': start.MODEL,
                               'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': REPLY},
                                            'finish_reason': 'stop'}], 'usage': usage}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)


def wait_for(check, message, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.2)
    raise AssertionError(message)


def run(binary, state):
    with socket.socket() as unused:
        unused.bind(('127.0.0.1', 0))
        port = unused.getsockname()[1]
    secret = start.password(state)
    env = start.environment(state, port, secret)
    # No inherited runtime selector may direct this test at a real agent home.
    for key in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'OPENCODE_CONFIG', 'OPENCODE_CONFIG_CONTENT'):
        env.pop(key, None)
    env['XDG_CONFIG_HOME'] = str(state / 'xdg-config')
    env['OPENCODE_BIN'] = binary
    user_home = state / 'user'
    launch = start.configure(state, port, env, user_home=user_home)
    model = ThreadingHTTPServer(('127.0.0.1', 0), LocalModel)
    LocalModel.requests = []
    threading.Thread(target=model.serve_forever, daemon=True).start()
    config_path = Path(env['OPENCODE_CONFIG_DIR']) / 'opencode.json'
    config = json.loads(config_path.read_text())
    config['provider']['dmr']['options']['baseURL'] = f'http://127.0.0.1:{model.server_port}/v1'
    start.write_json(config_path, config)
    credentials = 'Basic ' + base64.b64encode(('opencode:' + secret).encode()).decode()

    def api(path, body=None, directory=None):
        query = '?' + urllib.parse.urlencode({'directory': str(directory)}) if directory else ''
        req = urllib.request.Request(f'http://127.0.0.1:{port}{path}{query}',
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Authorization': credentials, 'Content-Type': 'application/json'})
        with start.local_opener().open(req, timeout=90) as response:
            return json.load(response)

    def command(arguments):
        result = subprocess.run(arguments, env=env, cwd=start.SOURCE, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise AssertionError('Command failed: ' + ' '.join(arguments) + '\n' + result.stdout[-2000:] + result.stderr[-2000:])
        return result.stdout

    process = None
    try:
        assert command([binary, '--version']).strip() == start.OPENCODE_VERSION
        with (state / 'opencode.log').open('w') as log:
            process = subprocess.Popen([binary, 'web', '--hostname', '127.0.0.1', '--port', str(port)],
                                       cwd=launch, env=env, stdout=log, stderr=log)
        wait_for(lambda: start.healthy(port, secret), 'OpenCode did not start')
        assert {'foxrun-setup', 'thread', 'foxrun-help'} <= {item['name'] for item in api('/skill')}
        api('/session', {'title': 'Bootstrap fixture'})
        print('PASS native server and bootstrap skill discovery')

        system, portfolio = state / 'system', state / 'portfolio'
        command(['python3', str(start.SOURCE / 'install.py'), '--home', str(system), '--portfolio', str(portfolio),
                 '--runtime-home', str(config_path.parent), '--runtime', 'opencode', '--person', 'integration',
                 '--workspace', 'trial', '--yes', '--no-schedule'])
        assert 'Doctor: 0 failed' in command(['python3', str(system / 'foxrun.py'), 'doctor'])
        assert 'Doctor: 0 failed' in command(['python3', str(user_home / '.foxrun/foxrun.py'), 'doctor'])
        assert (user_home / 'foxrun/trial/AGENTS.md').samefile(portfolio / 'trial/AGENTS.md')
        print('PASS default product-path aliases reach the actual installation')
        command(['python3', str(system / 'foxrun.py'), 'hookup', '--runtime', 'opencode',
                 '--runtime-home', str(config_path.parent)])
        assert 'Nothing changed.' in command(['python3', str(system / 'foxrun.py'), 'hookup', '--runtime', 'opencode',
                                              '--runtime-home', str(config_path.parent)])
        api('/instance/dispose', {})
        workspace = portfolio / 'trial'
        skills = api('/skill', directory=workspace)
        names = {item['name'] for item in skills}
        assert {'foxrun-setup', 'thread', 'task', 'checkpoint', 'handoff', 'orchestrate'} <= names
        print(f'PASS installer, doctor, idempotent hookup, and {len(skills)} discovered skills')

        sid = api('/session', {'title': 'Native lifecycle fixture'}, workspace)['id']
        message = {'model': {'providerID': 'dmr', 'modelID': start.MODEL},
                   'parts': [{'type': 'text', 'text': 'Reply with one sentence for this lifecycle fixture.'}]}
        reply = api(f'/session/{sid}/message', message, workspace)
        assert REPLY in [part.get('text') for part in reply.get('parts', []) if part.get('type') == 'text']
        transcript = state / 'transcripts' / f'{sid}.jsonl'
        wait_for(transcript.exists, 'The native idle hook did not export a transcript')
        assert transcript.stat().st_mode & 0o777 == 0o600

        def ended():
            with sqlite3.connect(system / 'data.db') as db:
                return db.execute('SELECT COUNT(*) FROM runs WHERE runtime=? AND session=? AND ended_at IS NOT NULL',
                                  ('opencode', sid)).fetchone()[0] > 0

        wait_for(ended, 'The native idle hook did not close its run')
        contexts = [str(msg.get('content', '')) for request in LocalModel.requests
                    for msg in request.get('messages', []) if msg.get('role') == 'system']
        assert any('Person: integration' in content for content in contexts)
        assert any('opencode=dmr/' + start.MODEL in content for content in contexts), \
            'The start page did not identify the configured local OpenCode model'
        handoffs = workspace / 'history/handoffs'
        wait_for(lambda: bool(list(handoffs.glob('*-precompact.md'))), 'The idle handoff was not saved')
        print('PASS native start, idle, private transcript, run record, and handoff')

        shell_code = (
            "import os, subprocess; "
            + "assert os.environ['FOXRUN_HOME'] == " + repr(str(system)) + "; "
            + "subprocess.run(['python3', " + repr(str(user_home / '.foxrun/foxrun.py'))
            + ", 'doctor'], check=True)"
        )
        shell_result = api(f'/session/{sid}/shell',
                           {'agent': 'build', 'command': shlex.join(['python3', '-c', shell_code])}, workspace)
        assert 'Doctor: 0 failed' in json.dumps(shell_result)
        print('PASS native shell environment and default product-path command')

        api(f'/session/{sid}/summarize', {'providerID': 'dmr', 'modelID': start.MODEL}, workspace)
        reply = api(f'/session/{sid}/message', message, workspace)
        assert REPLY in [part.get('text') for part in reply.get('parts', []) if part.get('type') == 'text']
        wait_for(ended, 'The post-compaction turn did not settle')
        api('/instance/dispose', {}, workspace)
        sid2 = api('/session', {'title': 'Reload lifecycle fixture'}, workspace)['id']
        api(f'/session/{sid2}/message', message, workspace)
        wait_for(lambda: (state / 'transcripts' / f'{sid2}.jsonl').exists(), 'Hooks did not reload after instance disposal')
        print('PASS native compaction, next turn, and plugin reload')
        first = LocalModel.requests[0]
        print('Initial request characters: messages=' + str(len(json.dumps(first.get('messages', [])))) +
              ', tools=' + str(len(json.dumps(first.get('tools', [])))))
        print('Model responses came from a deterministic local fixture; no Gemma inference was tested.')
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=15)
        model.shutdown()
        model.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opencode', default=os.environ.get('OPENCODE_BIN', 'opencode'),
                        help='path to the pinned OpenCode binary')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='foxrun-opencode-integration-') as temporary:
        run(args.opencode, Path(temporary))


if __name__ == '__main__':
    main()
