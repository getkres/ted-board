"""Regression cases from PR45-REVIEW-1024.md, with forbidden external effects."""
import reconciler_test_support
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import reconciler_runtime as d
import runner_admission as admission

NOW=1800000000


class FreshRuntimeReview(unittest.TestCase):
 def test_malformed_enable_config_warns_and_leaves_legacy_disabled(self):
  with tempfile.TemporaryDirectory() as temp,patch.dict(admission.os.environ,{'TED_RECONCILER_ENABLED':'false'}):
   path=Path(temp)/'enable.json'
   for content in ('{','{"enabled":"yes"}','[]'):
    path.write_text(content)
    with self.subTest(content=content):self.assertFalse(admission.reconciler_enabled(path))
 def test_bad_config_blocks_apply_even_with_enable_environment_override(self):
  with tempfile.TemporaryDirectory() as temp,patch.dict(admission.os.environ,{'TED_RECONCILER_ENABLED':'true'}):
   root=Path(temp);(root/'jobs').mkdir();(root/'jobs/reconciler-config.json').write_text('{')
   with patch.object(d.importlib,'import_module',side_effect=AssertionError('must not construct an effect adapter')):
    with self.assertRaisesRegex(RuntimeError,'configuration'):d.main(['--apply','--root',temp])

 def test_health_counts_distinct_misses_and_resets_on_activity_or_live_pid(self):
  data={'sessions':{'c':dict(status='running',turn='t',cwd='/nonexistent',pid=100,identity='i',lease_token='f',lease_expires_at=NOW-500,lease=dict(renewed_at=NOW-650))}}
  held=[]
  @contextlib.contextmanager
  def locked():
   held.append(True)
   try:yield data
   finally:held.pop()
  def dead(*args):
   self.assertFalse(held);return False
  store=types.SimpleNamespace(locked=locked)
  with patch.dict(sys.modules,{'sessions':types.SimpleNamespace(alive=dead)}),patch.object(d,'activity_stamp',return_value=0):
   for n in range(3):
    d.sample_health(store,NOW+n*120)
    self.assertEqual(data['sessions']['c']['missed_renewals'],n+1)
   d.sample_health(store,NOW+241)
   self.assertEqual(data['sessions']['c']['missed_renewals'],3)
  with patch.dict(sys.modules,{'sessions':types.SimpleNamespace(alive=dead)}),patch.object(d,'activity_stamp',return_value=NOW+250):
   d.sample_health(store,NOW+360)
   self.assertEqual(data['sessions']['c']['missed_renewals'],0)
   self.assertFalse(data['sessions']['c']['activity_quiet'])
  with patch.dict(sys.modules,{'sessions':types.SimpleNamespace(alive=lambda *a:True)}),patch.object(d,'activity_stamp',return_value=0):
   d.sample_health(store,NOW+480)
   self.assertEqual(data['sessions']['c']['missed_renewals'],0)
   self.assertFalse(data['sessions']['c']['pid_dead'])

 def test_apply_refuses_lease_less_cutover_before_any_remote_mutation(self):
  snapshot=dict(cards=[],sessions={'live':dict(status='running',turn='t',pid=100)},coverage=dict(backend_ledger='ok',inbox_policy='ok',remote_jobs='ok'))
  board=types.SimpleNamespace(call=Mock(side_effect=AssertionError('remote effect forbidden')))
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaisesRegex(RuntimeError,'lease'):
    d.run(snapshot,Path(temp)/'journal.db',NOW,False,object(),board)
   board.call.assert_not_called()
 def test_500_card_feed_is_partial_coverage_and_keeps_local_sessions(self):
  cards=[dict(id='c'+str(n),title='fixture',section='up_next') for n in range(500)]
  board=types.SimpleNamespace(call=lambda **k:dict(jobs=[],reconciliation_error='not_published') if k else dict(cards=cards))
  mockups=types.SimpleNamespace(call=lambda:dict(mockups=[]))
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'jobs').mkdir();(root/'jobs/sessions.json').write_text(json.dumps(dict(sessions={'c0':dict(status='running',turn='t',lease_token='f')})))
   snapshot=d.observe(root,board=board,mockups=mockups)
   self.assertEqual(snapshot['coverage']['cards'],'truncated')
   self.assertIn('c0',snapshot['sessions'])
 def test_bad_card_row_is_partial_coverage_instead_of_stopping_observation(self):
  board=types.SimpleNamespace(call=lambda **k:dict(jobs=[],reconciliation_error='not_published') if k else dict(cards=[dict(id='valid',title='fixture'),None]))
  mockups=types.SimpleNamespace(call=lambda:dict(mockups=[]))
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'jobs').mkdir();(root/'jobs/sessions.json').write_text('{"sessions":{}}')
   snapshot=d.observe(root,board=board,mockups=mockups)
   self.assertEqual(snapshot['coverage']['cards'],'invalid_rows')
   self.assertEqual([c['id'] for c in snapshot['cards']],['valid'])

 def test_partial_card_feed_runs_confirmed_local_recovery_without_publish_or_dispatch(self):
  actions=[dict(id='retry',kind='retry',entity='c',payload=dict(card_id='c')),dict(id='dispatch',kind='dispatch',entity='new',payload=dict(card_id='new'))]
  result=dict(generated_at=d.iso(NOW),items=[],ted_queue=[],banner=True,coverage_defects=['cards'],actions=actions)
  snapshot=dict(cards=[],sessions={},coverage=dict(cards='truncated',backend_ledger='ok',inbox_policy='ok',remote_jobs='ok'))
  seen=[];board=types.SimpleNamespace(call=Mock(side_effect=AssertionError('partial remote effect forbidden')))
  with tempfile.TemporaryDirectory() as temp,patch.object(d,'plan',return_value=result),patch.object(d,'execute',side_effect=lambda a,*args:seen.append(a['kind']) or True):
   out=d.run(snapshot,Path(temp)/'journal.db',NOW,False,object(),board)
   self.assertEqual(seen,['retry']);self.assertTrue(out['publication_skipped']);board.call.assert_not_called()
 def test_recovery_observation_and_explicit_stop_run_outside_the_store_lock(self):
  session=dict(turn='t',lease_token='f',status='failed',cwd='/nonexistent',retry_count=0,pid_dead=True,activity_quiet=True,missed_renewals=3)
  data={'sessions':{'c':session}};held=[]
  @contextlib.contextmanager
  def locked():
   held.append(True)
   try:yield data
   finally:held.pop()
  store=types.SimpleNamespace(locked=locked)
  def stop(*args,**kwargs):
   self.assertFalse(held,'process observation held the lease lock');return True
  action=dict(id='r',kind='retry',entity='c',payload=dict(card_id='c',expected_turn='t',expected_lease_token='f',attempt=1,retry_at=d.iso(NOW)))
  with patch.dict(sys.modules,{'sessions':types.SimpleNamespace(matching_result=lambda *a:False)}),patch.object(d,'confirmed_stop',side_effect=stop):
   self.assertTrue(d.execute(action,store,{},None))
 def test_automatic_recovery_never_signals_a_live_pid(self):
  kill=Mock(return_value=True)
  with patch.dict(sys.modules,{'sessions':types.SimpleNamespace(alive=lambda *a:True,safe_kill=kill)}),patch.object(d,'group_members',return_value=[100]),patch.object(d.time,'sleep'):
   self.assertFalse(d.confirmed_stop(dict(pid=100,identity='fixture')))
   kill.assert_not_called()


if __name__=='__main__':unittest.main()
