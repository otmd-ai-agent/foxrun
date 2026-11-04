"""Real Foxrun lifecycle checks, plus boundaries of the demo's small tool adapter."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import agent

class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='foxrun-demo-test-')
        cls.root=Path(cls.temp.name);cls.system=cls.root/'system';cls.portfolio=cls.root/'portfolio';cls.workspace=cls.portfolio/'demo'
        command=[sys.executable,str(agent.SOURCE/'install.py'),'--home',str(cls.system),'--portfolio',str(cls.portfolio),'--runtime-home',str(cls.root/'runtime'),'--yes','--person','visitor','--workspace','demo','--runtime','codex','--no-schedule']
        result=subprocess.run(command,capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
        cls.patch=patch.multiple(agent,SYSTEM=cls.system,PORTFOLIO=cls.portfolio,WORKSPACE=cls.workspace);cls.patch.start()
    @classmethod
    def tearDownClass(cls):cls.patch.stop();cls.temp.cleanup()
    def test_lifecycle_and_independent_acceptance(self):
        result=agent.execute('create_task',{'title':'Write demo checklist','problem':'Need a small demo','body':'Write three steps','acceptance':'Exactly three Markdown checklist items'})
        self.assertTrue(result['ok'],result);ident=result['output'].strip()
        proof=agent.execute('submit_proof',{'task_id':ident,'content':'- [ ] Create a task\n- [ ] Read proof\n- [ ] Accept it'})
        self.assertTrue(proof['ok'],proof)
        self.assertEqual(next(t['status'] for t in agent.tasks() if t['id']==ident),'in-review')
        self.assertFalse(agent.work('accept',ident,'--by','demo-lead')['ok'])
        self.assertTrue(agent.work('accept',ident,'--by','visitor')['ok'])
        self.assertEqual(next(t['status'] for t in agent.tasks() if t['id']==ident),'done')
        with self.assertRaises(ValueError):agent.execute('submit_proof',{'task_id':ident,'content':'Overwrite'})
    def test_unknown_tools_and_paths_refused(self):
        for tool in ['shell','accept_task','send_email']:
            with self.assertRaises(ValueError):agent.execute(tool,{})
        with self.assertRaises(ValueError):agent.execute('submit_proof',{'task_id':'../../file','content':'bad'})
        with self.assertRaises(ValueError):agent.execute('create_task',{'title':'x'})
    def test_new_history_can_read_persistent_records(self):
        self.assertTrue(agent.execute('list_tasks',{})['tasks'])

if __name__=='__main__':unittest.main()
