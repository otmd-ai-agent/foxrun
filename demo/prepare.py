"""Install Foxrun in isolated disposable folders and load a verified GGUF into DMR."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from settings import *


def report(stage, detail='', ready=False):
    tmp = ROOT / 'status.tmp'
    tmp.write_text(json.dumps({'stage': stage, 'detail': detail, 'ready': ready, 'model': MODEL}))
    tmp.replace(ROOT / 'status.json')


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    try:
        if not (SYSTEM / 'data.db').exists():
            report('Installing Foxrun', 'Creating an isolated visitor and demo workspace.')
            result = subprocess.run([sys.executable, str(SOURCE / 'install.py'), '--home', str(SYSTEM), '--portfolio', str(PORTFOLIO), '--runtime-home', str(ROOT / 'runtime'), '--yes', '--person', 'visitor', '--workspace', 'demo', '--runtime', 'codex', '--no-schedule'], capture_output=True, text=True)
            (ROOT / 'install.log').write_text(result.stdout + result.stderr)
            if result.returncode: raise RuntimeError('Foxrun installation failed. See ' + str(ROOT / 'install.log'))
        report('Checking Foxrun')
        result = subprocess.run([sys.executable, str(SYSTEM / 'foxrun.py'), 'doctor'], capture_output=True, text=True)
        (ROOT / 'doctor.log').write_text(result.stdout + result.stderr)
        if result.returncode: raise RuntimeError('Foxrun doctor failed. See doctor.log.')
        report('Connecting to Docker Model Runner')
        for attempt in range(60):
            try:
                with urllib.request.urlopen(MODEL_HOST + '/engines/status', timeout=3) as response:
                    json.load(response)
                break
            except OSError:
                if attempt == 59: raise
                time.sleep(2)
        env = dict(os.environ, MODEL_RUNNER_HOST=MODEL_HOST)
        dmr = os.environ.get('DMR_BIN', 'dmr')
        exists = subprocess.run([dmr, 'inspect', MODEL], env=env, capture_output=True).returncode == 0
        if not exists:
            model_file = ROOT / 'model.gguf'
            # For controlled local experiments, a previously downloaded file avoids another 5 GB transfer.
            supplied = os.environ.get('FOXRUN_DEMO_MODEL_FILE')
            if supplied: model_file = Path(supplied).resolve()
            if not model_file.exists():
                if shutil.disk_usage(ROOT).free < MODEL_BYTES + 1024**3: raise RuntimeError('Need at least 6.2 GB free for the model download, plus DMR storage.')
                report('Downloading Gemma', '0% · 5.15 GB · no API key needed')
                partial = ROOT / 'model.partial'
                with urllib.request.urlopen(MODEL_URL, timeout=60) as src, partial.open('wb') as out:
                    total = 0; last = -1
                    while chunk := src.read(4 * 1024**2):
                        out.write(chunk); total += len(chunk); pct = int(100 * total / MODEL_BYTES)
                        if pct != last: report('Downloading Gemma', f'{pct}% · {total / 1e9:.2f} / 5.15 GB'); last = pct
                partial.replace(model_file)
            report('Verifying model', 'Checking the pinned SHA-256 before loading it.')
            h = hashlib.sha256()
            with model_file.open('rb') as f:
                while chunk := f.read(8 * 1024**2): h.update(chunk)
            if h.hexdigest() != MODEL_SHA256: raise RuntimeError('Model checksum mismatch; delete the demo download and retry.')
            report('Loading model', 'Packaging the verified GGUF into Docker Model Runner.')
            with (ROOT / 'model-load.log').open('w') as log:
                subprocess.run([dmr, 'package', '--gguf', str(model_file), '--context-size', '4096', MODEL], env=env, stdout=log, stderr=log, check=True)
            if not supplied: model_file.unlink()  # only our verified temporary download; DMR owns its copy
        report('Ready', 'Local Gemma is ready. First inference may take longer while weights load.', True)
    except Exception as e:
        report('Setup failed', str(e))
        raise

if __name__ == '__main__': main()
