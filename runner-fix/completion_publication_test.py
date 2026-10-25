#!/usr/bin/env python3
"""Completion delivery ACKs with isolated files and fully stubbed providers."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

SOURCE=None

class CompletionPublicationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.calls=[]
  client=types.ModuleType('board_client');client.BoardConflict=RuntimeError;client.BoardGone=LookupError
  client.call=lambda *a,**k:self.fail('unstubbed provider access')
  live=types.ModuleType('live_status');live.instructions=lambda *a:'';live.publish_live=lambda *a,**k:False
  modules=mock.patch.dict(sys.modules,board_client=client,live_status=live);modules.start();self.addCleanup(modules.stop)
  spec=importlib.util.spec_from_file_location('isolated_completion_sessions',SOURCE/'reconciler_sessions.py')
  self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
  self.store=self.module.Store(self.root/'jobs')
  self.session=dict(card_id='sample',status='done',queue=[],pid=None,turn='turn',lease_token='fence',identity='old worker',
                    lease=dict(token='fence',turn='turn',pid=12345,identity='old worker'))
  with self.store.locked() as data:
   data['sessions']['sample']=copy.deepcopy(self.session)
   self.store._queue_publication(data,self.session,'blocked','ted review','complete',section='up_next')
   data['ted_outbox']=[dict(card_id='sample',text='retained review note')];data['review_queue']=['preserved']
  self.card=dict(id='sample',project='example',section='up_next',live_state='blocked',live_status='ted review',decision_kind=None)
  self.response=dict(cards=[self.card]);self.publish_effect=lambda *a,**k:False
  def get(*a,**k):
   self.calls.append((a,k));self.assertEqual(a,());self.assertEqual(k,dict(page=True));return copy.deepcopy(self.response)
  self.get_effect=get
  self.ps_result=types.SimpleNamespace(returncode=0,stdout='1 1 S\n')
  self.patches=[mock.patch.object(self.module,'publish_live',side_effect=lambda *a,**k:self.publish_effect(*a,**k)),
                mock.patch.object(self.module,'call',side_effect=lambda *a,**k:self.get_effect(*a,**k)),
                mock.patch.object(self.module.subprocess,'run',side_effect=lambda *a,**k:self.ps_result),
                mock.patch.object(self.module.subprocess,'Popen',side_effect=AssertionError('model launch forbidden'))]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def flush(self):self.store._flush_publications();return self.store.read()
 def mutate(self,fn):
  with self.store.locked() as data:fn(data)
 def test_failed_publish_acks_exact_existing_target_without_card_write(self):
  result=self.flush()
  self.assertFalse(result['publications']);self.assertEqual(len(self.calls),1)
  self.assertEqual(result['sessions']['sample'],self.session)
  self.assertEqual(result['ted_outbox'],[dict(card_id='sample',text='retained review note')]);self.assertEqual(result['review_queue'],['preserved'])
 def test_existing_successful_publish_still_uses_normal_ack(self):
  self.publish_effect=lambda *a,**k:True
  self.assertFalse(self.flush()['publications']);self.assertFalse(self.calls)
 def test_snapshot_failures_and_ambiguity_remain_pending(self):
  invalid=[None,{},dict(ok=False,cards=[self.card]),dict(truncated=True,cards=[self.card]),dict(has_more=True,cards=[self.card]),dict(error='refused',cards=[self.card]),dict(cards='bad'),dict(cards=[]),dict(cards=[self.card,self.card]),
           dict(cards=[self.card]*500),dict(cards=[dict(self.card,section='ted_doing')]),dict(cards=[dict(self.card,live_state='done')]),
           dict(cards=[dict(self.card,live_status='different')]),dict(cards=[dict(self.card,decision_kind='send_email')]),
           dict(cards=[dict(self.card,classification_uncertain=True)]),dict(cards=[dict(self.card,pending_approval=True)]),
           dict(cards=[dict(self.card,approval='malformed')]),dict(cards=[dict(self.card,veto_status='cleared')]),
           dict(cards=[dict(self.card,inbox_decision='copy')]),dict(cards=[dict(self.card,options=['approve'])]),
           dict(cards=[dict(self.card,steps=['send'])]),dict(cards=[{k:v for k,v in self.card.items() if k!='decision_kind'}])]
  original=self.store.read()
  for response in invalid:
   with self.subTest(response=response):
    self.mutate(lambda d:(d.clear(),d.update(copy.deepcopy(original))))
    self.response=response;self.assertTrue(self.flush()['publications'])
 def test_invalid_lease_or_local_schema_refuses_fallback(self):
  original=self.store.read()
  for change in (dict(lease=None),dict(lease=dict(pid=12345,turn='turn',token='fence',identity='changed')),dict(lease=dict(pid='12345')),dict(lease=dict(pid=12345,turn='other',token='fence')),dict(queue=None)):
   with self.subTest(change=change):
    self.mutate(lambda d:(d.clear(),d.update(copy.deepcopy(original))))
    self.mutate(lambda d:d['sessions']['sample'].update(change));self.assertTrue(self.flush()['publications'])
 def test_process_probe_errors_refuse_fallback(self):
  with mock.patch.object(self.module.subprocess,'run',side_effect=OSError('fixture')):
   self.assertTrue(self.flush()['publications']);self.assertEqual(self.calls,[((),dict(page=True))])
 def test_noncompletion_target_shape_never_uses_fallback(self):
  original=self.store.read()
  for change in (dict(state='running'),dict(line='other'),dict(kwargs=dict(section='needs_you')),dict(status='failed')):
   with self.subTest(change=change):
    self.mutate(lambda d:(d.clear(),d.update(copy.deepcopy(original))))
    self.mutate(lambda d:d['publications']['sample'].update(change))
    with mock.patch.object(self.module,'publish_live',side_effect=AssertionError('invalid completion must stay local')):
     self.assertTrue(self.flush()['publications'])
  self.assertFalse(self.calls)
 def test_get_errors_remain_pending(self):
  for exception in (OSError('fixture'),RuntimeError('fixture'),ValueError('fixture'),TypeError('fixture')):
   with self.subTest(exception=type(exception).__name__):
    self.get_effect=lambda *a,**k:(_ for _ in ()).throw(exception)
    self.assertTrue(self.flush()['publications'])
 def test_local_unsafe_states_do_not_publish_or_ack(self):
  changes=[dict(status='queued'),dict(queue=[dict(id='next')]),dict(pid=678),dict(stop_requested=True),dict(kill_requested_at=1),
           dict(reviewing='approval'),dict(review_context='protected'),dict(active_veto_revision=2),dict(veto_outcome=dict(status='sent')),
           dict(active_turn=dict(kind='review')),dict(side_effecting=True),dict(failure_publish_pending=True)]
  original=self.store.read()
  for changeset in changes:
   with self.subTest(change=changeset):
    self.mutate(lambda d:(d.clear(),d.update(copy.deepcopy(original))))
    self.mutate(lambda d:d['sessions'].__setitem__('sample',dict(self.session,**changeset)))
    with mock.patch.object(self.module,'publish_live',side_effect=AssertionError('unsafe completion must stay local')):
     self.assertTrue(self.flush()['publications'])
  self.assertFalse(self.calls)
 def test_live_old_worker_or_group_and_unknown_census_refuse_ack(self):
  for response in (types.SimpleNamespace(returncode=0,stdout='12345 12345 S\n'),types.SimpleNamespace(returncode=0,stdout='12346 12345 S\n'),
                   types.SimpleNamespace(returncode=1,stdout=''),types.SimpleNamespace(returncode=0,stdout='malformed'),types.SimpleNamespace(returncode=0,stdout='1 1 123')):
   with self.subTest(response=response):self.ps_result=response;self.assertTrue(self.flush()['publications'])
 def test_pending_local_approval_refuses_ack(self):
  self.mutate(lambda d:d['approvals'].update(a=dict(card_id='sample',status='approved')))
  self.assertTrue(self.flush()['publications']);self.assertFalse(self.calls)
 def test_concurrent_session_or_record_changes_are_not_acked(self):
  original=self.store.read()
  for change in (lambda d:d['sessions']['sample'].update(queue=[dict(id='new')]),lambda d:d['sessions']['sample'].update(turn='new'),
                 lambda d:d['sessions']['sample'].update(lease_token='new'),lambda d:d['sessions']['sample'].update(status='running'),
                 lambda d:d['sessions']['sample'].update(last_activity=123),lambda d:d['publications']['sample'].update(line='new'),
                 lambda d:d['approvals'].update(a=dict(card_id='sample',status='pending'))):
   with self.subTest(change=change):
    self.mutate(lambda d:(d.clear(),d.update(copy.deepcopy(original))))
    def get(*a,**k):self.mutate(change);return copy.deepcopy(self.response)
    self.get_effect=get;result=self.flush();self.assertTrue(result['publications'])
 def test_successful_publish_cannot_ack_a_concurrently_changed_completion(self):
  def publish(*a,**k):self.mutate(lambda d:d['sessions']['sample'].update(queue=[dict(id='new')]));return True
  self.publish_effect=publish;self.assertTrue(self.flush()['publications'])
 def test_other_publication_kinds_never_use_target_fallback(self):
  for kind in ('failure','admission','start','resume','unknown'):
   with self.subTest(kind=kind):
    self.mutate(lambda d:d['publications']['sample'].update(kind=kind))
    self.flush();self.assertFalse(self.calls)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--runtime-root',type=Path,required=True);args,rest=p.parse_known_args()
 SOURCE=args.runtime_root.resolve();sys.path.insert(0,str(SOURCE));unittest.main(argv=[sys.argv[0],*rest])
