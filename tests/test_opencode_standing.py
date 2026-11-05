"""OpenCode standing seats keep a native binding before the boot prompt runs."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from work import standing


class OpenCodeStandingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.home = root / 'system'
        self.portfolio = root / 'portfolio'
        self.workspace = self.portfolio / 'sample'
        for relative in ('config', 'agents', 'profile'):
            (self.home / relative).mkdir(parents=True)
        self.workspace.mkdir(parents=True)
        self.identity = self.home / 'agents/architect.md'
        self.identity.write_text('---\nid: architect\nruntimes: [opencode]\n---\n# Architect\n\n### Boot reads\nRead the current contract.\n')
        (self.home / 'config/models.yaml').write_text((Path(__file__).resolve().parents[1] / 'config/models.yaml').read_text())
        (self.home / 'config/standing-seats.json').write_text(json.dumps({'seats': {'architect': 'system:agents/architect.md'}}))
        for file in (self.home / 'agents/soul.md', self.home / 'profile/AGENTS.md',
                     self.workspace / 'AGENTS.md', self.workspace / 'RESOLVER.md'):
            file.write_text('# Labeled fixture\n')
        environment = patch.dict(os.environ, {'FOXRUN_HOME': str(self.home), 'FOXRUN_PORTFOLIO': str(self.portfolio),
                                             'FOXRUN_OPENCODE_MODEL': 'dmr/local-test-model'})
        environment.start()
        self.addCleanup(environment.stop)
        self.args = argparse.Namespace(name='architect-local', seat='architect', workspace='sample',
                                       runtime='opencode', conversation='opencode:caller', caller='opencode')

    def call(self, api):
        output = io.StringIO()
        with patch.object(standing, 'opencode_api', api), contextlib.redirect_stdout(output):
            code = standing.standing(self.args)
        return code, json.loads(output.getvalue())

    def test_binding_exists_before_prompt_and_resume_reads_current_identity(self):
        calls = []
        def api(workspace, path, body):
            calls.append((workspace, path, body))
            if path == '/session':
                return {'id': 'ses_real_id'}
            bound = standing.read(standing.store('sessions/opencode/ses_real_id.json'))
            self.assertEqual(bound['seat'], 'architect')
            context = standing.start(runtime='opencode', session='ses_real_id', hook={'cwd': str(self.workspace)})
            self.assertIn('Seat: architect', context)
        code, result = self.call(api)
        self.assertEqual(code, 0)
        self.assertEqual(result['native_session_id'], 'ses_real_id')
        self.assertEqual(result['boot'], 'queued')
        self.assertEqual(calls[1][2]['model'], {'providerID': 'dmr', 'modelID': 'local-test-model'})
        self.identity.write_text(self.identity.read_text() + '\nCurrent instruction added after launch.\n')
        self.assertIn('Current instruction added after launch.', standing.start(runtime='opencode', session='ses_real_id'))
        with self.assertRaisesRegex(ValueError, 'outside the standing workspace'):
            standing.start(runtime='opencode', session='ses_real_id', hook={'cwd': str(self.home)})

    def test_missing_hook_keeps_session_and_reserved_name_for_inspection(self):
        def api(workspace, path, body):
            return {'id': 'ses_no_hook'} if path == '/session' else None
        with patch.object(standing.time, 'monotonic', side_effect=[0, 20]):
            with self.assertRaisesRegex(ValueError, 'hook did not deliver seat context'):
                self.call(api)
        self.assertTrue(standing.store('sessions/opencode/ses_no_hook.json').is_file())
        self.assertTrue(standing.store('names/opencode/architect-local.json').is_file())
        with self.assertRaisesRegex(ValueError, 'standing name exists'):
            self.call(api)

    def test_banned_model_is_rejected_before_session_or_binding(self):
        policy_file = self.home / 'config/models.yaml'
        policy = json.loads(policy_file.read_text())
        policy['banned'].append('local-test-model')
        policy_file.write_text(json.dumps(policy))
        with patch.object(standing, 'opencode_api') as api:
            with self.assertRaisesRegex(ValueError, 'banned'):
                standing.standing(self.args)
        api.assert_not_called()
        self.assertFalse((self.home / 'runs/standing').exists())

    def test_unmanaged_opencode_session_has_no_standing_identity(self):
        with patch.object(standing, 'ancestry_launch', return_value=None):
            self.assertIsNone(standing.start(runtime='opencode', session='ses_unmanaged'))


if __name__ == '__main__':
    unittest.main()
