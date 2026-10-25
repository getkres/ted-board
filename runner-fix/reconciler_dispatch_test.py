import reconciler_test_support
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import reconciler as r
import reconciler_runtime as d

NOW=1800000000

def snapshot(**card_fields):
 card=dict(id='direct',project='Fixture',title='Work',section='up_next',created_at=r.iso(NOW-100),updated_at=r.iso(NOW-10),**card_fields)
 return dict(cards=[card],sessions={},approvals=[],mockups=[],prs={},workflows={},coverage={})

def dispatches(value):return [a for a in r.plan(value,now=NOW)['actions'] if a['kind']=='dispatch']

class DispatchPolicy(unittest.TestCase):
 def test_missing_empty_or_malformed_policy_never_starts_new_work(self):
  for policy in (None,{},dict(allow_card_ids=[]),dict(allow_card_ids=True),dict(allow_card_ids=['direct'],hold_card_ids='direct')):
   value=snapshot();value['dispatch_policy']=policy
   with self.subTest(policy=policy):self.assertEqual(dispatches(value),[])
 def test_allowlist_is_exact_and_holds_override_permission(self):
  for fields,held,expected in (({},[],1),({},['direct'],0),({'metadata':{'reconciler_hold':True}},[],0),({'live_state':'running'},[],0)):
   value=snapshot(**fields);value['dispatch_policy']=dict(allow_card_ids=['direct'],hold_card_ids=held)
   self.assertEqual(len(dispatches(value)),expected,(fields,held))
  value=snapshot();value['dispatch_policy']=dict(allow_card_ids=['another'],hold_card_ids=[])
  self.assertEqual(dispatches(value),[])
 def test_active_external_job_blocks_even_an_allowlisted_card(self):
  value=snapshot();value['dispatch_policy']=dict(allow_card_ids=['direct'],hold_card_ids=[])
  value['external_jobs']=[dict(id='outside',card_id='direct',status='running')]
  self.assertEqual(dispatches(value),[])
 def test_observation_reads_empty_default_and_exact_configured_dispatch_policy(self):
  board=types.SimpleNamespace(call=lambda **kw:dict(jobs=[],reconciliation_error='not_published') if kw.get('resource') else dict(cards=[]))
  mockups=types.SimpleNamespace(call=lambda:dict(mockups=[]))
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'jobs').mkdir();(root/'jobs/sessions.json').write_text('{"sessions":{},"approvals":{}}')
   self.assertEqual(d.observe(root,board=board,mockups=mockups)['dispatch_policy'],dict(allow_card_ids=[],hold_card_ids=[]))
   (root/'jobs/reconciler-config.json').write_text(json.dumps(dict(enabled=True,dispatch=dict(allow_card_ids=['direct'],hold_card_ids=['parked']))))
   self.assertEqual(d.observe(root,board=board,mockups=mockups)['dispatch_policy'],dict(allow_card_ids=['direct'],hold_card_ids=['parked']))
 def test_dispatch_rechecks_a_card_that_started_direct_work_after_planning(self):
  value=snapshot();value['dispatch_policy']=dict(allow_card_ids=['direct'],hold_card_ids=[])
  store=types.SimpleNamespace(enqueue=Mock(side_effect=AssertionError('duplicate start')))
  board=types.SimpleNamespace(call=lambda **kw:dict(cards=[dict(value['cards'][0],live_state='running')]))
  action=dict(id='start',kind='dispatch',payload=dict(card_id='direct'))
  self.assertFalse(d.execute(action,store,value,board));store.enqueue.assert_not_called()

class DispatchEffectPolicy(unittest.TestCase):
 def test_dispatch_reloads_revoked_local_permission_before_enqueue(self):
  value=snapshot();value['dispatch_policy']=dict(allow_card_ids=['direct'],hold_card_ids=[])
  board=types.SimpleNamespace(call=lambda **kw:dict(jobs=[]) if kw.get('resource') else dict(cards=value['cards']))
  action=dict(id='start',kind='dispatch',payload=dict(card_id='direct'))
  with tempfile.TemporaryDirectory() as temp:
   store=types.SimpleNamespace(root=Path(temp),enqueue=Mock(return_value=True))
   for allowed,want in (([],False),(['direct'],True)):
    (Path(temp)/'reconciler-config.json').write_text(json.dumps(dict(enabled=True,dispatch=dict(allow_card_ids=allowed,hold_card_ids=[]))))
    self.assertEqual(d.execute(action,store,value,board),want)
   self.assertEqual(store.enqueue.call_count,1)

if __name__=='__main__':unittest.main()
