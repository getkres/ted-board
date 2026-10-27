"""Offline regression for finishing all requested self-trigger measurements."""
import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

DIAGNOSTICS = Path(__file__).parents[1] / 'diagnostics'
sys.path.insert(0, str(DIAGNOSTICS))
spec = importlib.util.spec_from_file_location('voice_acceptance_runner', DIAGNOSTICS / 'test_voice.py')
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)
sys.path.pop(0)


class ContinueMeasurementTests(unittest.TestCase):
    def measure(self, continue_on_failure, fail_first=True, fail_fixture_at=None):
        runner = object.__new__(runner_module.Runner)
        runner.args = SimpleNamespace(trials=10, minimum_long_seconds=20,
                                      continue_on_failure=continue_on_failure)
        calls = []

        def fixture(kind):
            calls.append(kind)
            if len(calls) == fail_fixture_at:
                raise RuntimeError('audio device unavailable')
            return {'trial_id': kind, 'duration_seconds': 25, 'started': {'at': 10}}

        def rows(since):
            trial = calls[-1]
            result = [{'at': 10, 'event': 'diagnostic_fixture_started', 'trial_id': trial},
                      {'at': 35, 'event': 'diagnostic_fixture_completed', 'trial_id': trial}]
            if fail_first and len(calls) == 1:
                result.insert(1, {'at': 11, 'event': 'playback_stopped', 'stop_id': 'echo'})
            return result

        runner.fixture = fixture
        runner.rows = rows
        runner.wait = lambda *args: None
        runner.jabra_verified = lambda: True
        with patch.object(runner_module.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            return runner.no_self_trigger()

    def test_continuation_records_all_trials_without_hiding_failure(self):
        result = self.measure(True)
        self.assertEqual(result['completed_trials'], 10)
        self.assertEqual(result['failed_trials'], 1)
        self.assertEqual(result['trials'][0]['self_triggers'], 1)
        self.assertFalse(result['ok'])

    def test_default_still_stops_on_first_failure(self):
        self.assertEqual(self.measure(False)['completed_trials'], 1)

    def test_fixture_start_error_preserves_completed_trials_and_stops(self):
        result = self.measure(True, fail_fixture_at=4)
        self.assertFalse(result['ok'])
        self.assertEqual(result['completed_trials'], 3)
        self.assertEqual(result['failed_trials'], 1)
        self.assertEqual(len(result['trials']), 3)
        self.assertEqual(result['trials'][0]['self_triggers'], 1)
        self.assertEqual(result['error'], 'RuntimeError: audio device unavailable')
        self.assertEqual(result['failed_to_start_trial'], 4)

    def test_ten_clean_trials_still_pass(self):
        result = self.measure(True, fail_first=False)
        self.assertTrue(result['ok'])
        self.assertEqual(result['failed_trials'], 0)


if __name__ == '__main__':
    unittest.main()
