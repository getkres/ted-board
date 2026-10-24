import reconciler_test_support
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch

ROOT=Path(os.environ.get('RECONCILER_CANDIDATE',Path(__file__).resolve().parents[2]/'candidate'))

def load(name):
 spec=importlib.util.spec_from_file_location('candidate_'+name,ROOT/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@unittest.skipUnless((ROOT/'sessions.py').is_file(),'private reconstructed candidate required')
class IntegrationTests(unittest.TestCase):
 def test_heartbeat_defers_lifecycle_when_enabled(self):
  fake=types.ModuleType('board_client');fake.call=Mock(return_value={'ok':True,'cleared':[]});fake.cards=lambda:[]
  sessions=types.ModuleType('sessions');store=Mock();store.snapshot.return_value=([],[]);sessions.Store=lambda:store;sessions.identity=lambda p:''
  fresh=types.ModuleType('fresh_ted');fresh.dispatch=Mock()
  with patch.dict(sys.modules,{'board_client':fake,'sessions':sessions,'fresh_ted':fresh}),patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'true'}):
   m=load('jobs_heartbeat');m.untracked=lambda jobs:[];m.main()
  store.tick.assert_not_called();store.controls.assert_not_called();store.collect_approvals.assert_not_called();store.flush.assert_not_called()
 def test_board_live_routes_enabled_entry_to_single_loop(self):
  runtime=types.ModuleType('reconciler_runtime');runtime.main=Mock(return_value=0)
  board=types.ModuleType('board_client');board.cards=Mock(side_effect=AssertionError('legacy reaper read'))
  live=types.ModuleType('live_status');live.update=Mock()
  sessions=types.ModuleType('sessions');sessions.alive=Mock();sessions.identity=Mock()
  with patch.dict(sys.modules,{'board_client':board,'live_status':live,'sessions':sessions,'reconciler_runtime':runtime}),patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'true'}):
   self.assertEqual(load('board_live').main(),0)
  runtime.main.assert_called_once_with(['--apply'])
 def test_watchdog_cannot_recover_under_reconciler(self):
  with patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'true'}):
   m=load('job_watchdog')
   with self.assertRaises(RuntimeError):m.main(['--recover','--expected','{}'])
 def test_card_creation_refuses_operational_inbox_ask(self):
  board=types.ModuleType('board_client');board.call=Mock();board.cards=lambda:[];board.resolve_rule=Mock(return_value={'outcome':'rule_applied'})
  sessions=types.ModuleType('sessions');sessions.Store=Mock()
  sync=types.ModuleType('sync');sync.ENDPOINT='https://example.invalid';sync.load_env=lambda:{}
  with patch.dict(sys.modules,{'board_client':board,'sessions':sessions,'sync':sync}):
   m=load('card')
   with self.assertRaises(ValueError):m.create('test','failure','worker stopped without a final result, please retry',needs_you=True)
  board.resolve_rule.assert_not_called()
 def test_steward_cannot_mutate_under_reconciler(self):
  with patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'true'}):
   m=load('inbox_steward');m.snapshot=lambda:([],[],[]);m.move_card=Mock(side_effect=AssertionError('legacy mutation'))
   self.assertTrue(m.run_once()['dry_run'])

if __name__=='__main__':unittest.main()
