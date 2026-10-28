"""Offline checks that acceptance cannot pass from unrelated or incomplete evidence."""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / 'diagnostics/acceptance_evidence.py'
spec = importlib.util.spec_from_file_location('acceptance_evidence', MODULE)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class EvidenceTests(unittest.TestCase):
    def rows(self):
        return [
            {'at': 10, 'event': 'diagnostic_fixture_started', 'trial_id': 'trial'},
            {'at': 11, 'event': 'wake_candidate', 'trigger_id': 'wake', 'trigger_at': 11, 'barge_in': True},
            {'at': 11.1, 'event': 'playback_stopped', 'stop_id': 'wake', 'trigger_at': 11, 'stopped_at': 11.1},
            {'at': 12, 'event': 'wake', 'trigger_id': 'wake', 'confirmed_at': 12, 'barge_in': True},
            {'at': 12, 'event': 'diagnostic_fixture_interrupted', 'trial_id': 'trial'},
            {'at': 15, 'event': 'transcribed'},
            {'at': 16, 'event': 'submitted'},
            {'at': 16.5, 'event': 'claude_voice_reply', 'account': 2, 'characters': 26},
            {'at': 17, 'event': 'reply_received'},
            {'at': 18, 'event': 'speech_started'},
            {'at': 19, 'event': 'playback_done'},
        ]

    def classify(self, rows):
        return evidence.barge_in_evidence(rows, 'trial', 10.5, 11.5, 14)

    def test_correlation_and_followup_are_required(self):
        result = self.classify(self.rows())
        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['trigger_to_native_stop_ms'], 100)
        wrong = self.rows()
        wrong[2]['stop_id'] = 'unrelated'
        self.assertFalse(self.classify(wrong)['ok'])
        self.assertFalse(self.classify(self.rows()[:-1])['ok'])

    def test_local_notice_without_real_ted_reply_is_not_a_handled_followup(self):
        rows = [row for row in self.rows() if row['event'] != 'claude_voice_reply']
        rows.insert(7, {'at': 16.4, 'event': 'voice_action_queued', 'marker': 'action'})
        result = self.classify(rows)
        self.assertFalse(result['ok'])
        self.assertFalse(result['followup_handled'])

    def test_real_reply_cannot_hide_queued_or_uncertain_delivery(self):
        for event in ('voice_action_queued', 'voice_main_delivery_uncertain'):
            with self.subTest(event=event):
                rows = self.rows()
                rows.insert(7, {'at': 16.4, 'event': event, 'marker': 'action'})
                self.assertFalse(self.classify(rows)['followup_handled'])

    def test_real_route_reply_must_belong_to_followup_window(self):
        for at, account in ((13, 2), (18.1, 2), (16.5, 1)):
            with self.subTest(at=at, account=account):
                rows = self.rows()
                reply = next(row for row in rows if row['event'] == 'claude_voice_reply')
                reply.update(at=at, account=account)
                self.assertFalse(self.classify(rows)['followup_handled'])

    def test_main_ted_reply_also_verifies_the_followup(self):
        rows = self.rows()
        reply = next(row for row in rows if row['event'] == 'claude_voice_reply')
        reply.update(event='voice_main_reply', session_id='main')
        result = self.classify(rows)
        self.assertTrue(result['followup_handled'])
        self.assertEqual(result['followup_reply_route'], 'main')

    def test_slow_or_unconfirmed_stop_cannot_pass(self):
        slow = self.rows()
        slow[2]['stopped_at'] = 11.301
        self.assertFalse(self.classify(slow)['ok'])
        unconfirmed = [row for row in self.rows() if row['event'] != 'wake']
        self.assertFalse(self.classify(unconfirmed)['ok'])

    def test_monotonic_latency_wins_when_wall_clock_changes(self):
        rows = self.rows()
        rows[1]['trigger_monotonic'] = 100
        rows[2]['stopped_monotonic'] = 100.1
        rows[2]['stopped_at'] = 12.1
        result = self.classify(rows)
        self.assertTrue(result['ok'])
        self.assertAlmostEqual(result['trigger_to_native_stop_ms'], 100)

    def test_pre_stimulus_candidate_cannot_pass(self):
        rows = self.rows()
        rows[1]['trigger_at'] = 10.1
        self.assertFalse(self.classify(rows)['ok'])

    def test_provisional_stop_fails_uninterrupted_trial(self):
        rows = [
            {'at': 10, 'event': 'diagnostic_fixture_started', 'trial_id': 'trial'},
            {'at': 11, 'event': 'playback_stopped', 'stop_id': 'echo'},
            {'at': 11.1, 'event': 'playback_resumed'},
            {'at': 30, 'event': 'diagnostic_fixture_completed', 'trial_id': 'trial'},
        ]
        self.assertFalse(evidence.self_trigger_evidence(rows, 'trial', 15)['ok'])
        self.assertTrue(evidence.self_trigger_evidence([rows[0], rows[-1]], 'trial', 15)['ok'])
        rows[-1]['at'] = 12
        self.assertFalse(evidence.self_trigger_evidence([rows[0], rows[-1]], 'trial', 15)['ok'])


if __name__ == '__main__':
    unittest.main()
