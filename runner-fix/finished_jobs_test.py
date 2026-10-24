"""Offline tests for private runtime candidates. No worker or network is launched."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(os.environ.get('TED_RUNTIME_SOURCE', Path.home() / 'ted-ops/ted-board'))

def module(name, filename, deps):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, deps):
        spec.loader.exec_module(result)
    return result

client = types.SimpleNamespace(BoardConflict=RuntimeError, BoardGone=LookupError, call=Mock(side_effect=AssertionError('network forbidden')), cards=lambda: [])
live = module('candidate_live', 'live_status.py', {'board_client': client})
sessions = module('candidate_sessions', 'sessions.py', {'board_client': client, 'live_status': live})
worker = module('candidate_worker', 'session_worker.py', {'board_client': client, 'sessions': sessions})
reaper = module('candidate_reaper', 'board_live.py', {'board_client': client, 'live_status': live, 'sessions': sessions})

class FinishedJobs(unittest.TestCase):
    def session(self, root):
        store = sessions.Store(root)
        store.enqueue(dict(id='x', title='Synthetic job'), 'do the work', 'receipt', engine='codex')
        with store.locked() as data:
            s = data['sessions']['x']
            s.update(status='running', pid=os.getpid(), identity='fixture', turn='turn', queue=[])
        return store, store.read()['sessions']['x']

    def test_dispatcher_routes_success_to_ted_review_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, s = self.session(tmp)
            sessions.atomic(Path(s['cwd']) / 'turn.result.json', dict(ok=True, text='PR ready for Ted', completion=dict(section='needs_you', note='wrong')))
            with patch.object(sessions, 'alive', return_value=False), patch.object(sessions, 'publish_live') as publish:
                store.tick();store.tick()
            self.assertEqual(store.read()['sessions']['x']['status'], 'done')
            self.assertEqual(publish.call_count, 1)
            self.assertEqual(publish.call_args.args, ('x', 'blocked', 'Ted review'))
            self.assertEqual(publish.call_args.kwargs, dict(section='up_next'))

    def test_dispatcher_does_not_mark_failure_or_queued_work_finished(self):
        for ok, queued in ((False, False), (True, True)):
            with self.subTest(ok=ok, queued=queued), tempfile.TemporaryDirectory() as tmp:
                store, s = self.session(tmp)
                if queued:
                    with store.locked() as data:
                        # All slots occupied stops spawning without bypassing terminal handling.
                        data['sessions']['x']['queue'] = [dict(id='next', kind='work', message='more')]
                        for i in range(3):
                            data['sessions'][str(i)] = dict(status='running', cwd=tmp, turn='other', pid=1, identity='alive', last_activity=0)
                sessions.atomic(Path(s['cwd']) / 'turn.result.json', dict(ok=ok, text='result'))
                with patch.object(sessions, 'alive', side_effect=lambda pid, expected: pid == 1), patch.object(sessions, 'publish_live') as publish:
                    store.tick()
                self.assertFalse(any(c.kwargs.get('section') == 'up_next' for c in publish.call_args_list))

    def test_worker_records_review_handoff_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, s = self.session(tmp)
            prefix = Path(s['cwd']) / 'turn'
            sessions.atomic(str(prefix) + '.input.json', dict(session=s, prompt='fixture'))
            Path(str(prefix) + '.last.txt').write_text('A complete synthetic result')
            with patch.object(worker, 'identity', return_value='fixture'), patch.object(worker, 'engine_command', return_value=['fixture-only']), patch.object(worker.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)):
                worker.run(prefix)
            result = json.loads(Path(str(prefix) + '.result.json').read_text())
            self.assertEqual(result.get('completion'), dict(section='up_next', note='Ted review'))
            self.assertTrue(result['ok'])

    def test_reaper_retries_successful_handoff_even_for_blocked_or_missing_reports(self):
        for report in ('LIVE_STATE: blocked\nLIVE_STATUS: pr pending review', '# Done\nShipped.', None):
            with self.subTest(report=report), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp);d = root / 'card-x';d.mkdir()
                if report:
                    (d / 'REPORT.md').write_text(report)
                (root / 'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d), status='done', queue=[], started_at=1)})))
                with patch.object(reaper, 'update') as publish:
                    reaper.reap([dict(id='x', section='ted_doing', updated_at='1970-01-01T00:00:00Z')], root, now=30000)
                self.assertEqual(publish.call_args.args, ('x', 'blocked', 'Ted review'))
                self.assertEqual(publish.call_args.kwargs['section'], 'up_next')
                self.assertNotIn('ask_anyway_reason', publish.call_args.kwargs)

    def test_reaper_does_not_hide_a_new_answer_behind_an_old_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);d = root / 'card-x';d.mkdir()
            (root / 'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d), status='done', queue=[], started_at=1, last_activity=2)})))
            card = dict(id='x', section='ted_doing', answer=dict(created_at='2026-10-22T12:00:00Z'), updated_at='2026-10-22T12:00:00Z')
            with patch.object(reaper, 'update') as publish:
                reaper.reap([card], root, now=30000)
            self.assertFalse(any(c.kwargs.get('section') == 'up_next' for c in publish.call_args_list))

    def test_live_status_accepts_up_next_and_keeps_manual_move_guard(self):
        with patch.object(live, 'call', return_value=dict(ok=True, card=dict(id='x'))) as call:
            live.update('x', 'blocked', 'Ted review', section='up_next')
        self.assertEqual(call.call_args.kwargs, dict(card_id='x', state='blocked', line='ted review', section='up_next', expected_section='ted_doing'))

if __name__ == '__main__':
    unittest.main()
