"""Stale publication defers safely, and diagnostics never echo private transport data."""
import reconciler_test_support
import contextlib
import copy
import importlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
import urllib.error
from unittest.mock import Mock, patch
import reconciler_runtime as runtime

try:
 import reconciler_transport as transport
except ImportError:
 transport=None

NOW=1800000000


def snapshot():
 return dict(cards=[dict(id='fixture-card',title='fixture',project='fixture',section='ted_doing',
  created_at='2027-01-14T00:00:00Z',updated_at='2027-01-15T07:00:00Z')],
  sessions={},approvals=[],mockups=[],prs={},workflows={},
  coverage={key:'ok' for key in ('cards','backend_ledger','inbox_policy','remote_jobs')})


class ConflictTests(unittest.TestCase):
 def setUp(self):self.assertIsNotNone(transport,'managed transport with safe status metadata is missing')

 def test_conflict_defers_before_journal_or_actions_without_replaying_payload(self):
  board=types.SimpleNamespace(call=Mock(side_effect=transport.BoardConflict()))
  with tempfile.TemporaryDirectory() as temp,patch.object(runtime,'execute',side_effect=AssertionError('stale action')):
   journal=Path(temp,'journal.db')
   result=runtime.run(snapshot(),journal,NOW,False,object(),board)
   self.assertFalse(result['applied']);self.assertTrue(result['publication_skipped'])
   self.assertEqual(result['publication_deferred'],'conflict');self.assertEqual(result['selected_actions'],[])
   self.assertFalse(journal.exists());self.assertEqual(board.call.call_count,1)

 def test_existing_receipts_survive_conflict_and_next_invocation_observes_a_fresh_payload(self):
  board=types.SimpleNamespace(call=Mock(side_effect=[transport.BoardConflict(),dict(ok=True)]))
  with tempfile.TemporaryDirectory() as temp,patch.object(runtime,'execute',return_value=True):
   journal=Path(temp,'journal.db')
   with runtime.Journal(journal) as j:j.complete('existing',dict(kind='fixture'))
   before=journal.read_bytes()
   runtime.run(snapshot(),journal,NOW,False,object(),board)
   self.assertEqual(journal.read_bytes(),before)
   fresh=copy.deepcopy(snapshot());fresh['cards'][0]['updated_at']='2027-01-15T07:01:00Z'
   result=runtime.run(fresh,journal,NOW+120,False,object(),board)
   self.assertTrue(result['applied']);self.assertEqual(board.call.call_count,2)
   first,second=board.call.call_args_list
   self.assertNotEqual(first.kwargs['generated_at'],second.kwargs['generated_at'])
   self.assertNotEqual(first.kwargs['items'][0]['expected_updated_at'],second.kwargs['items'][0]['expected_updated_at'])
   self.assertIn('existing',runtime.completed_readonly(journal))

 def test_main_conflict_skips_all_lifecycle_and_archive_effects_but_returns_successful_deferral(self):
  store=Mock();board=types.SimpleNamespace(call=Mock(side_effect=[dict(commands=[]),transport.BoardConflict()]))
  def imported(name):return types.SimpleNamespace(Store=lambda root:store) if name=='reconciler_sessions' else board
  with tempfile.TemporaryDirectory() as temp,patch.dict(runtime.os.environ,{'TED_RECONCILER_ENABLED':'true','TED_MOCKUP_AUTOARCHIVE_ENABLED':'true'}),patch.object(runtime.socket,'gethostname',return_value='test-mini'),patch.object(runtime.importlib,'import_module',side_effect=imported),patch.object(runtime,'observe',return_value=snapshot()),patch.object(runtime,'sample_health',return_value={}),contextlib.redirect_stdout(io.StringIO()) as out:
   Path(temp,'jobs').mkdir();self.assertEqual(runtime.main(['--root',temp,'--apply']),0)
   summary=json.loads(out.getvalue());self.assertEqual(summary['publication'],'deferred_conflict')
   self.assertFalse(Path(temp,'jobs/reconciler.sqlite').exists())
  for method in ('tick','collect_approvals','sync_approval_status','flush'):getattr(store,method).assert_not_called()
  self.assertEqual(board.call.call_count,2)

 def test_real_publish_failure_keeps_sanitized_stage_and_status_and_never_opens_journal(self):
  board=types.SimpleNamespace(call=Mock(side_effect=transport.BoardTransportError('http',503)))
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp,'journal.db')
   with self.assertRaises(runtime.ReconcilerFailure) as got:runtime.run(snapshot(),path,NOW,False,object(),board)
   self.assertEqual(got.exception.diagnostic(),dict(event='reconciler_failed',stage='publish',error_kind='http',http_status=503))
   self.assertFalse(path.exists());self.assertEqual(board.call.call_count,1)

 def test_cli_diagnostics_allowlist_stage_category_and_status_without_echoing_exception_text(self):
  secret='private key https://example.invalid/?key=private card body'
  for failure,expected in [(RuntimeError(secret),dict(event='reconciler_failed',stage='startup',error_kind='exception',http_status=None)),
    (runtime.ReconcilerFailure('publish',transport.BoardTransportError('http',504)),dict(event='reconciler_failed',stage='publish',error_kind='http',http_status=504)),
    (runtime.ReconcilerFailure(secret,types.SimpleNamespace(kind=secret,http_status=secret)),dict(event='reconciler_failed',stage='unknown',error_kind='exception',http_status=None))]:
   with patch.object(runtime,'main',side_effect=failure),contextlib.redirect_stderr(io.StringIO()) as out:
    self.assertEqual(runtime.cli([]),1);self.assertEqual(json.loads(out.getvalue()),expected)
    self.assertNotIn('private',out.getvalue());self.assertNotIn('example.invalid',out.getvalue())

 def test_diagnostic_metadata_with_unexpected_types_cannot_break_failure_reporting(self):
  failure=runtime.ReconcilerFailure(['private stage'],types.SimpleNamespace(kind={'private':'category'},http_status=True))
  self.assertEqual(failure.diagnostic(),dict(event='reconciler_failed',stage='unknown',error_kind='exception',http_status=None))


class TransportTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(transport,'managed transport with safe status metadata is missing')
  self.env=types.SimpleNamespace(ENDPOINT='https://fixture.invalid/functions/v1/ted-board',load_env=lambda:dict(TED_DECISIONS_KEY='page-fixture',TED_DECISIONS_WORKER_KEY='worker-fixture'))

 def test_http_conflict_and_gone_keep_numeric_status_without_response_body_or_same_payload_retry(self):
  for status,want in [(409,transport.BoardConflict),(404,transport.BoardGone),(503,transport.BoardTransportError)]:
   error=urllib.error.HTTPError('https://private.invalid/?key=secret',status,'private detail',{},io.BytesIO(b'private response'))
   with patch.dict(sys.modules,{'sync':self.env}),patch('urllib.request.urlopen',side_effect=error) as request:
    with self.assertRaises(want) as got:transport.call('reconcile_publish',items=[])
   self.assertEqual(got.exception.http_status,status);self.assertEqual(got.exception.kind,'http')
   self.assertNotIn('private',str(got.exception));self.assertEqual(request.call_count,1)

 def test_timeout_and_network_failure_have_fixed_categories_and_one_attempt(self):
  for error,kind in [(socket.timeout('private host'), 'timeout'),(urllib.error.URLError(socket.timeout('private host')),'timeout'),(urllib.error.URLError('private host'),'transport')]:
   with patch.dict(sys.modules,{'sync':self.env}),patch('urllib.request.urlopen',side_effect=error) as request:
    with self.assertRaises(transport.BoardTransportError) as got:transport.call('reconcile_publish',items=[])
   self.assertEqual(got.exception.kind,kind);self.assertIsNone(got.exception.http_status)
   self.assertNotIn('private',str(got.exception));self.assertEqual(request.call_count,1)

 def test_get_page_auth_and_post_worker_auth_preserve_wire_shape_and_timeout(self):
  for action,page,want in [(None,False,'page-fixture'),('reconcile_publish',False,'worker-fixture'),('example',True,'page-fixture')]:
   response=io.BytesIO(b'{"ok":true}')
   with patch.dict(sys.modules,{'sync':self.env}),patch('urllib.request.urlopen',return_value=response) as request:
    self.assertEqual(transport.call(action,page=page,resource='jobs'),dict(ok=True))
   sent=request.call_args.args[0];self.assertEqual(request.call_args.kwargs['timeout'],25)
   if action is None:self.assertEqual(sent.method,'GET');self.assertIn('key='+want,sent.full_url)
   else:self.assertEqual(sent.method,'POST');self.assertEqual(json.loads(sent.data),dict(key=want,action=action,resource='jobs'))

 def test_invalid_response_and_credentials_are_sanitized(self):
  for raw in (b'private invalid json',b'[]'):
   with patch.dict(sys.modules,{'sync':self.env}),patch('urllib.request.urlopen',return_value=io.BytesIO(raw)):
    with self.assertRaises(transport.BoardTransportError) as got:transport.call()
   self.assertEqual(got.exception.kind,'response');self.assertNotIn('private',str(got.exception))
  self.env.load_env=Mock(side_effect=OSError('private secret path'))
  with patch.dict(sys.modules,{'sync':self.env}),patch('urllib.request.urlopen',side_effect=AssertionError('no credential request')):
   with self.assertRaises(transport.BoardTransportError) as got:transport.call()
  self.assertEqual(got.exception.kind,'credentials');self.assertNotIn('private',str(got.exception))


if __name__=='__main__':unittest.main()
