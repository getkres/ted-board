"""Entry-point regression tests. Every remote side effect is mocked."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_status
import mockup_upload
import sessions
from review_gate import ReviewBlocked
try: import reconciler_card
except ImportError: reconciler_card = None
from review_unit_fixtures import collect_approvals, status_module


class AdapterTests(unittest.TestCase):
    def test_routine_handoff_cannot_publish_unreviewed_approvals(self):
        if not hasattr(sessions.Store, 'record_output'):
            self.skipTest('current private routine handoff not installed')
        for name in ('draft-email.json', 'spend.json', 'apply.sql'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                store = sessions.Store(tmp)
                store.record_output({'id': 'routine', 'title': 'Routine output',
                                     'body': 'Review the exact proposal.', 'project': 'Ted ops'},
                                    {'REPORT.md': 'Routine proposal.\n', name: '{}'}, 'needs_approval')
                collect_approvals(store)
                self.assertEqual(store.snapshot()[1], [])
                self.assertEqual(store.read()['approvals'], {})
                self.assertEqual(store.read()['sessions']['routine']['status'], 'review_blocked')

    def test_oversized_unreviewed_packet_keeps_bounded_draft_recovery(self):
        try:
            import reconciler_sessions as managed
        except ImportError:
            self.skipTest('current private reconciler not installed')
        with tempfile.TemporaryDirectory() as tmp, patch.object(managed, 'reconciler_enabled', return_value=True):
            store = managed.Store(tmp)
            store.enqueue({'id': 'repair', 'title': 'Prepare a packet'}, 'work', 'receipt')
            with store.locked() as data:
                session = data['sessions']['repair']
                session.update(status='done', queue=[], turn='maker-turn')
                packet = Path(session['cwd']) / 'apply.sql'
                packet.write_text('x' * 60001)
            store.collect_approvals(reconcile=True)
            session = store.read()['sessions']['repair']
            self.assertEqual(session['status'], 'queued')
            self.assertEqual(len(session['queue']), 1)
            self.assertEqual(session['queue'][0]['kind'], 'work')
            self.assertTrue(session['queue'][0]['artifact_repair'])
            self.assertNotIn('approval_id', session['queue'][0])
            self.assertEqual(store.read()['approvals'], {})
            self.assertEqual(packet.stat().st_size, 60001)

    def test_upload_without_review_makes_no_remote_call(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mockup_upload, 'call') as send:
            from PIL import Image
            image = Path(tmp) / 'image.png'; Image.new('RGB', (8, 8)).save(image)
            result = mockup_upload.main(['--job-dir', tmp, '--project', 'Ted ops', '--batch', 'test', str(image)])
            self.assertEqual(result, 1); send.assert_not_called()

    def test_needs_you_without_review_makes_no_remote_call(self):
        card = {'id': 'x', 'project': 'Ted ops', 'section': 'ted_doing'}
        status = status_module()
        with patch.object(status.board_client, 'cards', return_value=[card]), \
                patch.object(status, 'call') as send:
            with self.assertRaises(ReviewBlocked):
                live_status.update('x', 'waiting_on_you', 'review this', section='needs_you')
            send.assert_not_called()

    def test_all_approval_types_are_held_before_staging(self):
        for name in ('draft-email.json', 'spend.json', 'apply.sql'):
            with tempfile.TemporaryDirectory() as tmp:
                store = sessions.Store(tmp); store.enqueue({'id': 'x', 'title': 'Test'}, 'work', 'r')
                with store.locked() as data:
                    s = data['sessions']['x']; s.update(status='done', queue=[])
                    (Path(s['cwd']) / name).write_text('{}')
                collect_approvals(store)
                self.assertEqual(store.read()['approvals'], {})
                self.assertEqual(store.read()['sessions']['x']['status'], 'review_blocked')

    def test_unreviewed_worker_result_is_not_in_outbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = sessions.Store(tmp); store.enqueue({'id': 'x', 'title': 'Test'}, 'work', 'r')
            with store.locked() as data:
                s = data['sessions']['x']; s.update(status='running', turn='turn', queue=[], pid=999999)
                sessions.atomic(Path(s['cwd']) / 'turn.result.json', {'ok': True, 'text': 'Unreviewed report.'})
            if hasattr(store, '_deliver_final') and 'reconcile' in __import__('inspect').signature(store.tick).parameters:
                # The reconciler settles through the same delivery gate after its lease checks.
                with store.locked() as data:
                    store._deliver_final(data, data['sessions']['x'], {'ok': True, 'text': 'Unreviewed report.'})
            else:
                with patch.object(sessions, 'alive', return_value=False): store.tick()
            data = store.read()
            self.assertEqual(data['sessions']['x']['status'], 'review_blocked')
            self.assertFalse(any('Unreviewed report.' in item['text'] for item in data['outbox']))

    def test_flush_rechecks_previously_queued_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = sessions.Store(tmp)
            with store.locked() as data:
                data['outbox'] = [{'card_id': 'x', 'text': 'Old unreviewed content', 'token': 't',
                                   'requires_review': True, 'job_dir': str(Path(tmp) / 'missing')}]
            with patch.object(sessions, 'deliver') as send: store.flush(); send.assert_not_called()

    def test_reaper_keeps_a_review_hold_blocked_even_when_the_report_says_done(self):
        import board_live
        with tempfile.TemporaryDirectory() as tmp:
            store=sessions.Store(tmp);store.enqueue({'id':'x','title':'Test'},'work','r')
            with store.locked() as data:
                session=data['sessions']['x'];session.update(status='review_blocked',queue=[])
                (Path(session['cwd'])/'REPORT.md').write_text('# Done\nShipped the content.\n')
            with patch.object(board_live,'update') as send:
                board_live.reap([{'id':'x','section':'ted_doing'}],tmp,now=30000)
                self.assertEqual(send.call_args.args[1],'blocked')
                self.assertEqual(send.call_args.args[2],'content review missing, failed, or stale')
                self.assertIsNone(send.call_args.kwargs['section'])

    def test_timed_failure_and_uncertainty_stay_visible_without_unreviewed_needs_you(self):
        import board_live
        for outcome in ('failed','uncertain'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                store=sessions.Store(tmp);store.enqueue({'id':'x','title':'Test'},'work','r')
                with store.locked() as data:
                    data['sessions']['x'].update(status='review_blocked',queue=[],veto_outcome={'status':outcome,'revision':7})
                def publish(card_id,state,line,**kwargs):
                    if state=='waiting_on_you':raise ReviewBlocked('review required')
                    return {'id':card_id}
                with patch.object(board_live,'update',side_effect=publish) as send:
                    result=board_live.reap([{'id':'x','section':'ted_doing','revision':7,'updated_at':'1970-01-01T00:00:01Z'}],tmp,now=30000)
                    self.assertEqual(result,(1,0))
                    self.assertEqual(send.call_args.args[1],'blocked')
                    self.assertIsNone(send.call_args.kwargs.get('section'))
                    self.assertIn('review' if outcome=='failed' else 'Gmail Sent',send.call_args.args[2])

    def test_confirmed_timed_send_does_not_point_to_an_undelivered_reply(self):
        import board_live
        with tempfile.TemporaryDirectory() as tmp:
            store=sessions.Store(tmp);store.enqueue({'id':'x','title':'Test'},'work','r')
            with store.locked() as data:
                data['sessions']['x'].update(status='review_blocked',queue=[],veto_outcome={'status':'sent','revision':7})
            with patch.object(board_live,'update') as send:
                board_live.reap([{'id':'x','section':'ted_doing','revision':7,'updated_at':'1970-01-01T00:00:01Z'}],tmp,now=30000)
                self.assertEqual(send.call_args.args[1],'done')
                self.assertIn('receipt recorded by the worker',send.call_args.args[2])
                self.assertNotIn('card reply',send.call_args.args[2])


    def test_runner_notices_pass_but_model_text_needs_review(self):
        import review_gate
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'sessions.json').write_text(json.dumps({'sessions': {}}))
            review_gate.validate_reply('x', 'Approval needed: Send the exact drafted email. Review the exact content on this card.', tmp)
            review_gate.validate_reply('x', 'Job stop queued for the reconciler.', tmp)
            for text in ('Approval needed: wire 5000 dollars. Review the exact content on this card.', 'Here is the client email.'):
                with self.assertRaises(ReviewBlocked): review_gate.validate_reply('x', text, tmp)

    def test_reconciler_needs_you_card_requires_review(self):
        if reconciler_card is None: self.skipTest('reconciler not installed')
        with tempfile.TemporaryDirectory() as tmp, patch.object(reconciler_card, 'resolve_rule') as rule, \
                patch.object(reconciler_card, 'urlopen_json') as send:
            cwd = Path.cwd()
            try:
                __import__('os').chdir(tmp)
                with self.assertRaises(ReviewBlocked):
                    reconciler_card.create('Ted ops', 'Pick one', 'choose the copy', needs_you=True, kind='other')
            finally: __import__('os').chdir(cwd)
            rule.assert_not_called(); send.assert_not_called()

    def test_heartbeat_drops_a_stale_approval_and_keeps_jobs(self):
        import board_client
        approvals = [{'id': 'a', 'card_id': 'missing'}]
        with patch.object(board_client, 'load_env', return_value={'TED_DECISIONS_KEY': 'k', 'TED_DECISIONS_WORKER_KEY': 'k'}), \
                patch.object(board_client, 'urlopen_json', return_value={'ok': True}) as send, \
                patch('review_gate.validate_approval_payload', side_effect=ReviewBlocked('stale')):
            board_client.call('heartbeat', jobs=[{'id': 'j'}], approvals=approvals)
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual(body['approvals'], []); self.assertEqual(body['jobs'], [{'id': 'j'}])

    def test_unreviewed_pin_reply_makes_no_remote_call(self):
        import mockup_client
        with tempfile.TemporaryDirectory() as tmp, patch.object(mockup_client, 'load_env') as secrets:
            cwd = Path.cwd()
            try:
                __import__('os').chdir(tmp)
                with self.assertRaises(ReviewBlocked):
                    mockup_client.call('ted_reply', pin_id='00000000-0000-0000-0000-000000000000', text='Unreviewed copy.')
            finally: __import__('os').chdir(cwd)
            secrets.assert_not_called()


if __name__ == '__main__': unittest.main()
