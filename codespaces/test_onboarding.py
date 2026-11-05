"""Check that onboarding preserves failures and keeps verbose logs out of context."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('onboarding', Path(__file__).with_name('onboarding.py'))
onboarding = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(onboarding)


class OnboardingTests(unittest.TestCase):
    def test_success_keeps_full_log_and_short_doctor_result(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as output:
            result = onboarding.run([sys.executable, '-c',
                "print('PASS file\\n'*2000); print('Doctor: 0 failed')"], Path(folder))
            response = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(response['summary'], ['Doctor: 0 failed'])
            self.assertLess(len(output.getvalue()), 1000)
            self.assertGreater(len(Path(response['log']).read_text()), 2000)
            self.assertEqual(Path(response['log']).stat().st_mode & 0o777, 0o600)

    def test_failure_keeps_exit_status_and_error(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as output:
            result = onboarding.run([sys.executable, '-c',
                "import sys; print('FAIL missing file'); sys.exit(7)"], Path(folder))
            response = json.loads(output.getvalue())
            self.assertEqual(result, 7)
            self.assertFalse(response['ok'])
            self.assertIn('FAIL missing file', response['error_tail'])

    def test_structured_result_is_returned_without_discarding_fields(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as output:
            result = onboarding.run([sys.executable, '-c',
                'import json; print(json.dumps({"made": True, "boot": "queued", "id": "session-test", "emoji": "📋"}))'],
                Path(folder), structured=True)
            response = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(response['result']['boot'], 'queued')
            self.assertEqual(response['result']['id'], 'session-test')
            self.assertIn('📋', output.getvalue())


if __name__ == '__main__':
    unittest.main()
