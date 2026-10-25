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
 def test_busy_pass_lock_reports_operator_commands_as_unperformed(self):
  for args in (['--redrive','c','--reason','repaired'],['--settle-review','c','--approval-id','a','--review-outcome','failed','--reason','verified']):
   with tempfile.TemporaryDirectory() as temp,patch.dict(d.os.environ,{'TED_RECONCILER_ENABLED':'true'}),patch.object(d.socket,'gethostname',return_value='test-mini'),patch.object(d.fcntl,'flock',side_effect=BlockingIOError),patch.object(d.importlib,'import_module',side_effect=AssertionError('busy command must not mutate')):
    Path(temp,'jobs').mkdir()
    self.assertEqual(d.main(['--apply','--root',temp]+args),1)
 def test_route_forwards_observed_revision_and_messages(self):
  from unittest.mock import Mock
  messages=[dict(who='Ted',text='operational work')]
  board=types.SimpleNamespace(call=Mock(return_value=dict(ok=True)))
  action=dict(kind='route_ted',payload=dict(card_id='c',expected_updated_at='2026-10-23T20:00:00Z',expected_revision=7,expected_messages=messages))
  self.assertTrue(d.execute(action,None,{},board))
  self.assertEqual(board.call.call_args.kwargs['expected_revision'],7)
  self.assertEqual(board.call.call_args.kwargs['expected_messages'],messages)
 def test_verified_close_forwards_the_planned_revision_guard(self):
  from unittest.mock import Mock
  board=types.SimpleNamespace(call=Mock(return_value=dict(ok=True)))
  action=dict(kind='close_verified',payload=dict(card_id='c',expected_updated_at='2026-10-23T20:00:00Z',expected_revision=7))
  self.assertTrue(d.execute(action,None,dict(cards=[dict(id='c',revision=8)]),board))
  self.assertEqual(board.call.call_args.kwargs['expected_revision'],7)
  self.assertEqual(board.call.call_args.kwargs['expected_updated_at'],'2026-10-23T20:00:00Z')
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
 def test_stopped_review_clears_review_and_active_account_state(self):
  s={'turn':'t','lease_token':'f','stop_requested':True,'queue':[{'id':'new'}],
     'reviewing':'approval','review_context':'private review','review_session_id':'review-thread',
     'review_claude_lane':'design','review_claude_config_dir':'private',
     'active_claude_lane':'design','active_claude_config_dir':'private','active_claude_managed':True,
     'active_turn':{'id':'old','kind':'review'},'active_veto_revision':4}
  a={'id':'stop','kind':'stop_worker','payload':{'expected_turn':'t','expected_lease_token':'f'}}
  self.assertTrue(d.recover_session(s,a,lambda s:True))
  self.assertEqual(s['queue'],[{'id':'new'}])
  for key in ('reviewing','review_context','review_session_id','review_claude_lane',
              'review_claude_config_dir','active_claude_lane','active_claude_config_dir',
              'active_claude_managed','active_turn','active_veto_revision'):
   self.assertNotIn(key,s,key)

 def test_stop_discards_automatic_queue_but_retains_human_requests(self):
  s={'turn':'t','lease_token':'f','stop_requested':True,'queue':[{'id':'human'},{'id':'auto','automatic':True},{'id':'reconciler-retry-old'}]}
  a={'id':'stop','kind':'stop_worker','payload':{'expected_turn':'t','expected_lease_token':'f'}}
  self.assertTrue(d.recover_session(s,a,lambda s:True))
  self.assertEqual(s['queue'],[{'id':'human'}])
 def test_operator_can_settle_a_dead_lettered_review_without_restarting_it(self):
  data={'sessions':{'c':dict(status='dead_letter',pid=None,reviewing='a',turn='t',lease_token='f',review_context='private',active_turn={'kind':'review'},claude_lane='design')},'approvals':{'a':dict(id='a',card_id='c',status='reviewing')}}
  d.settle_review(data,'c','a','failed','verified that the action did not complete')
  self.assertEqual(data['approvals']['a']['status'],'failed');self.assertTrue(data['approvals']['a']['sync_status'])
  self.assertNotIn('reviewing',data['sessions']['c']);self.assertNotIn('active_turn',data['sessions']['c'])
  self.assertEqual(data['sessions']['c']['claude_lane'],'design');self.assertEqual(data['sessions']['c']['status'],'dead_letter')
  with self.assertRaises(ValueError):d.settle_review(data,'c','a','done','stale duplicate request')
 def test_review_settlement_cli_refuses_a_live_reviewer_without_mutating_metadata(self):
  data={'sessions':{'c':dict(status='dead_letter',pid=None,reviewing='a',turn='t',lease_token='f',lease=dict(pid=123,identity='matching'))},'approvals':{'a':dict(id='a',card_id='c',status='reviewing')}}
  @contextlib.contextmanager
  def locked():yield data
  store=types.SimpleNamespace(locked=locked)
  with tempfile.TemporaryDirectory() as temp,patch.dict(d.os.environ,{'TED_RECONCILER_ENABLED':'true'}),patch.object(d.socket,'gethostname',return_value='test-mini'),patch.object(d.importlib,'import_module',return_value=types.SimpleNamespace(Store=lambda root:store)),patch.object(d,'confirmed_stop',return_value=False):
   Path(temp,'jobs').mkdir()
   with self.assertRaisesRegex(RuntimeError,'process absence'):
    d.main(['--apply','--root',temp,'--settle-review','c','--approval-id','a','--review-outcome','failed','--reason','verified not applied'])
  self.assertEqual(data['approvals']['a']['status'],'reviewing');self.assertEqual(data['sessions']['c']['reviewing'],'a')
 def test_review_settlement_cli_records_only_the_verified_local_outcome(self):
  data={'sessions':{'c':dict(status='dead_letter',pid=None,reviewing='a',turn='t',lease_token='f',lease=dict(pid=123,identity='matching'))},'approvals':{'a':dict(id='a',card_id='c',status='reviewing')}}
  @contextlib.contextmanager
  def locked():yield data
  store=types.SimpleNamespace(locked=locked)
  with tempfile.TemporaryDirectory() as temp,patch.dict(d.os.environ,{'TED_RECONCILER_ENABLED':'true'}),patch.object(d.socket,'gethostname',return_value='test-mini'),patch.object(d.importlib,'import_module',return_value=types.SimpleNamespace(Store=lambda root:store)) as imports,patch.object(d,'confirmed_stop',return_value=True) as stopped:
   Path(temp,'jobs').mkdir()
   self.assertEqual(d.main(['--apply','--root',temp,'--settle-review','c','--approval-id','a','--review-outcome','done','--reason','verified the exact approved effect']),0)
  self.assertEqual(imports.call_count,1);self.assertEqual(stopped.call_args.kwargs,{'allow_kill':False})
  self.assertEqual(data['approvals']['a']['status'],'done');self.assertNotIn('reviewing',data['sessions']['c'])
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

class ConservativeRouting(unittest.TestCase):
 def test_original_decision_and_auth_scope_cannot_be_routed_by_a_cosmetic_status(self):
  cards=[dict(id=str(n),section='needs_you',title=title,body=body,live_status='ted review pending') for n,(title,body) in enumerate([
   ('Creator rate', 'flat fee $2,200, so you decide'),
   ('Copy', 'yours to write: pin the headline and type your version'),
   ('Login', 'one-time authentication key, enter the code'),
   ('Submit', 'sign in to app store connect and complete apple verification')])]
  board=types.SimpleNamespace(call=lambda **k:dict(jobs=[],reconciliation_error='not_published') if k else dict(cards=cards))
  mockups=types.SimpleNamespace(call=lambda:dict(mockups=[]))
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'jobs').mkdir();(root/'jobs/sessions.json').write_text('{"sessions":{}}')
   snapshot=d.observe(root,board=board,mockups=mockups)
   result=d.plan(snapshot,now=1800000000)
  self.assertFalse(any(a['kind']=='route_ted' for a in result['actions']))
  self.assertTrue(all(c.get('classification_uncertain') for c in snapshot['cards']))

class PassLimits(unittest.TestCase):
 def fixture(self):
  actions=[];items=[]
  for kind in ('retry','route_ted','create_build','advance_deploy','advance_verify','dispatch','escalate_2h'):
   for n in reversed(range(18)):
    cid=kind+str(n);items.append(dict(id='card:'+cid,card_id=cid,action_started_at=d.iso(1700000000+n),priority=2))
    actions.append(dict(id=cid,kind=kind,entity=cid,payload=dict(card_id=cid)))
  return dict(actions=actions,items=items,ted_queue=[x['id'] for x in items],generated_at=d.iso(1800000000),coverage_defects=[],banner=True)
 def test_apply_limits_each_mutation_class_oldest_first_and_carries_remainder(self):
  result=self.fixture();completed={d.INITIAL_DIGEST_ID}
  selected,deferred=d.select_pass(result,completed)
  expected={'retry':3,'route_ted':5,'create_build':5,'dispatch':10,'escalate_2h':10}
  for kind,count in expected.items():
   self.assertEqual([a['id'] for a in selected if a['kind']==kind],[kind+str(n) for n in range(count)])
  self.assertEqual(sum(a['kind'].startswith('advance_') for a in selected),5)
  self.assertEqual(len(selected)+len(deferred),len(result['actions']))
  first={a['id'] for a in selected};result['actions']=[a for a in result['actions'] if a['id'] not in first]
  selected,_=d.select_pass(result,completed|first)
  self.assertEqual([a['id'] for a in selected if a['kind']=='retry'],['retry3','retry4','retry5'])
 def test_first_run_creates_one_ranked_digest_and_no_individual_escalations(self):
  result=self.fixture();selected,deferred=d.select_pass(result,set())
  digest=[a for a in selected if a['kind']=='escalation_digest']
  self.assertEqual(len(digest),1)
  self.assertFalse(any(a['kind'].startswith('escalate_') for a in selected))
  self.assertEqual(len([a for a in selected if a['kind'] in ('escalation_digest','create_build')]),5)
  self.assertEqual(digest[0]['payload']['covered_ids'],['escalate_2h'+str(n) for n in range(18)])
  self.assertEqual(digest[0]['payload']['items'][0]['card_id'],'escalate_2h0')
 def test_digest_replay_creates_one_card_and_receipts_the_covered_backlog(self):
  result=self.fixture();result['actions']=[a for a in result['actions'] if a['kind']=='escalate_2h']
  snapshot=dict(cards=[],coverage=dict(backend_ledger='ok',inbox_policy='ok',remote_jobs='ok'))
  created=[]
  def create(*args,**kwargs):
   created.append(kwargs['card_id']);snapshot['cards'].append(dict(id=kwargs['card_id']))
  board=types.SimpleNamespace(call=lambda *a,**k:dict(ok=True))
  with tempfile.TemporaryDirectory() as temp,patch.dict(sys.modules,{'card':types.SimpleNamespace(create=create)}),patch.object(d,'plan',return_value=result):
   path=Path(temp)/'journal.db'
   first=d.run(snapshot,path,1800000000,False,object(),board)
   self.assertFalse(first['failed'])
   self.assertEqual(d.completed_readonly(path),{d.INITIAL_DIGEST_ID}|{'escalate_2h'+str(n) for n in range(18)})
   d.run(snapshot,path,1800000000,False,object(),board)
   self.assertEqual(created,['reconciler-initial-ted-digest'])
 def test_digest_marker_and_members_roll_back_together_on_receipt_failure(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as temp,d.Journal(Path(temp)/'journal.db') as journal:
   journal.db.execute("create trigger receipt_failure before insert on receipts when new.id='member' begin select raise(abort,'fixture'); end")
   with self.assertRaises(sqlite3.IntegrityError):journal.complete_group([(d.INITIAL_DIGEST_ID,'escalation_digest'),('member','initial_digest_member')])
   self.assertEqual(journal.completed(),set())

 def test_unexecuted_and_failed_actions_never_receive_receipts(self):
  result=self.fixture();s={'coverage':dict(backend_ledger='ok',inbox_policy='ok',remote_jobs='ok')}
  board=types.SimpleNamespace(call=lambda *a,**k:dict(ok=True))
  with tempfile.TemporaryDirectory() as temp,patch.object(d,'plan',return_value=result),patch.object(d,'execute',return_value=False):
   path=Path(temp)/'journal.db';out=d.run(s,path,1800000000,False,object(),board)
   self.assertEqual(d.completed_readonly(path),set());self.assertTrue(out['deferred'])

if __name__=='__main__':unittest.main()
