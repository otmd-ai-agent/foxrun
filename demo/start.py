"""Start the demo and verify its listener before reporting success."""
import json
import subprocess
import sys
import time
import urllib.request
from settings import PORT, ROOT, SOURCE


def healthy():
    # A local health check must not use a proxy configured for external traffic.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{PORT}/api/health', timeout=2) as response:
            return json.load(response).get('application') == 'foxrun-demo'
    except (OSError, ValueError, AttributeError):
        return False


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    if healthy():
        print(f'Foxrun demo is already running on port {PORT}.')
        return 0
    log_path = ROOT / 'server.log'
    with log_path.open('a') as log:
        process = subprocess.Popen(
            [sys.executable, str(SOURCE / 'demo/server.py')],
            stdout=log, stderr=log, start_new_session=True,
        )
    deadline = time.monotonic() + 10
    while process.poll() is None and time.monotonic() < deadline:
        if healthy():
            print(f'Foxrun demo is running at http://127.0.0.1:{PORT}. Open its private port with Open in Browser.')
            print('First launch downloads a 5.15 GB local model; the page shows setup progress.')
            return 0
        time.sleep(0.2)
    print(f'Foxrun demo did not become healthy on port {PORT}. See {log_path}.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
