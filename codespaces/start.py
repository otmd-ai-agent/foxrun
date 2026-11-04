"""Start OpenCode with the local model and Foxrun's onboarding skills."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
MODEL = 'foxrun/gemma4-e4b:qat-q4_0-32k'
MODEL_URL = 'https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/gemma-4-E4B_q4_0-it.gguf'
MODEL_SHA256 = '676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee'
MODEL_BYTES = 5154941280
CONTEXT = 32768
OPENCODE_VERSION = '1.19.5'


def settings():
    state = Path(os.environ.get('FOXRUN_CODESPACES_STATE', '/workspaces/foxrun-state')).resolve()
    return state, int(os.environ.get('PORT', '8081'))


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def password(state):
    path = state / 'server-password'
    if path.is_symlink():
        raise RuntimeError('The server password file must not be a symlink.')
    if not path.exists():
        with open(path, 'x', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            stream.write(secrets.token_urlsafe(32) + '\n')
    if path.stat().st_mode & 0o077:
        raise RuntimeError('Restrict server-password to its owner with chmod 600 before starting.')
    value = path.read_text().strip()
    if not value:
        raise RuntimeError('The server password file is empty.')
    return value


def environment(state, port, secret):
    env = dict(os.environ)
    env.update({
        'FOXRUN_HOME': str(state / 'system'),
        'FOXRUN_PORTFOLIO': str(state / 'portfolio'),
        'FOXRUN_PRODUCT_SOURCE': str(SOURCE),
        'FOXRUN_EPHEMERAL': '1',
        'FOXRUN_OPENCODE_URL': f'http://127.0.0.1:{port}',
        'FOXRUN_OPENCODE_MODEL': 'dmr/' + MODEL,
        'FOXRUN_OPENCODE_TRANSCRIPTS': str(state / 'transcripts'),
        'OPENCODE_CONFIG_DIR': str(state / 'opencode-config'),
        'XDG_DATA_HOME': str(state / 'data'),
        'XDG_STATE_HOME': str(state / 'state'),
        'XDG_CACHE_HOME': str(state / 'cache'),
        'OPENCODE_SERVER_USERNAME': 'opencode',
        'OPENCODE_SERVER_PASSWORD': secret,
        'BROWSER': '/bin/true',
    })
    return env


def prepare_user_home(state, user_home=None):
    """Create default-path aliases only in this Codespace's declared account home."""
    expected = state / 'user'
    selected = Path.home() if user_home is None else Path(user_home)
    if selected != expected or expected.is_symlink():
        raise RuntimeError(
            'Codespaces startup requires the container account home at ' + str(expected) +
            '. Rebuild the devcontainer. Startup will not change your current home.'
        )
    aliases = {'.foxrun': state / 'system', 'foxrun': state / 'portfolio'}
    # Check both entries before creating either, so a conflict leaves them untouched.
    for name, target in aliases.items():
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise RuntimeError('Foxrun target must be a directory inside the state volume: ' + str(target))
        path = expected / name
        if path.is_symlink():
            if path.resolve() != target.resolve():
                raise RuntimeError('Conflicting Foxrun alias: ' + str(path))
        elif path.exists():
            raise RuntimeError('Foxrun alias would replace an existing path: ' + str(path))
    expected.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, target in aliases.items():
        path = expected / name
        if not path.is_symlink():
            path.symlink_to(target, target_is_directory=True)
    return expected


def configure(state, port, env, user_home=None):
    prepare_user_home(state, user_home)
    config_dir = Path(env['OPENCODE_CONFIG_DIR'])
    config_dir.mkdir(parents=True, exist_ok=True)
    launch = state / 'launch'
    launch.mkdir(exist_ok=True)
    # Bootstrap skills stay in this project; installation owns the runtime shelf.
    for name in ('foxrun-setup', 'thread', 'foxrun-help'):
        target = launch / '.opencode' / 'skills' / name
        shutil.copytree(SOURCE / 'plugins' / 'foxrun' / 'skills' / name, target, dirs_exist_ok=True)
    (launch / 'AGENTS.md').write_text(
        '# Foxrun onboarding\n\n'
        'Use the foxrun-setup skill to install and configure Foxrun. Ask for the person\'s name '
        'and first workspace; do not invent them. This Codespace uses OpenCode and a local '
        'Docker Model Runner model. Install from FOXRUN_PRODUCT_SOURCE with --runtime opencode. '
        'FOXRUN_HOME and FOXRUN_PORTFOLIO name persistent locations.\n\n'
        'After setup, continue in the chosen portfolio workspace. Read its AGENTS.md and '
        'the installed Foxrun global contract. Use the actual Foxrun commands and skills.\n'
    )
    path = config_dir / 'opencode.json'
    config = json.loads(path.read_text()) if path.exists() else {}
    # These settings belong to the local Codespaces integration. Keep other keys,
    # including the plugin list written by Foxrun's hookup command.
    config.update({
        '$schema': 'https://opencode.ai/config.json',
        'autoupdate': False,
        'enabled_providers': ['dmr'],
        'model': 'dmr/' + MODEL,
        'small_model': 'dmr/' + MODEL,
        'share': 'disabled',
        'server': {'hostname': '0.0.0.0', 'port': port},
    })
    config.setdefault('provider', {})['dmr'] = {
        'npm': '@ai-sdk/openai-compatible',
        'name': 'Docker Model Runner',
        'options': {'baseURL': env.get('MODEL_RUNNER_HOST', 'http://model-runner:12434').rstrip('/') + '/engines/v1',
                    'timeout': 1800000},
        'models': {MODEL: {'name': 'Local Gemma 4 E4B', 'tool_call': True,
                           'limit': {'context': CONTEXT, 'output': 4096}}},
    }
    source_plugin = (SOURCE / 'hooks/opencode/foxrun.mjs').as_uri()
    installed_plugin = (state / 'system/hooks/opencode/foxrun.mjs').as_uri()
    plugins = config.setdefault('plugin', [])
    if installed_plugin in plugins:
        config['plugin'] = [item for item in plugins if item != source_plugin]
    elif source_plugin not in plugins:
        plugins.append(source_plugin)
    config.setdefault('command', {})['foxrun-setup'] = {
        'description': 'Set up Foxrun with your name and workspace',
        'template': 'Load the foxrun-setup skill and complete its onboarding steps. '
                    'Use the local source in FOXRUN_PRODUCT_SOURCE and runtime opencode.',
    }
    write_json(path, config)
    return launch


def local_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def healthy(port, secret):
    credentials = base64.b64encode(('opencode:' + secret).encode()).decode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}/global/health',
                                 headers={'Authorization': 'Basic ' + credentials})
    try:
        with local_opener().open(req, timeout=2) as response:
            data = json.load(response)
        return data.get('healthy') is True and data.get('version') == OPENCODE_VERSION
    except (OSError, ValueError, AttributeError):
        return False


def ensure_model(state, env):
    host = env.get('MODEL_RUNNER_HOST', 'http://model-runner:12434').rstrip('/')
    for attempt in range(60):
        try:
            with local_opener().open(host + '/engines/status', timeout=3) as response:
                json.load(response)
            break
        except OSError:
            if attempt == 59:
                raise RuntimeError('Docker Model Runner did not become ready.')
            time.sleep(2)
    dmr = env.get('DMR_BIN', 'dmr')
    if subprocess.run([dmr, 'inspect', MODEL], env=env, capture_output=True).returncode == 0:
        return
    supplied = env.get('FOXRUN_MODEL_FILE')
    model_file = Path(supplied).resolve() if supplied else state / 'model.gguf'
    if not model_file.exists():
        if supplied:
            raise RuntimeError('FOXRUN_MODEL_FILE does not exist.')
        if shutil.disk_usage(state).free < 2 * MODEL_BYTES + 1024**3:
            raise RuntimeError('Model setup needs at least 11.4 GB free for the download and DMR copy.')
        print('Downloading the pinned local Gemma model (5.15 GB).', flush=True)
        partial = state / 'model.partial'
        with urllib.request.urlopen(MODEL_URL, timeout=120) as src, partial.open('wb') as out:
            total, reported = 0, -1
            while chunk := src.read(4 * 1024**2):
                out.write(chunk)
                total += len(chunk)
                percent = int(100 * total / MODEL_BYTES)
                if percent // 10 != reported:
                    print(f'Model download: {percent}%.', flush=True)
                    reported = percent // 10
        partial.replace(model_file)
    digest = hashlib.sha256()
    with model_file.open('rb') as stream:
        while chunk := stream.read(8 * 1024**2):
            digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError('Model checksum mismatch. Remove the incomplete download and retry.')
    print('Loading the verified model into Docker Model Runner.', flush=True)
    with (state / 'model-load.log').open('a') as log:
        subprocess.run([dmr, 'package', '--gguf', str(model_file), '--context-size', str(CONTEXT), MODEL],
                       env=env, stdout=log, stderr=log, check=True)
    if not supplied:
        model_file.unlink()


def start(state, port, user_home=None):
    secret = password(state)
    env = environment(state, port, secret)
    launch = configure(state, port, env, user_home=user_home)
    if healthy(port, secret):
        print(f'OpenCode is already running on port {port}.')
        return
    with socket.socket() as probe:
        try:
            probe.bind(('0.0.0.0', port))
        except OSError as error:
            raise RuntimeError(f'Port {port} is occupied by another process; OpenCode was not started.') from error
    binary = env.get('OPENCODE_BIN', 'opencode')
    version = subprocess.check_output([binary, '--version'], text=True, env=env).strip()
    if version != OPENCODE_VERSION:
        raise RuntimeError(f'Expected OpenCode {OPENCODE_VERSION}, found {version}. Rebuild the container.')
    ensure_model(state, env)
    with (state / 'opencode.log').open('a') as log:
        process = subprocess.Popen([binary, 'web', '--hostname', '0.0.0.0', '--port', str(port)],
                                   cwd=launch, env=env, stdout=log, stderr=log, start_new_session=True)
    (state / 'opencode.pid').write_text(str(process.pid) + '\n')
    for _ in range(150):
        if healthy(port, secret):
            print(f'OpenCode is ready on private port {port}. Open it in your browser.')
            print('Username: opencode. Show your password with: python3 codespaces/start.py --password')
            print('In OpenCode, open the launch project and run /foxrun-setup.')
            return
        if process.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError(f'OpenCode did not become ready. Read {state / "opencode.log"}.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--password', action='store_true', help='show your private OpenCode browser password')
    parser.add_argument('--configure-only', action='store_true', help='prepare local configuration without starting services')
    args = parser.parse_args()
    state, port = settings()
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'startup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.password:
            print(password(state))
        elif args.configure_only:
            configure(state, port, environment(state, port, password(state)))
        else:
            start(state, port)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
