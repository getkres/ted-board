"""Managed failure routing only. Flag-off byte compatibility is tested separately."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

ROOT=Path(os.environ['TED_RUNTIME_SOURCE']).resolve()
sys.path.insert(0,str(ROOT))
requests=[]
current=dict(id='x',project='Fixture',title='Fixture task',body='',section='ted_doing',decision_kind='other',updated_at='2026-10-20T00:00:00Z')

def call(action,**body):
 requests.append((action,body));return dict(ok=True,card=dict(current,section=body.get('section',current['section'])))

client=types.SimpleNamespace(BoardConflict=RuntimeError,BoardGone=LookupError,RuleResolutionRequired=RuntimeError,
 call=call,cards=lambda:[dict(current)],resolve_rule=Mock(side_effect=AssertionError('operational failure must not resolve a Sebastian ask')),
 DECISION_KINDS=('send_email','spend_money','approve_design','other'))
sys.modules['board_client']=client
import reconciler_status as live
sys.modules['live_status']=live
import reconciler_sessions as sessions
import reconciler_runtime as runtime


class ManagedFailureRouting(unittest.TestCase):
 def setUp(self):
  requests.clear();client.resolve_rule.reset_mock()
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.store=sessions.Store(self.temp.name)
  mode=patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'true'});mode.start();self.addCleanup(mode.stop)
  for owner,name,value in ((sessions,'admission_state',dict(cap=0)),(sessions,'alive',False)):
   p=patch.object(owner,name,return_value=value);p.start();self.addCleanup(p.stop)

 def running(self):
  self.store.enqueue(dict(current),'work','fixture',engine='codex')
  with self.store.locked() as data:
   s=data['sessions']['x'];turn=s['queue'].pop(0)
   s.update(status='running',turn=turn['id'],active_turn=turn,pid=98765,identity='fixture',lease_token='f',lease_expires_at=1800000000,
    lease=dict(token='f',turn=turn['id'],pid=98765,identity='fixture',expires_at=1800000000,renewed_at=1700000000))
  return self.store.read()['sessions']['x']

 def assert_no_inbox(self):
  client.resolve_rule.assert_not_called()
  for action,body in requests:
   self.assertNotEqual(body.get('section'),'needs_you',(action,body))
   self.assertNotEqual(body.get('state'),'waiting_on_you',(action,body))
   self.assertNotIn('ask_anyway_reason',body)

 def test_worker_error_status_requests_are_forced_to_ted(self):
  for text in ('Worker exceeded the twelve-hour limit. Reply to continue.','Worker stopped without a final result. Reply to retry.',
               'Worker could not start. Reply to retry.','Worker failed: crash. Reply to retry.'):
   for kind in ('other','send_email','spend_money'):
    with self.subTest(text=text,kind=kind),patch.dict(current,decision_kind=kind):
     live.update('x','waiting_on_you',text,section='needs_you')
     self.assertEqual(requests[-1][1]['section'],'up_next')
  self.assert_no_inbox()

 def test_current_result_failures_publish_blocked_ted_recovery(self):
  for kind,text in [('timeout','worker exceeded the twelve-hour limit'),('no_result','worker returned no final answer'),('crash','worker failed')]:
   with self.subTest(kind=kind):
    # Each independent card execution gets its own empty fixture store.
    self.store=sessions.Store(Path(self.temp.name)/kind)
    s=self.running()
    result=dict(ok=False,text=text,failure_kind=kind,lease_token='f',turn=s['turn'],pid=s['pid'],identity=s['identity'])
    sessions.atomic(Path(s['cwd'])/(s['turn']+'.result.json'),result)
    self.store.tick(reconcile=True)
    saved=self.store.read()
    self.assertEqual(saved['sessions']['x']['status'],'failed')
    self.assertEqual(requests[-1][1]['section'],'up_next')
    self.assertEqual(requests[-1][1]['state'],'blocked')
    self.assertEqual(len(saved['ted_outbox']),1)
    self.assertEqual(saved['outbox'],[])
  self.assert_no_inbox()

 def test_failed_launch_never_creates_an_inbox_ask(self):
  self.store.enqueue(dict(current),'work','fixture',engine='codex')
  with patch.object(sessions,'admission_state',return_value=dict(cap=64)),patch.object(sessions.subprocess,'Popen',side_effect=OSError):
   self.store.tick(reconcile=True)
  self.assertEqual(self.store.read()['sessions']['x']['status'],'failed')
  self.assertEqual(requests[-1][1]['section'],'up_next');self.assert_no_inbox()

 def test_dead_letter_note_is_durable_deduplicated_and_owned_by_ted(self):
  s=self.running()
  with self.store.locked() as data:data['sessions']['x'].update(status='failed',retry_count=2)
  action=dict(id='dlq',kind='dead_letter',entity='x',payload=dict(card_id='x',expected_turn=s['turn'],expected_lease_token='f'))
  with patch.dict(sys.modules,{'sessions':sessions}),patch.object(runtime,'confirmed_stop',return_value=True):
   self.assertTrue(runtime.execute(action,self.store,{},None))
   self.assertTrue(runtime.execute(action,self.store,{},None))
  data=self.store.read();self.assertEqual(data['sessions']['x']['status'],'dead_letter')
  self.assertEqual(len(data['ted_outbox']),1)
  self.assertEqual(data['outbox'],[])
  snapshot=dict(cards=[dict(current)],sessions=data['sessions'],approvals=[],mockups=[],workflows={},coverage={})
  plan=runtime.plan(snapshot,now=1800000100)
  self.assertTrue(all(x['owner']=='ted' for x in plan['items'] if x.get('card_id')=='x'))
  self.assertFalse(any(a['kind']=='sebastian_escalation' for a in plan['actions']))
  self.assert_no_inbox()

 def test_unsafe_approval_artifact_is_operational_and_cannot_request_approval(self):
  self.store.enqueue(dict(current),'work','fixture',engine='codex')
  with self.store.locked() as data:
   s=data['sessions']['x'];self.store._fail_artifact(data,s);self.store._publish_failure(s,data)
  self.store._flush_publications()
  self.assertEqual(requests[-1][1]['section'],'up_next');self.assert_no_inbox()

 def test_failure_note_on_an_existing_needs_you_card_is_never_delivered_to_it(self):
  self.store.enqueue(dict(current),'work','fixture',engine='codex')
  with self.store.locked() as data:
   session=data['sessions']['x']
   self.store._out(data,session,'Ted owns this worker failure','worker-failure-fixture')
  with patch.dict(current,section='needs_you',decision_kind='spend_money'),patch.object(sessions,'deliver',side_effect=AssertionError('failure must not enter Sebastian inbox')):
   self.store.flush()
  data=self.store.read()
  self.assertEqual(data['outbox'],[])
  self.assertEqual(len(data['ted_outbox']),1)
  self.assertEqual(data['ted_outbox'][0]['owner'],'ted')

 def test_legacy_failure_outbox_is_quarantined_before_delivery(self):
  with self.store.locked() as data:
   data['outbox'].append(dict(card_id='x',token='legacy-turn',text='Worker failed: crash. Reply to retry.'))
  with patch.object(sessions,'deliver',side_effect=AssertionError('legacy failure must not enter Sebastian inbox')):
   self.store.flush()
   self.store.flush()
  data=self.store.read();self.assertEqual(data['outbox'],[])
  self.assertEqual(len(data['ted_outbox']),1)

 def test_send_spend_and_review_failures_are_never_automatically_retried(self):
  for fields in (dict(reviewing='approval'),dict(side_effecting=True),dict(active_turn=dict(veto_proposal_id='v'))):
   snapshot=dict(cards=[dict(current)],sessions={'x':dict(status='failed',turn='t',lease_token='f',**fields)},approvals=[],mockups=[],workflows={},coverage={})
   self.assertNotIn('retry',[a['kind'] for a in runtime.plan(snapshot,now=1800000000)['actions']])
  self.assert_no_inbox()


if __name__=='__main__':unittest.main()
