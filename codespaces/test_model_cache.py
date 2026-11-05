"""Check verified image caching and startup with a fresh model volume."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import model_cache
import start


class ModelCacheTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.model = self.root / 'image/opt/foxrun-model/model.gguf'
        self.data = b'local model fixture'
        for name, value in [('MODEL_BYTES', len(self.data)),
                            ('MODEL_SHA256', hashlib.sha256(self.data).hexdigest())]:
            fixture = patch.object(model_cache, name, value)
            fixture.start()
            self.addCleanup(fixture.stop)

    def test_build_cache_is_verified_readable_and_reused_without_download(self):
        with patch.object(model_cache.urllib.request, 'urlopen', return_value=io.BytesIO(self.data)) as fetch:
            model_cache.prepare(self.model)
        fetch.assert_called_once()
        self.assertEqual(self.model.read_bytes(), self.data)
        self.assertEqual(self.model.stat().st_mode & 0o777, 0o444)
        with patch.object(model_cache.urllib.request, 'urlopen', side_effect=AssertionError('unexpected download')):
            model_cache.prepare(self.model)

    def test_bad_download_does_not_leave_a_ready_or_partial_model(self):
        with patch.object(model_cache.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad')):
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                model_cache.prepare(self.model)
        self.assertFalse(self.model.exists())
        self.assertFalse(self.model.with_suffix('.partial').exists())

    def test_interrupted_download_cleans_up_for_retry(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.side_effect = [b'partial', OSError('connection closed')]
        with patch.object(model_cache.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(OSError, 'connection closed'):
                model_cache.prepare(self.model)
        self.assertFalse(self.model.exists())
        self.assertFalse(self.model.with_suffix('.partial').exists())

    def test_oversized_download_is_rejected(self):
        with patch.object(model_cache.urllib.request, 'urlopen', return_value=io.BytesIO(self.data + b'extra')):
            with self.assertRaisesRegex(RuntimeError, 'exceeds the pinned size'):
                model_cache.prepare(self.model)
        self.assertFalse(self.model.exists())

    def test_fresh_volumes_import_the_image_model_without_network_download(self):
        self.model.parent.mkdir(parents=True)
        self.model.write_bytes(self.data)
        env = {'FOXRUN_MODEL_FILE': str(self.model)}
        opener = Mock()
        opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(b'{}')
        for name in ('first-volume', 'replacement-volume'):
            state = self.root / name
            state.mkdir()
            with patch.object(start, 'local_opener', return_value=opener), \
                    patch.object(start.subprocess, 'run', side_effect=[Mock(returncode=1), Mock(returncode=0)]) as runner, \
                    patch.object(model_cache.urllib.request, 'urlopen', side_effect=AssertionError('unexpected download')), \
                    patch.object(start.shutil, 'disk_usage', return_value=Mock(free=20 * 1024**3)):
                start.ensure_model(state, env)
            self.assertEqual(runner.call_args.args[0][1:4], ['package', '--gguf', str(self.model)])
            self.assertEqual(self.model.read_bytes(), self.data)
            self.assertFalse((state / 'model.gguf').exists())

    def test_missing_image_cache_fails_without_download(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{}')
        with patch.object(start, 'local_opener', return_value=opener), \
                patch.object(start.subprocess, 'run', return_value=Mock(returncode=1)) as runner, \
                patch.object(model_cache.urllib.request, 'urlopen', side_effect=AssertionError('unexpected download')):
            with self.assertRaisesRegex(RuntimeError, 'Rebuild the devcontainer image'):
                start.ensure_model(self.root, {'FOXRUN_MODEL_FILE': str(self.model)})
        self.assertEqual(runner.call_count, 1)


if __name__ == '__main__':
    unittest.main()
