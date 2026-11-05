"""Local OpenCode routing keeps session identity and host permissions explicit."""
import json
import os
import shlex
import unittest
from unittest.mock import patch
from tests.support import orchestrate


class OpenCodeRoutes(unittest.TestCase):
    def test_default_uses_local_provider_and_quotes_untrusted_brief(self):
        with patch.dict(os.environ, {'FOXRUN_OPENCODE_MODEL': 'dmr/local-model'}):
            row = orchestrate.resolve(source='opencode', want='fix', task='--agent other; echo bad')
        argv = shlex.split(row['command'])
        self.assertEqual(row['to'], 'opencode')
        self.assertEqual(argv, ['opencode', 'run', '--format', 'json', '--model', 'dmr/local-model', '--', '--agent other; echo bad'])
        self.assertNotIn('--auto', argv)

    def test_review_has_enforced_read_only_tools(self):
        row = orchestrate.resolve(source='opencode', want='review', task='review')
        env = shlex.split(row['command'])[0]
        permissions = json.loads(env.split('=', 1)[1])
        self.assertEqual(permissions['*'], 'deny')
        self.assertEqual(permissions['read'], 'allow')
        self.assertNotIn('bash', permissions)

    def test_continuation_preserves_session_and_parallel_refuses_shared_session(self):
        row = orchestrate.resolve(source='opencode', want='steer', task='follow up', session_id='ses_example')
        self.assertIn('--session ses_example', row['command'])
        self.assertEqual(orchestrate.resolve(source='opencode', want='steer')['status'], 'session_required')
        self.assertEqual(orchestrate.resolve(source='opencode', want='parallel', session_id='ses_example')['status'], 'refused')

    def test_hermes_parallel_refusal_uses_new_native_sessions_without_herdr(self):
        with patch.object(orchestrate, 'herdr_installed', return_value=False):
            for session_id in (None, 'ses_existing'):
                with self.subTest(session_id=session_id):
                    row = orchestrate.resolve(source='opencode', want='parallel', to='hermes',
                                              task='Implement disjoint changes', session_id=session_id)
                    self.assertEqual(row['status'], 'refused')
                    self.assertIn('Hermes child', row['reason'])
                    replacement = shlex.split(row['use_instead'])
                    self.assertEqual(replacement[:2], ['opencode', 'run'])
                    self.assertNotIn('--session', replacement)
                    self.assertNotIn('codex', replacement)
                    self.assertEqual(replacement[-1], 'Implement disjoint changes')

    def test_claude_native_workers_keep_tracked_start_metadata(self):
        for want in orchestrate.ONE_SHOT_ROWS:
            with self.subTest(want=want):
                row = orchestrate.resolve(source='claude', want=want, to='opencode')
                self.assertEqual(row['status'], 'resolved')
                self.assertEqual(row['start'], 'tracked-background')
                self.assertFalse(row['opens_window'])
