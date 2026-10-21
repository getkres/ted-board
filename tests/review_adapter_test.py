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


class AdapterTests(unittest.TestCase):
    def test_upload_without_review_makes_no_remote_call(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mockup_upload, 'call') as send:
            from PIL import Image
            image = Path(tmp) / 'image.png'; Image.new('RGB', (8, 8)).save(image)
            result = mockup_upload.main(['--job-dir', tmp, '--project', 'Ted ops', '--batch', 'test', str(image)])
            self.assertEqual(result, 1); send.assert_not_called()

    def test_needs_you_without_review_makes_no_remote_call(self):
        card = {'id': 'x', 'project': 'Ted ops', 'section': 'ted_doing'}
        with patch.object(live_status.board_client, 'cards', return_value=[card]), \
                patch.object(live_status, 'call') as send:
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
                store.collect_approvals()
                self.assertEqual(store.read()['approvals'], {})
                self.assertEqual(store.read()['sessions']['x']['status'], 'review_blocked')

    def test_unreviewed_worker_result_is_not_in_outbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = sessions.Store(tmp); store.enqueue({'id': 'x', 'title': 'Test'}, 'work', 'r')
            with store.locked() as data:
                s = data['sessions']['x']; s.update(status='running', turn='turn', queue=[], pid=999999)
                sessions.atomic(Path(s['cwd']) / 'turn.result.json', {'ok': True, 'text': 'Unreviewed report.'})
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


if __name__ == '__main__': unittest.main()
