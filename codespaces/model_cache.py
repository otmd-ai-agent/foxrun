"""Download and verify the pinned model while building the devcontainer image."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request

MODEL_URL = 'https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/gemma-4-E4B_q4_0-it.gguf'
MODEL_SHA256 = '676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee'
MODEL_BYTES = 5154941280
CACHED_MODEL = Path('/opt/foxrun-model/model.gguf')


def verify(path):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError('Cached model is missing. Rebuild the devcontainer image: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024**2):
            digest.update(chunk)
    if path.stat().st_size != MODEL_BYTES or digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError('Model checksum mismatch or incorrect size: ' + str(path))
    return path


def require_space(path, operation):
    available = shutil.disk_usage(path).free
    required = MODEL_BYTES + 1024**3
    if available < required:
        raise RuntimeError(
            f'{operation} needs {required / 1e9:.2f} GB free; '
            f'{available / 1e9:.2f} GB is available on {path}. '
            'Free space on this Codespace, or choose a larger machine if your account offers one, then retry.'
        )


def prepare(path=CACHED_MODEL):
    path = Path(path)
    if path.exists():
        verify(path)
        print('Using the verified model already in the image cache.', flush=True)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    require_space(path.parent, 'Image model cache')
    partial = path.with_suffix('.partial')
    print('Downloading the pinned model into the image cache (5.15 GB).', flush=True)
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=120) as source, partial.open('wb') as output:
            total, reported = 0, -1
            while chunk := source.read(4 * 1024**2):
                output.write(chunk)
                total += len(chunk)
                if total > MODEL_BYTES:
                    raise RuntimeError('Model download exceeds the pinned size.')
                percent = int(100 * total / MODEL_BYTES)
                if percent // 10 != reported:
                    print(f'Model download: {percent}%.', flush=True)
                    reported = percent // 10
        verify(partial)
        partial.chmod(0o444)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    print('Verified model saved in the devcontainer image.', flush=True)
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', type=Path, default=CACHED_MODEL)
    args = parser.parse_args()
    prepare(args.path)
