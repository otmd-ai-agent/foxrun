"""OpenCode installation and lifecycle checks without a model service."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from base import hookup
import install

spec = importlib.util.spec_from_file_location('opencode_bridge', ROOT / 'hooks/opencode/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class OpenCodeRuntime(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='foxrun-opencode-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'system'
        (self.home / 'config').mkdir(parents=True)
        (self.home / 'config/person.json').write_text('{}')
        self.settings = self.root / 'runtime/opencode.json'
        self.settings.parent.mkdir()

    def test_hookup_preserves_provider_and_plugins_and_is_idempotent(self):
        existing = {'provider': {'dmr': {'options': {'baseURL': 'http://model-runner:12434/v1'}}},
                    'plugin': ['other-plugin'], 'permission': {'bash': 'ask'}}
        self.settings.write_text(json.dumps(existing))
        original = self.settings.read_bytes()
        report = hookup.connect(self.home, {'opencode': self.settings})
        data = json.loads(self.settings.read_text())
        self.assertEqual(data['provider'], existing['provider'])
        self.assertEqual(data['permission'], existing['permission'])
        self.assertEqual(data['plugin'], ['other-plugin', hookup.opencode_plugin(self.home)])
        self.assertNotIn('hooks', data)
        self.assertFalse((self.settings.parent / 'config.toml').exists())
        backup = Path(report[0]['backup']) / 'opencode/opencode.json'
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        second = hookup.connect(self.home, {'opencode': self.settings})
        self.assertEqual(second[0]['written'], [])
        self.assertIsNone(second[0]['backup'])

    def test_invalid_plugin_shape_changes_nothing(self):
        self.settings.write_text('{"plugin": "not-a-list"}')
        original = self.settings.read_bytes()
        with self.assertRaises(ValueError):
            hookup.connect(self.home, {'opencode': self.settings})
        self.assertEqual(self.settings.read_bytes(), original)

    def test_hookup_replaces_only_the_exact_bootstrap_plugin(self):
        source = self.root / 'source'
        original = {'plugin': [hookup.opencode_plugin(source), 'another-plugin']}
        self.settings.write_text(json.dumps(original))
        with patch.dict(os.environ, {'FOXRUN_PRODUCT_SOURCE': str(source)}):
            hookup.connect(self.home, {'opencode': self.settings})
        self.assertEqual(json.loads(self.settings.read_text())['plugin'],
                         ['another-plugin', hookup.opencode_plugin(self.home)])

    def test_runtime_home_and_contract(self):
        with patch.dict(os.environ, {'OPENCODE_CONFIG_DIR': str(self.settings.parent)}):
            self.assertEqual(hookup.runtime_settings('opencode'), self.settings)
        self.assertEqual(hookup.runtime_settings('opencode', self.root / 'override'),
                         self.root / 'override/opencode.json')
        install.install_runtime_contracts({'opencode': self.settings}, self.home, 'avery')
        text = (self.settings.parent / 'AGENTS.md').read_text()
        self.assertIn(str(self.home / 'profile/AGENTS.md'), text)
        self.assertIn(str(self.home / 'agents/soul.md'), text)

    def test_both_keeps_claude_and_codex_scope(self):
        for runtime in ('claude', 'codex'):
            folder = self.home / 'hooks' / runtime
            folder.mkdir(parents=True)
            for name in hookup.SCRIPTS:
                (folder / name).write_text('#!/bin/sh\n')
        result = hookup.hookup_existing(self.home, 'both', self.root / 'both')
        self.assertEqual([row['runtime'] for row in result], ['claude', 'codex'])

    def test_lifecycle_uses_native_runtime_and_actual_handoff_commands(self):
        calls = []
        def invoke(home, relative, arguments, payload):
            calls.append((relative, arguments, payload.copy()))
            if relative in ('foxrun.py', 'hooks/after_compact.py'):
                return json.dumps({'hookSpecificOutput': {'additionalContext': 'Live Foxrun state'}})
            if relative == 'hooks/write_handoff.py':
                return json.dumps({'written': '/portfolio/work/history/handoffs/saved.md'})
            return ''
        payload = {'session_id': 'ses_123', 'cwd': str(self.root)}
        with patch.object(bridge, 'invoke', invoke):
            self.assertEqual(bridge.handle(self.home, 'start', payload)['context'], 'Live Foxrun state')
            self.assertIn('--runtime', calls[0][1])
            self.assertIn('opencode', calls[0][1])
            self.assertEqual(calls[1][0], 'events/session_run.py')
            self.assertEqual(calls[1][2]['runtime'], 'opencode')
            result = bridge.handle(self.home, 'before-compact', payload)
            self.assertIn('saved.md', result['context'])
            self.assertEqual(calls[-2][0], 'hooks/write_handoff.py')
            self.assertEqual(calls[-1][0], 'memory/before_compact.py')
            bridge.handle(self.home, 'after-compact', payload)
            self.assertEqual(calls[-1][:2], ('hooks/after_compact.py', ['opencode']))
            bridge.handle(self.home, 'idle', payload)
            self.assertEqual(calls[-1][1], ['hook-end', '--runtime', 'opencode'])

    def test_child_sessions_cannot_write_person_handoffs(self):
        payload = {'session_id': 'ses_child', 'agent_id': 'ses_child', 'cwd': str(self.root)}
        with patch.object(bridge, 'invoke', return_value='') as invoke:
            result = bridge.handle(self.home, 'before-compact', payload)
            self.assertIsNone(result['handoff'])
            invoke.assert_not_called()
            result = bridge.handle(self.home, 'idle', payload)
            self.assertIsNone(result['handoff'])
            invoke.assert_called_once()
            self.assertEqual(invoke.call_args.args[1:3],
                             ('events/session_run.py', ['hook-end', '--runtime', 'opencode']))

    def test_thread_binding_selects_the_registered_seat_and_rejects_wrong_directory(self):
        row = {'runtime': 'opencode', 'id': 'ses_123', 'cwd': str(self.root)}
        (self.home / 'config/threads.json').write_text(json.dumps({'threads': {'architect@work': row}}))
        with patch.object(bridge, 'invoke', return_value=json.dumps({'hookSpecificOutput': {'additionalContext': 'seat'}})) as invoke:
            bridge.handle(self.home, 'start', {'session_id': 'ses_123', 'cwd': str(self.root)})
            self.assertEqual(invoke.call_args_list[0].args[2][-4:], ['--seat', 'architect', '--workspace', 'work'])
            with self.assertRaisesRegex(ValueError, 'directory'):
                bridge.handle(self.home, 'start', {'session_id': 'ses_123', 'cwd': '/different'})

    def test_invalid_session_and_missing_install(self):
        with self.assertRaisesRegex(ValueError, 'session ID'):
            bridge.handle(self.home, 'start', {'session_id': '../other'})
        (self.home / 'config/person.json').unlink()
        self.assertFalse(bridge.handle(self.home, 'start', {'session_id': 'ses_123'})['installed'])


if __name__ == '__main__':
    unittest.main()
