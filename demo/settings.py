"""Pinned local demo configuration. No model API key is read or required."""
import os
from pathlib import Path
SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('FOXRUN_DEMO_ROOT', '/tmp/foxrun-demo')).resolve()
SYSTEM = ROOT / 'system'
PORTFOLIO = ROOT / 'portfolio'
WORKSPACE = PORTFOLIO / 'demo'
MODEL_HOST = os.environ.get('MODEL_RUNNER_HOST', 'http://model-runner:12434').rstrip('/')
MODEL = 'foxrun-demo/gemma4-e4b:qat-q4_0'
MODEL_URL = 'https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/gemma-4-E4B_q4_0-it.gguf'
MODEL_SHA256 = '676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee'
MODEL_BYTES = 5154941280
