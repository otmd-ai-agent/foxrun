"""Native OpenCode entry points enforce policy before starting inference."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from base.agent_catalog import model_policy, validate_opencode_model
from agents.tools import agent_new

ROOT = Path(__file__).resolve().parents[1]


def load(relative, name):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / relative))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


THREADS = [load(path, 'thread_policy_' + str(i)) for i, path in enumerate((
    'skillwright/skills/thread/bin/thread', 'plugins/foxrun/skills/thread/bin/thread'))]
ORCHESTRATORS = [load(path, 'orchestrate_policy_' + str(i)) for i, path in enumerate((
    'skills/orchestrate/bin/orchestrate', 'skillwright/skills/orchestrate/bin/orchestrate'))]


class OpenCodeModelPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        (self.home / 'config').mkdir()
        self.policy = json.loads((ROOT / 'config/models.yaml').read_text())
        self.policy['allowed'].append('dmr/fixture-model')
        self.policy['banned'] += ['blocked-model', 'dmr/qualified-ban']
        for tier in self.policy['tiers'].values():
            tier['opencode'] = {'model': 'dmr/fixture-model'}
        self.save()
        environment = patch.dict(os.environ, {'HOME': str(self.home), 'FOXRUN_HOME': str(self.home),
                                             'FOXRUN_OPENCODE_MODEL': ''})
        environment.start()
        self.addCleanup(environment.stop)

    def save(self):
        (self.home / 'config/models.yaml').write_text(json.dumps(self.policy))

    def test_syntax_and_both_ban_forms(self):
        for value in ('model', '/model', 'dmr/', 'dmr/model name', 'dmr/model\n',
                      'dmr/\x00model', 'dmr//model', 'dmr/a//b', 'dmr/a/'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_opencode_model(value)
        self.assertEqual(validate_opencode_model('dmr/foxrun/gemma4-e4b:qat-q4_0-32k'),
                         'dmr/foxrun/gemma4-e4b:qat-q4_0-32k')
        for banned in ('blocked-model', 'dmr/blocked-model'):
            with self.assertRaisesRegex(ValueError, 'banned'):
                validate_opencode_model('dmr/blocked-model', [banned])

    def test_core_checks_env_and_tier_bans(self):
        for value in ('dmr/blocked-model', 'dmr/qualified-ban', 'bare-model', 'dmr/model name'):
            with self.subTest(value=value), patch.dict(os.environ, {'FOXRUN_OPENCODE_MODEL': value}):
                with self.assertRaises(ValueError):
                    model_policy(self.home)
        self.policy['banned'].append('fixture-model')
        self.save()
        with self.assertRaisesRegex(ValueError, 'banned'):
            model_policy(self.home)

    def test_thread_env_explicit_and_tier_models_are_checked_in_both_copies(self):
        for thread in THREADS:
            for value in ('dmr/blocked-model', 'dmr/qualified-ban', 'bare-model', 'dmr/model name'):
                with self.subTest(copy=thread.__name__, value=value):
                    with patch.dict(os.environ, {'FOXRUN_OPENCODE_MODEL': value}):
                        with self.assertRaises(thread.ThreadError):
                            thread.pick_model(self.home, 'opencode', 'work', None)
                    policy = json.loads(json.dumps(self.policy))
                    policy['allowed'].append(value)
                    policy['tiers']['work']['opencode'] = {'model': value}
                    with patch.object(thread, 'models', return_value=policy):
                        for explicit in (value, None):
                            with self.assertRaises(thread.ThreadError):
                                thread.pick_model(self.home, 'opencode', 'work', explicit)
            with patch.dict(os.environ, {'FOXRUN_OPENCODE_MODEL': 'dmr/new-local-model'}):
                self.assertEqual(thread.pick_model(self.home, 'opencode', 'work', None),
                                 ('dmr/new-local-model', None))

    def test_orchestrate_policy_runs_before_returning_a_command(self):
        for orchestrate in ORCHESTRATORS:
            for value in ('dmr/blocked-model', 'dmr/qualified-ban', 'bad-model'):
                with self.subTest(copy=orchestrate.__name__, value=value):
                    with patch.dict(os.environ, {'FOXRUN_OPENCODE_MODEL': value}):
                        with self.assertRaises(orchestrate.ResolveError):
                            orchestrate.resolve(source='opencode', want='fix')
            row = orchestrate.resolve(source='opencode', want='fix')
            self.assertIn('--model dmr/fixture-model', row['command'])
            with patch.dict(os.environ, {'FOXRUN_HOME': str(self.home / 'standalone'),
                                         'FOXRUN_OPENCODE_MODEL': 'dmr/local-only'}):
                self.assertIn('--model dmr/local-only', orchestrate.resolve(source='opencode', want='review')['command'])

    def test_probe_rejects_banned_env_before_runner(self):
        identity = SimpleNamespace(data={'id': 'fixture-seat', 'tier': 'work'})
        runner = Mock()
        with patch.object(agent_new, 'roots', return_value={'repo': self.home, 'system': self.home, 'vault': self.home}), \
             patch.object(agent_new, 'cape_body', return_value='Fixture identity'), \
             patch.dict(os.environ, {'FOXRUN_OPENCODE_MODEL': 'dmr/blocked-model'}):
            with self.assertRaisesRegex(agent_new.AgentNewError, 'banned'):
                agent_new.probe_one('opencode', identity, 1, runner)
        runner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
