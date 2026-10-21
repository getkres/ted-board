"""Alternate worker transport paths must enforce the same prerequisite."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import board_client
import pod_pulse
import review_gate as gate
import session_worker


class TransportTests(unittest.TestCase):
    def test_direct_reply_veto_and_approval_heartbeat_block_before_credentials(self):
        examples = [
            ('ted_reply', {'card_id': 'unreviewed-fixture', 'text': 'Unreviewed report.'}),
            ('veto_mark', {'card_id': 'unreviewed-fixture', 'draft_text': 'Unreviewed draft.'}),
            ('heartbeat', {'jobs': [], 'approvals': [{'card_id': 'unreviewed-fixture', 'kind': 'email'}]}),
        ]
        for action, body in examples:
            with self.subTest(action=action), patch.object(board_client, 'load_env', return_value={}) as secrets:
                with self.assertRaises(gate.ReviewBlocked): board_client.call(action, **body)
                secrets.assert_not_called()

    def test_unreviewed_pod_pulse_is_not_published(self):
        row = {'pod_id': 'fixture', 'project': 'Ted ops'}
        with patch.object(pod_pulse, 'build_snapshot', return_value=[row]), patch.object(pod_pulse, 'call') as send:
            with self.assertRaises(gate.ReviewBlocked): pod_pulse.publish(Path('/nonexistent-test-fixture'))
            send.assert_not_called()

    def test_codex_model_comes_from_the_executed_command(self):
        self.assertEqual(session_worker.maker_model(['codex', 'exec', '-m', 'configured-model'], 'codex'), 'configured-model')
        self.assertEqual(session_worker.maker_model(['codex', 'exec'], 'codex'), '')
        self.assertEqual(session_worker.maker_model(['claude'], 'claude', {'modelUsage': {'actual-model': {}}}), 'actual-model')
        self.assertEqual(session_worker.maker_model(['claude'], 'claude', {}), '')

    def test_reviewed_pod_rows_publish_while_unreviewed_rows_are_omitted(self):
        approved={'pod_id':'approved','project':'Ted ops'}
        blocked={'pod_id':'blocked','project':'Ted ops'}
        with patch.object(pod_pulse,'build_snapshot',return_value=[approved,blocked]), \
                patch.object(gate,'validate_pod',side_effect=[None,gate.blocked()]), \
                patch.object(pod_pulse,'call',return_value={'ok':True}) as send:
            self.assertEqual(pod_pulse.publish(Path('/fixture')),[approved])
            self.assertEqual(send.call_args.kwargs['pods'],[approved])


if __name__ == '__main__': unittest.main()
