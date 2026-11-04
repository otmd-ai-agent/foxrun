#!/usr/bin/env python3
"""Run Foxrun's existing session and handoff commands for OpenCode events."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys


def invoke(home, relative, arguments, payload):
    result = subprocess.run(
        [sys.executable, '-B', str(home / relative), *arguments],
        input=json.dumps(payload), text=True, capture_output=True, timeout=90,
        env=dict(os.environ, FOXRUN_HOME=str(home), PYTHONDONTWRITEBYTECODE='1'),
    )
    if result.returncode:
        raise RuntimeError(relative + ': ' + (result.stderr.strip() or result.stdout.strip()))
    return result.stdout


def handle(home, event, payload):
    if not isinstance(payload, dict):
        raise ValueError('OpenCode hook input must be a JSON object')
    session = payload.get('session_id')
    if not isinstance(session, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}', session):
        raise ValueError('OpenCode session ID is invalid')
    if not (home / 'config/person.json').is_file():
        return {'context': '', 'installed': False}
    payload = dict(payload, runtime='opencode')
    registry = home / 'config/threads.json'
    if registry.is_file():
        threads = json.loads(registry.read_text(encoding='utf-8')).get('threads', {})
        matches = [(key, row) for key, row in threads.items() if isinstance(row, dict)
                   and row.get('runtime') == 'opencode' and row.get('id') == session]
        if len(matches) > 1:
            raise ValueError('OpenCode session is registered to more than one Foxrun seat')
        if matches:
            key, row = matches[0]
            seat, separator, workspace = key.partition('@')
            if not separator or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', seat) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', workspace):
                raise ValueError('OpenCode thread has an invalid seat or workspace')
            if Path(row['cwd']).resolve() != Path(payload.get('cwd', '')).resolve():
                raise ValueError('OpenCode thread directory does not match its Foxrun workspace')
            payload.update(seat=seat, workspace=workspace)
    if event in ('start', 'after-compact'):
        payload['hook_event_name'] = 'SessionStart'
        payload['source'] = 'compact' if event == 'after-compact' else 'resume'
        if event == 'after-compact':
            raw = invoke(home, 'hooks/after_compact.py', ['opencode'], payload)
        else:
            arguments = ['start', '--runtime', 'opencode', '--session-id', session, '--hook-json']
            if payload.get('seat'):
                arguments += ['--seat', payload['seat'], '--workspace', payload['workspace']]
            raw = invoke(home, 'foxrun.py', arguments, payload)
            invoke(home, 'events/session_run.py', ['hook-start', '--runtime', 'opencode'], payload)
        return {'context': json.loads(raw)['hookSpecificOutput']['additionalContext'], 'installed': True}
    if payload.get('agent_id') and event in ('before-compact', 'idle'):
        # Child prompts come from another agent and cannot settle the person's work.
        if event == 'idle':
            payload['hook_event_name'] = 'SessionEnd'
            invoke(home, 'events/session_run.py', ['hook-end', '--runtime', 'opencode'], payload)
        return {'context': '', 'installed': True, 'handoff': None}
    if event in ('before-compact', 'idle'):
        payload.update(hook_event_name='PreCompact', trigger='auto' if event == 'before-compact' else 'turn-end')
        arguments = ['--json']
        if payload.get('seat'):
            arguments += ['--seat', payload['seat'], '--workspace', payload['workspace']]
        raw = invoke(home, 'hooks/write_handoff.py', arguments, payload)
        report = json.loads(raw) if raw.strip() else {}
        check = invoke(home, 'memory/before_compact.py', [], payload)
        parts = []
        if report.get('written'):
            parts.append('Foxrun handoff: ' + report['written'])
        if report.get('warning'):
            parts.append(report['warning'])
        if report.get('check_error'):
            parts.append('Foxrun settlement check: ' + report['check_error'])
        if check.strip():
            parts.append(check.strip())
        if event == 'idle':
            payload['hook_event_name'] = 'SessionEnd'
            invoke(home, 'events/session_run.py', ['hook-end', '--runtime', 'opencode'], payload)
        return {'context': '\n'.join(parts), 'installed': True, 'handoff': report.get('written')}
    if event == 'end':
        payload['hook_event_name'] = 'SessionEnd'
        invoke(home, 'events/session_run.py', ['hook-end', '--runtime', 'opencode'], payload)
        return {'context': '', 'installed': True}
    raise ValueError('Unknown OpenCode lifecycle event: ' + event)


def main():
    try:
        home = Path(os.environ.get('FOXRUN_HOME', str(Path(__file__).resolve().parents[2]))).resolve()
        print(json.dumps(handle(home, sys.argv[1], json.load(sys.stdin))))
        return 0
    except (ValueError, KeyError, IndexError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('Foxrun OpenCode hook failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
