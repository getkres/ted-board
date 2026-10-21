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


if __name__ == '__main__': unittest.main()
