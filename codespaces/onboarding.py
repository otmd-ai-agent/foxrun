"""Run the real installer or doctor, retaining full logs outside model context."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(command, log_dir, structured=False):
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w+', prefix='setup-', suffix='.log', dir=log_dir,
                                     delete=False) as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True)
        log.seek(0)
        lines = log.read().splitlines()
        summary = [line for line in lines if line.startswith(('Doctor:', 'FAIL', 'ERROR', 'Error:'))]
        response = {'ok': result.returncode == 0, 'exit_code': result.returncode,
                    'summary': summary[-20:], 'log': log.name}
        if structured and result.returncode == 0:
            response['result'] = json.loads('\n'.join(lines))
        if result.returncode:
            response['error_tail'] = '\n'.join(lines[-15:])[-4000:]
        print(json.dumps(response, ensure_ascii=False))
        return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'doctor', 'status', 'plan', 'make', 'memory'))
    parser.add_argument('--person')
    parser.add_argument('--workspace')
    parser.add_argument('--seat')
    parser.add_argument('--emoji')
    parser.add_argument('--part', choices=('questions', 'threads', 'hooks', 'backup'))
    args = parser.parse_args()
    state = Path(os.environ.get('FOXRUN_CODESPACES_STATE', '/workspaces/foxrun-state'))
    home = Path(os.environ.get('FOXRUN_HOME', str(state / 'system')))
    source = Path(__file__).resolve().parents[1]
    if args.action == 'install':
        if not args.person or not args.workspace:
            parser.error('install requires --person and --workspace')
        command = [sys.executable, str(source / 'install.py'), '--home', str(home),
                   '--portfolio', os.environ.get('FOXRUN_PORTFOLIO', str(state / 'portfolio')),
                   '--runtime-home', os.environ.get('OPENCODE_CONFIG_DIR', str(state / 'opencode-config')),
                   '--runtime', 'opencode', '--person', args.person, '--workspace', args.workspace,
                   '--yes', '--no-schedule']
    elif args.action == 'doctor':
        command = [sys.executable, str(home / 'foxrun.py'), 'doctor']
    elif args.action == 'status':
        if not (home / 'foxrun.py').exists():
            print(json.dumps({'installed': False, 'next': 'Ask for first name, then workspace.'}))
            return 0
        command = [sys.executable, str(home / 'skills/foxrun-setup/bin/setup'), 'status']
        if args.part:
            command += ['--part', args.part]
    elif args.action in ('plan', 'make'):
        if not args.seat or not args.workspace:
            parser.error('plan and make require --seat and --workspace')
        target = ['lead', args.workspace] if args.seat == 'lead' else [args.seat]
        command = [sys.executable, str(home / 'skills/thread/bin/thread'), args.action, *target,
                   '--runtime', 'opencode', '--workspace', args.workspace]
        if args.emoji:
            command += ['--emoji', args.emoji]
    else:
        command = [sys.executable, str(home / 'skills/foxrun-setup/bin/setup'), 'hooks', '--answer', 'yes']
    return run(command, state / 'setup-logs', structured=args.action in ('status', 'plan', 'make', 'memory'))


if __name__ == '__main__':
    raise SystemExit(main())
