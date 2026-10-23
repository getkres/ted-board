import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# The board API and process probe are external to this repo checkout.
source = Path(os.environ.get('BOARD_LIVE_SOURCE', Path.home() / 'ted-ops/ted-board/board_live.py'))
spec = importlib.util.spec_from_file_location('board_live_under_test', source)
board_live = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {
    'board_client': types.SimpleNamespace(cards=lambda: []),
    'live_status': types.SimpleNamespace(update=lambda *args, **kwargs: None),
    'sessions': types.SimpleNamespace(alive=lambda *args: False, identity=lambda *args: ''),
}):
    spec.loader.exec_module(board_live)


class TerminalCardReconciliation(unittest.TestCase):
    def card(self):
        return dict(id='c-test', section='ted_doing', updated_at='1970-01-01T00:00:00Z')

    def test_dead_worker_without_report_moves_to_needs_you(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / 'card-c-test'
            directory.mkdir()
            (root / 'sessions.json').write_text(json.dumps({'sessions': {
                'c-test': dict(cwd=str(directory), status='failed', queue=[], started_at=1)
            }}))
            with patch.object(board_live, 'update') as update:
                changed, failed = board_live.reap([self.card()], root, now=30000)
            self.assertEqual((changed, failed), (1, 0))
            self.assertEqual(update.call_args.args[1], 'blocked')
            self.assertEqual(update.call_args.kwargs['section'], 'needs_you')
            self.assertTrue(update.call_args.kwargs['ask_anyway_reason'])

    def test_orphaned_card_moves_to_needs_you_after_six_hours(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(board_live, 'update') as update:
                board_live.reap([self.card()], temp, now=30000)
            self.assertEqual(update.call_args.kwargs['section'], 'needs_you')

    def test_blocked_report_moves_to_needs_you_and_done_report_to_done(self):
        for report_text, expected_state, expected_section in (
            ('LIVE_STATE: blocked\nLIVE_STATUS: pr needs review', 'blocked', 'needs_you'),
            ('LIVE_STATE: done\nLIVE_STATUS: merged and verified', 'done', 'done'),
            ('LIVE_STATE: waiting_on_you\nLIVE_STATUS: approve the plan', 'waiting_on_you', 'needs_you'),
        ):
            with self.subTest(expected_state=expected_state), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                directory = root / 'card-c-test'
                directory.mkdir()
                (directory / 'REPORT.md').write_text(report_text)
                (root / 'sessions.json').write_text(json.dumps({'sessions': {
                    'c-test': dict(cwd=str(directory), status='done', queue=[], started_at=1)
                }}))
                with patch.object(board_live, 'update') as update:
                    board_live.reap([self.card()], root, now=30000)
                self.assertEqual(update.call_args.args[1], expected_state)
                self.assertEqual(update.call_args.kwargs['section'], expected_section)
                if expected_section == 'needs_you':
                    self.assertTrue(update.call_args.kwargs['ask_anyway_reason'])

    def test_queued_turn_remains_in_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / 'card-c-test'
            directory.mkdir()
            (root / 'sessions.json').write_text(json.dumps({'sessions': {
                'c-test': dict(cwd=str(directory), status='queued', queue=[{'kind': 'work'}])
            }}))
            with patch.object(board_live, 'update') as update:
                board_live.reap([self.card()], root, now=30000)
            self.assertEqual(update.call_args.args[1], 'blocked')
            self.assertIsNone(update.call_args.kwargs['section'])


if __name__ == '__main__':
    unittest.main()
