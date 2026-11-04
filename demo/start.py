"""Idempotent devcontainer startup: serve immediately, prepare in the background."""
import json
import subprocess
import sys
import time
import urllib.request
from settings import ROOT, SOURCE

ROOT.mkdir(parents=True, exist_ok=True)
try:
    with urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2) as r:
        if json.load(r).get('application') == 'foxrun-demo':
            print('Foxrun demo is already running on port 8080.'); sys.exit(0)
except (OSError, ValueError):
    pass
log = (ROOT / 'server.log').open('a')
subprocess.Popen([sys.executable, str(SOURCE / 'demo/server.py')], stdout=log, stderr=log, start_new_session=True)
print('Foxrun demo starting on port 8080. First launch downloads a 5.15 GB local model.')
