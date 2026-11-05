"""Exercise configuration preservation, startup guards, and download integrity."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import tempfile
import unittest
from unittest.mock import patch, Mock

SPEC = importlib.util.spec_from_file_location('codespaces_start', Path(__file__).with_name('start.py'))
start = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(start)


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name)
        self.secret = start.password(self.state)
        self.env = start.environment(self.state, 8081, self.secret)

    def test_background_startup_logs_worker_failure_without_failing_lifecycle(self):
        env = dict(os.environ, FOXRUN_CODESPACES_STATE=str(self.state))
        script = str(Path(start.__file__).resolve())
        result = subprocess.run([sys.executable, script, '--background'], env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('startup.log', result.stdout)
        log = self.state / 'startup.log'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if log.exists() and 'Rebuild the devcontainer' in log.read_text():
                break
            time.sleep(0.05)
        self.assertIn('Codespaces startup requires the container account home', log.read_text())
        foreground = subprocess.run([sys.executable, script], env=env,
                                    capture_output=True, text=True, timeout=5)
        self.assertEqual(foreground.returncode, 1)
        self.assertIn('Rebuild the devcontainer', foreground.stderr)
        self.assertFalse((self.state / 'user').exists())

    def test_home_aliases_are_checked_and_stay_inside_state(self):
        user_home = self.state / 'user'
        start.prepare_user_home(self.state, user_home=user_home)
        for alias, target in (('.foxrun', 'system'), ('foxrun', 'portfolio')):
            self.assertTrue((user_home / alias).is_symlink())
            self.assertEqual((user_home / alias).resolve(), self.state / target)
        start.prepare_user_home(self.state, user_home=user_home)
        self.assertEqual(self.env.get('HOME'), os.environ.get('HOME'))

    def test_home_aliases_refuse_other_home_and_existing_data(self):
        unrelated = self.state / 'unrelated'
        with self.assertRaisesRegex(RuntimeError, 'account home'):
            start.prepare_user_home(self.state, user_home=unrelated)
        self.assertFalse(unrelated.exists())
        user_home = self.state / 'user'
        user_home.mkdir()
        (user_home / 'foxrun').mkdir()
        (user_home / 'foxrun/kept.txt').write_text('Keep this file.')
        with self.assertRaisesRegex(RuntimeError, 'existing path'):
            start.prepare_user_home(self.state, user_home=user_home)
        self.assertFalse((user_home / '.foxrun').is_symlink())
        self.assertEqual((user_home / 'foxrun/kept.txt').read_text(), 'Keep this file.')
        (user_home / '.foxrun').symlink_to(self.state / 'wrong-system')
        with self.assertRaisesRegex(RuntimeError, 'Conflicting Foxrun alias'):
            start.prepare_user_home(self.state, user_home=user_home)

    def test_password_is_private_and_reused(self):
        self.assertEqual(start.password(self.state), self.secret)
        self.assertEqual((self.state / 'server-password').stat().st_mode & 0o777, 0o600)
        (self.state / 'server-password').chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'chmod 600'):
            start.password(self.state)

    def test_configuration_preserves_installed_hooks_and_uses_only_local_model(self):
        launch = start.configure(self.state, 8081, self.env, user_home=self.state / 'user')
        path = self.state / 'opencode-config/opencode.json'
        config = json.loads(path.read_text())
        installed = (self.state / 'system/hooks/opencode/foxrun.mjs').as_uri()
        config['plugin'].extend([installed, 'other-plugin'])
        config['permission'] = {'bash': 'ask'}
        config['command']['mine'] = {'template': 'My command'}
        path.write_text(json.dumps(config))
        start.configure(self.state, 8081, self.env, user_home=self.state / 'user')
        actual = json.loads(path.read_text())
        self.assertEqual(actual['plugin'], [installed, 'other-plugin'])
        self.assertEqual(actual['permission'], {'bash': 'ask'})
        self.assertIn('mine', actual['command'])
        self.assertEqual(actual['enabled_providers'], ['dmr'])
        self.assertEqual(actual['model'], actual['small_model'])
        self.assertFalse((self.state / 'system/config/person.json').exists())
        self.assertTrue((launch / '.opencode/skills/foxrun-setup/SKILL.md').exists())
        self.assertNotIn(self.secret, path.read_text())

    def test_repeated_start_does_not_launch_a_second_server(self):
        with patch.object(start, 'healthy', return_value=True), patch.object(start, 'ensure_model') as model, \
                patch.object(start.subprocess, 'Popen') as process:
            start.start(self.state, 8081, user_home=self.state / 'user')
        model.assert_not_called()
        process.assert_not_called()

    def test_unrelated_listener_is_not_killed_or_replaced(self):
        with socket.socket() as listener:
            listener.bind(('0.0.0.0', 0))
            listener.listen()
            port = listener.getsockname()[1]
            with patch.object(start, 'healthy', return_value=False), patch.object(start, 'ensure_model') as model:
                with self.assertRaisesRegex(RuntimeError, 'occupied by another process'):
                    start.start(self.state, port, user_home=self.state / 'user')
            model.assert_not_called()

    def test_invalid_model_is_not_packaged(self):
        model = self.state / 'supplied.gguf'
        model.write_bytes(b'wrong model bytes')
        self.env['FOXRUN_MODEL_FILE'] = str(model)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{}'
        opener = Mock()
        opener.open.return_value = response
        with patch.object(start, 'local_opener', return_value=opener), \
                patch.object(start.subprocess, 'run', return_value=Mock(returncode=1)) as runner:
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                start.ensure_model(self.state, self.env)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[0][1], 'inspect')
        self.assertTrue(model.exists())


if __name__ == '__main__':
    unittest.main()
