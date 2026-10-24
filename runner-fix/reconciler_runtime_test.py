import reconciler_test_support
import json
import contextlib
import types
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import reconciler_runtime as d

class RuntimeTests(unittest.TestCase):
 def test_dry_run_never_constructs_effect_store_or_executes_actions(self):
  s={'cards':[],'sessions':{},'approvals':[],'mockups':[],'coverage':{}}
  with tempfile.TemporaryDirectory() as tmp,patch.object(d,'execute',side_effect=AssertionError('effect called')):
   result=d.run(s,Path(tmp)/'journal.db',now=1800000000,dry_run=True)
   self.assertFalse((Path(tmp)/'journal.db').exists());self.assertFalse(result['applied'])
 def test_journal_survives_restart_and_deduplicates(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'journal.db'
   with d.Journal(path) as j:j.complete('a',{'kind':'note'})
   with d.Journal(path) as j:self.assertEqual(j.completed(),{'a'})
 def test_failed_effect_is_not_recorded_success(self):
  with tempfile.TemporaryDirectory() as tmp:
   with d.Journal(Path(tmp)/'journal.db') as j:
    self.assertFalse(d.execute_recorded({'id':'a','kind':'dispatch'},j,lambda a:False));self.assertEqual(j.completed(),set())
 def test_retry_requires_matching_fence_and_verified_process_exit(self):
  session={'turn':'one','lease_token':'a','status':'running','pid':100,'identity':'ident','retry_count':0,'active_turn':{'message':'work'}}
  action={'id':'id','kind':'retry','payload':{'card_id':'c','expected_turn':'one','expected_lease_token':'a','attempt':1,'retry_at':'2027-01-15T08:01:00Z'}}
  self.assertFalse(d.recover_session(session,action,stop=lambda s:False))
  self.assertEqual(session['status'],'running')
  self.assertTrue(d.recover_session(session,action,stop=lambda s:True))
  self.assertEqual(session['retry_count'],1);self.assertEqual(len(session['queue']),1);self.assertEqual(session['status'],'queued')
  self.assertFalse(d.recover_session(session,action,stop=lambda s:True));self.assertEqual(len(session['queue']),1)
 def test_dead_worker_simulation_then_exhausted_retry(self):
  s={'turn':'one','lease_token':'a','status':'failed','pid':None,'retry_count':2}
  a={'id':'id','kind':'dead_letter','payload':{'card_id':'c','expected_turn':'one','expected_lease_token':'a','attempt':3}}
  self.assertTrue(d.recover_session(s,a,stop=lambda s:True));self.assertEqual(s['status'],'dead_letter');self.assertFalse(s['queue'])
 def test_side_effect_retry_refused_even_with_malformed_plan(self):
  s={'turn':'one','lease_token':'a','reviewing':'approval'}
  a={'id':'id','kind':'retry','payload':{'expected_turn':'one','expected_lease_token':'a'}}
  self.assertFalse(d.recover_session(s,a,stop=lambda s:True))
 def test_orphan_child_prevents_retry_even_when_wrapper_exited(self):
  import types,sys
  sessions=types.ModuleType('sessions');sessions.alive=lambda *a:False;sessions.safe_kill=lambda *a:False
  with patch.dict(sys.modules,{'sessions':sessions}),patch.object(d,'group_members',return_value=[1234]):
   self.assertFalse(d.confirmed_stop({'pid':100,'identity':'ident'}))
 def test_process_observation_failure_prevents_retry(self):
  import types,sys
  sessions=types.ModuleType('sessions');sessions.alive=lambda *a:False;sessions.safe_kill=lambda *a:False
  with patch.dict(sys.modules,{'sessions':sessions}),patch.object(d,'group_members',return_value=None):
   self.assertFalse(d.confirmed_stop({'pid':100,'identity':'ident'}))
 def test_result_arriving_after_observe_is_rechecked_before_recovery(self):
  with tempfile.TemporaryDirectory() as tmp:
   session={'turn':'t','lease_token':'f','status':'running','cwd':tmp}
   Path(tmp,'t.result.json').write_text('{"ok":true,"text":"finished"}')
   data={'sessions':{'c':session}}
   @contextlib.contextmanager
   def locked():yield data
   store=types.SimpleNamespace(locked=locked)
   sessions=types.SimpleNamespace(matching_result=lambda s,r:True)
   action={'id':'a','kind':'retry','payload':{'card_id':'c','expected_turn':'t','expected_lease_token':'f','attempt':1,'retry_at':'2027-01-15T08:01:00Z'}}
   with patch.dict(sys.modules,{'sessions':sessions}),patch.object(d,'confirmed_stop',side_effect=AssertionError('must not stop completed work')):
    self.assertFalse(d.execute(action,store,{},None))
   self.assertEqual(session['status'],'running')
 def test_unavailable_jobs_read_cannot_publish_partial_ledger(self):
  s={'cards':[],'sessions':{},'approvals':[],'mockups':[],'coverage':{'remote_jobs':'unavailable','inbox_policy':'ok'}}
  board=types.SimpleNamespace(call=lambda *a,**k: (_ for _ in ()).throw(AssertionError('partial publish forbidden')))
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(RuntimeError):d.run(s,Path(tmp)/'journal.db',1800000000,False,object(),board)
 def test_classified_card_priority_reaches_existing_session_admission(self):
  data={'sessions':{'c':{'status':'queued','queue':[{'id':'work'}],'lease_token':'f'}}}
  @contextlib.contextmanager
  def locked():yield data
  d.sync_scheduling(types.SimpleNamespace(locked=locked),{'cards':[{'id':'c','priority_class':'urgent','explicit_ask':True}]})
  self.assertEqual(data['sessions']['c']['priority_class'],'urgent');self.assertTrue(data['sessions']['c']['explicit_ask']);self.assertEqual(data['sessions']['c']['queue'],[{'id':'work'}]);self.assertEqual(data['sessions']['c']['lease_token'],'f')
 def test_cancelled_attempt_cannot_retry_and_stop_settlement_preserves_new_work(self):
  s={'turn':'t','lease_token':'f','stop_requested':True,'queue':[{'id':'new'}]}
  a={'id':'a','kind':'retry','payload':{'expected_turn':'t','expected_lease_token':'f','attempt':1,'retry_at':'2027-01-15T08:01:00Z'}}
  self.assertFalse(d.recover_session(s,a,lambda s:True));a['kind']='stop_worker'
  self.assertTrue(d.recover_session(s,a,lambda s:True));self.assertEqual(s['status'],'queued');self.assertEqual(s['queue'],[{'id':'new'}]);self.assertFalse(s.get('stop_requested'))
 def test_renewed_current_lease_invalidates_an_old_recovery_proposal(self):
  import time
  s={'turn':'t','lease_token':'f','status':'running','lease_expires_at':time.time()+150}
  a={'id':'a','kind':'retry','payload':{'expected_turn':'t','expected_lease_token':'f','attempt':1,'retry_at':'2027-01-15T08:01:00Z'}}
  self.assertFalse(d.recover_session(s,a,lambda s: (_ for _ in ()).throw(AssertionError('valid lease must not be killed'))))
 def test_recovery_preserves_new_user_requests(self):
  s={'turn':'one','lease_token':'a','status':'running','queue':[{'id':'new','message':'new request'}]}
  a={'id':'id','kind':'retry','payload':{'expected_turn':'one','expected_lease_token':'a','attempt':1,'retry_at':'2027-01-15T08:01:00Z'}}
  self.assertTrue(d.recover_session(s,a,stop=lambda s:True));self.assertEqual(s['queue'][-1]['id'],'new')
 def test_dead_letter_retains_new_user_requests(self):
  s={'turn':'one','lease_token':'a','status':'running','queue':[{'id':'new'}]}
  a={'id':'id','kind':'dead_letter','payload':{'expected_turn':'one','expected_lease_token':'a'}}
  self.assertTrue(d.recover_session(s,a,stop=lambda s:True));self.assertEqual(s['queue'],[{'id':'new'}])
 def test_redrive_requires_ted_reason_and_preserves_attempt_history(self):
  s={'status':'dead_letter','retry_count':2,'active_turn':{'message':'work'},'queue':[]}
  with self.assertRaises(ValueError):d.redrive(s,'')
  d.redrive(s,'dependency repaired');self.assertEqual(s['status'],'queued');self.assertEqual(s['redrive_history'][0]['retry_count'],2)
 def test_fresh_schema_can_bootstrap_without_prior_snapshot(self):
  board=type('Board',(),{'call':staticmethod(lambda **kw: {'jobs':[],'reconciliation':None,'reconciliation_error':'not_published'} if kw else {'cards':[]})})()
  mockups=type('Mockups',(),{'call':staticmethod(lambda:{'mockups':[]})})()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'jobs').mkdir();(root/'jobs/sessions.json').write_text('{"sessions":{},"approvals":{}}')
   s=d.observe(root,board=board,mockups=mockups)
   self.assertEqual(s['coverage']['backend_ledger'],'ok')
 def test_read_local_snapshot_does_not_write_sessions(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'jobs').mkdir();p=root/'jobs/sessions.json';p.write_text(json.dumps({'sessions':{},'approvals':{}}));before=p.stat().st_mtime_ns
   result=d.local_snapshot(root,[]);self.assertEqual(p.stat().st_mtime_ns,before);self.assertEqual(result['sessions'],{})

if __name__=='__main__':unittest.main()
