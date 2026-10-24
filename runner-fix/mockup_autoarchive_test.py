"""Offline archive policy and heartbeat tests. No production transport is loaded."""
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

NOW = datetime(2026, 10, 24, 6, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=6)).isoformat()
RECENT = (NOW - timedelta(days=1)).isoformat()
HERE = Path(__file__).resolve().parent
TEMP = tempfile.TemporaryDirectory()
ROOT = Path(os.environ.get('TED_RUNTIME_SOURCE', TEMP.name))
sys.path.insert(0, str(ROOT))
if 'TED_RUNTIME_SOURCE' not in os.environ:
    subprocess.run(['patch', '-s', '-p0', '-i', str(HERE / 'mockup-autoarchive.patch')],
                   cwd=ROOT, check=True, capture_output=True)


# Reconstruct the exact shared new-file artifact from the steward runtime bundle.
if 'TED_RUNTIME_SOURCE' not in os.environ:
    dependency = (HERE / 'inbox-steward/runtime.patch').read_text()
    shared = dependency[dependency.index('--- /dev/null\n+++ b/board_card_snapshot.py\n'):]
    subprocess.run(['patch', '-s', '-p1'], input=shared, text=True,
                   cwd=ROOT, check=True, capture_output=True)
elif not (ROOT / 'board_card_snapshot.py').is_file():
    raise SystemExit('Private candidate requires the reviewed board_card_snapshot.py helper.')
sys.path.insert(0, str(ROOT))


def load(name, filename, deps=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, deps or {}):
        spec.loader.exec_module(module)
    return module


archive = load('candidate_autoarchive', 'mockup_autoarchive.py')


def frame(id='a', batch='Home v1', project='Fictora', **extra):
    row = dict(id=id, project=project, batch=batch, title='Home screen',
               status='open', verdict=None, verdict_change=None, created_at=OLD)
    if extra.get('verdict'):
        row['verdict_change'] = dict(at=OLD)
    elif extra.get('status') == 'picked':
        row['picked_at'] = OLD
    return {**row, **extra}


def unrelated_card():
    return dict(id='unrelated', project='Other', section='done', title='Unrelated work')


class Policy(unittest.TestCase):
    def candidates(self, rows, cards=None, pins=None):
        if pins is not None:
            return archive.candidates(rows, cards or [], NOW, pins=pins)
        return archive.candidates(rows, cards or [], NOW)

    def test_terminal_reviewable_verdicts_and_legacy_picks_archive(self):
        rows = [frame(str(i), verdict=v) for i, v in enumerate(
            ['approved', 'scrapped', 'picked'])]
        rows += [frame('legacy', status='picked'), frame('note', title='Notes'),
                 frame('who', title='Who made and checked this')]
        result = self.candidates(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['reason'], 'all_reviewed')
        self.assertEqual(result[0]['reviewable'], 4)
        self.assertEqual(result[0]['ignored'], 2)
        self.assertEqual(set(result[0]['ids']), {r['id'] for r in rows})

    def test_needs_work_waits_for_new_round_even_with_other_terminal_verdicts(self):
        for rows in ([frame(verdict='needs_work')],
                     [frame(verdict='approved'), frame('b', verdict='needs_work')],
                     [frame(status='picked', verdict='needs_work')]):
            self.assertEqual(self.candidates(rows), [])

    def test_needs_work_can_archive_via_terminal_card_or_stale_supersession(self):
        for section in ('done', 'killed'):
            result = self.candidates([frame(verdict='needs_work', card_id='x')],
                [dict(id='x', project='Fictora', section=section, title='Work')])
            self.assertEqual(result[0]['reason'], 'linked_card_' + section)
        result = self.candidates([frame(verdict='needs_work'),
            frame('new', batch='Home v2', created_at=RECENT)])
        self.assertEqual(result[0]['reason'], 'stale_superseded')

    def test_24_hour_floor_applies_to_creation_and_every_verdict_clock(self):
        cutoff = NOW - timedelta(hours=24)
        for field in ('created_at', 'verdict_at', 'picked_at', 'verdict_change'):
            for delta, expected in ((timedelta(), 1), (timedelta(microseconds=1), 0)):
                at = (cutoff + delta).isoformat()
                value = dict(at=at) if field == 'verdict_change' else at
                rows = [frame(verdict='approved', **{field: value})]
                self.assertEqual(len(self.candidates(rows)), expected, field)

    def test_24_hour_floor_protects_terminal_cards_and_informational_frames(self):
        fresh = (NOW - timedelta(hours=23)).isoformat()
        cards = [dict(id='x', project='Fictora', section='done', title='build approved: Home v1')]
        for row in (frame(created_at=fresh), frame(verdict='needs_work', verdict_change=dict(at=fresh))):
            self.assertEqual(self.candidates([row], cards), [])
        for metadata in (frame('note', title='Notes', created_at=fresh),
                         frame('note', title='Who made and checked this', verdict_change=dict(at=fresh))):
            self.assertEqual(self.candidates([frame(verdict='approved'), metadata]), [])

    def test_invalid_or_missing_clock_blocks_every_reason(self):
        cards = [dict(id='x', project='Fictora', section='done', title='build approved: Home v1')]
        for row in (frame(verdict='approved', created_at=None),
                    frame(verdict='approved', created_at='invalid'),
                    frame(verdict='approved', verdict_change=None),
                    frame(verdict='approved', verdict_change=dict(at='invalid'))):
            self.assertEqual(self.candidates([row], cards), [])

    def test_unresolved_pin_blocks_all_reasons_including_archived_frames(self):
        rows = [frame(verdict='approved'), frame('old', status='archived')]
        for mockup_id in ('a', 'old'):
            self.assertEqual(self.candidates(rows, pins=[dict(mockup_id=mockup_id, resolved=False)]), [])
        cards = [dict(id='x', project='Fictora', section='done', title='build approved: Home v1')]
        pin = dict(mockup_id='a', resolved=False)
        self.assertEqual(self.candidates([frame()], cards, pins=[pin]), [])
        self.assertEqual(self.candidates([frame(), frame('new', batch='Home v2', created_at=RECENT)],
                                         pins=[pin]), [])

    def test_resolved_or_unrelated_pins_allow_an_archive(self):
        for pin in (dict(mockup_id='a', resolved=True), dict(mockup_id='other', resolved=False)):
            self.assertEqual(self.candidates([frame(verdict='approved')], pins=[pin])[0]['reason'],
                             'all_reviewed')

    def test_metadata_labels_are_case_insensitive_title_segments(self):
        for title in ('Notes: what changed', 'Hair v13: Notes, what changed and why',
                      '01: NOTES', 'Who made and checked this: team'):
            with self.subTest(title=title):
                rows = [frame(verdict='approved'), frame('meta', title=title)]
                self.assertEqual(self.candidates(rows)[0]['reviewable'], 1)

    def test_unreviewed_frames_and_metadata_only_batches_stay_open(self):
        for rows in ([frame()], [frame(title='Notes')],
                     [frame(verdict='approved'), frame('b')],
                     [frame(title='Notes app screen'), frame('b', verdict='approved')],
                     [frame(verdict='good_with_fix')],
                     [frame(status='picked', verdict='unknown')]):
            with self.subTest(rows=rows):
                self.assertEqual(self.candidates(rows), [])

    def test_archived_frames_do_not_block_or_repeat_an_archive(self):
        self.assertEqual(self.candidates([frame(status='archived', verdict='approved')]), [])
        result = self.candidates([frame(verdict='approved'), frame('b', status='archived')])
        self.assertEqual(result[0]['ids'], ['a'])
        self.assertEqual(result[0]['total'], 2)

    def test_done_or_killed_explicit_card_link_archives(self):
        for section in ('done', 'killed'):
            result = self.candidates([frame(card_id='card-a')],
                [dict(id='card-a', project='Fictora', section=section, title='Work')])
            self.assertEqual(result[0]['reason'], 'linked_card_' + section)
            self.assertEqual(result[0]['card_ids'], ['card-a'])

    def test_existing_build_title_and_mockup_id_links_are_supported(self):
        for title, body in [('build approved: Home v1', ''),
                            ('Finished work', 'Home (mockup ID: a)')]:
            result = self.candidates([frame(verdict='needs_work')], [dict(id='card-a', project='Fictora',
                section='done', title=title, body=body)])
            self.assertEqual(result[0]['reason'], 'linked_card_done')

    def test_id_reference_in_terminal_card_cannot_hide_unreviewed_frames(self):
        for section in ('done', 'killed'):
            card = dict(id='card-a', project='Fictora', section=section,
                        title='Finished one frame', body='Home (mockup ID: a)')
            for rows in ([frame()], [frame(verdict='approved'), frame('pending')],
                         [frame(verdict='unknown')], [frame(title='Notes')]):
                self.assertEqual(self.candidates(rows, [card]), [])

    def test_id_reference_terminal_card_requires_all_active_reviewable_verdicts(self):
        for section in ('done', 'killed'):
            rows = [frame(verdict='needs_work'), frame('b', verdict='approved'),
                    frame('note', title='Notes'), frame('who', title='Who made and checked this')]
            card = dict(id='card-a', project='Fictora', section=section,
                        title='Finished work', body='Home (mockup ID: a)')
            result = self.candidates(rows, [card])
            self.assertEqual(result[0]['reason'], 'linked_card_' + section)
            self.assertEqual(result[0]['ids'], ['a', 'b', 'note', 'who'])

    def test_exact_build_title_link_still_archives_unreviewed_batch(self):
        for section in ('done', 'killed'):
            card = dict(id='card-a', project='Fictora', section=section,
                        title='build approved: Home v1', body='')
            result = self.candidates([frame(), frame('b')], [card])
            self.assertEqual(result[0]['reason'], 'linked_card_' + section)

    def test_all_reviewed_waits_for_every_same_project_linked_card(self):
        for section in ('up_next', 'ted_doing', 'needs_you'):
            for link in ('explicit', 'title', 'reference'):
                row = frame(verdict='approved', **({'card_id': 'work'} if link == 'explicit' else {}))
                card = dict(id='work', project='Fictora', section=section,
                            title='build approved: Home v1' if link == 'title' else 'Build work',
                            body='mockup ID: a' if link == 'reference' else None)
                terminal = dict(id='finished', project='Fictora', section='done',
                                title='Finished frame', body='mockup ID: a')
                # A newer round must not turn this blocked all-reviewed batch into a stale archive.
                rows = [row, frame('new', batch='Home v2', created_at=RECENT)]
                self.assertEqual(self.candidates(rows, [terminal, card]), [], (section, link))

    def test_all_reviewed_allows_terminal_unlinked_and_cross_project_cards(self):
        rows = [frame(verdict='approved')]
        for card in (dict(id='x', project='Fictora', section='done', title='build approved: Home v1'),
                     dict(id='x', project='Fictora', section='killed', title='Build', body='mockup ID: a'),
                     dict(id='x', project='Fictora', section='ted_doing', title='Unrelated work'),
                     dict(id='x', project='Bookish', section='ted_doing', title='Other work',
                          body='mockup ID: a')):
            self.assertEqual(self.candidates(rows, [card])[0]['reason'], 'all_reviewed')

    def test_card_body_requires_string_or_none(self):
        for body in (True, False, 1, 0, ['mockup ID: a'], {'text': 'mockup ID: a'}):
            card = dict(id='x', project='Fictora', section='done', title='Build', body=body)
            with self.assertRaises(ValueError):
                self.candidates([frame(verdict='needs_work')], [card])
        for body in (None, '', 'ordinary text'):
            card = dict(id='x', project='Fictora', section='done', title='Build', body=body)
            self.assertEqual(self.candidates([frame(verdict='needs_work')], [card]), [])

    def test_missing_active_cross_project_body_and_fuzzy_links_stay_open(self):
        for card in (dict(id='x', project='Fictora', section='up_next', title='build approved: Home v1'),
                     dict(id='x', project='Bookish', section='done', title='Other', body='mockup ID: a'),
                     dict(id='x', project='Fictora', section='done', title='Home v1'),
                     dict(id='x', project='Fictora', section='done', title='build approved: Home v10'),
                     dict(id='x', project='Fictora', section='done', title='Other', body='mockup ID: abc')):
            with self.subTest(card=card):
                self.assertEqual(self.candidates([frame(card_id='missing')], [card]), [])

    def test_authoritative_links_block_active_cards_regardless_of_project(self):
        for project in ('Fictora', 'Bookish'):
            for link in ('explicit', 'title', 'batch'):
                for verdict in (None, 'needs_work', 'approved'):
                    extra = {'card_id': 'build'} if link == 'explicit' else {}
                    rows = [frame(verdict=verdict, **extra),
                            frame('new', batch='Home v2', created_at=RECENT)]
                    card = dict(id='build', project=project, section='doing',
                                title='build approved: Home v1' if link == 'title' else 'Other work',
                                batch='Home v1' if link == 'batch' else None)
                    self.assertEqual(self.candidates(rows, [card]), [], (project, link, verdict))

    def test_terminal_authoritative_links_match_across_projects(self):
        for link in ('explicit', 'title'):
            for section in ('done', 'killed'):
                card = dict(id='build', project='Bookish', section=section,
                            title='build approved: Home v1' if link == 'title' else 'Other work',
                            batch='Home v1' if link == 'batch' else None)
                result = self.candidates([frame(card_id='build' if link == 'explicit' else None)], [card])
                self.assertEqual(result[0]['reason'], 'linked_card_' + section)

    def test_terminal_batch_metadata_alone_does_not_archive_unreviewed_frames(self):
        card = dict(id='build', project='Bookish', section='done', title='Other work', batch='Home v1')
        self.assertEqual(self.candidates([frame()], [card]), [])

    def test_multiple_linked_cards_require_all_to_be_terminal(self):
        cards = [dict(id='done', project='Fictora', section='done', title='build approved: Home v1'),
                 dict(id='active', project='Fictora', section='up_next', title='Other', body='mockup ID: a')]
        self.assertEqual(self.candidates([frame()], cards), [])

    def test_stale_batch_requires_newer_same_project_prefix(self):
        rows = [frame(), frame('b', batch='Home v2', created_at=RECENT)]
        result = self.candidates(rows)
        self.assertEqual([(r['batch'], r['reason']) for r in result],
                         [('Home v1', 'stale_superseded')])
        self.assertEqual(result[0]['newer_batch'], 'Home v2')
        for newer in (frame('b', batch='Home v2', project='Bookish', created_at=RECENT),
                      frame('b', batch='Home icons v2', created_at=RECENT),
                      frame('b', batch='Home v2'), frame('b', batch='Unrelated', created_at=RECENT)):
            with self.subTest(newer=newer):
                self.assertEqual(self.candidates([frame(), newer]), [])

    def test_active_link_blocks_stale_unreviewed_and_needs_work_batches(self):
        old = (NOW - timedelta(days=10)).isoformat()
        for verdict in (None, 'needs_work'):
            for section in ('doing', 'ted_doing', 'up_next', 'needs_you'):
                for link in ('title', 'explicit', 'reference'):
                    extra = {'card_id': 'build'} if link == 'explicit' else {}
                    rows = [frame(batch='Hair v1', verdict=verdict, created_at=old,
                                  verdict_change=dict(at=old), **extra),
                            frame('new', batch='Hair v2', created_at=RECENT)]
                    card = dict(id='build', project='Fictora', section=section,
                                title='build approved: Hair v1' if link == 'title' else 'Active build',
                                body='mockup ID: a' if link == 'reference' else None)
                    self.assertEqual(self.candidates(rows, [card]), [], (verdict, section, link))

    def test_active_cross_project_body_reference_does_not_block_stale_supersession(self):
        rows = [frame(), frame('new', batch='Home v2', created_at=RECENT)]
        card = dict(id='build', project='Bookish', section='doing', title='Other work',
                    body='mockup ID: a')
        self.assertEqual(self.candidates(rows, [card])[0]['reason'], 'stale_superseded')

    def test_unversioned_date_round_and_hyphenated_prefixes(self):
        for old, new in [('Home', 'Home v2'), ('Home round 1', 'Home round 2'),
                         ('quote-kit-20261001-a', 'quote-kit-20261002-a'),
                         ('Home: 2026-10-01', 'Home: 2026-10-02'),
                         ('Home, 10-01', 'Home, 10-02')]:
            with self.subTest(old=old):
                result = self.candidates([frame(batch=old), frame('b', batch=new, created_at=RECENT)])
                self.assertEqual([r['batch'] for r in result], [old])

    def test_five_day_boundary_and_recent_verdict_activity(self):
        newer = frame('new', batch='Home v2', created_at=RECENT)
        for delta, expected in [(timedelta(days=5), 1),
                                (timedelta(days=5, microseconds=-1), 0)]:
            old = frame(created_at=(NOW-delta).isoformat())
            self.assertEqual(len(self.candidates([old, newer])), expected)
        for field in ('verdict_at', 'picked_at'):
            self.assertEqual(self.candidates([frame(**{field: RECENT}), newer]), [])
        self.assertEqual(self.candidates([frame(verdict_change={'at': RECENT}), newer]), [])

    def test_new_frame_prevents_stale_archive(self):
        rows = [frame(), frame('recent', created_at=RECENT),
                frame('newer', batch='Home v2', created_at=NOW.isoformat())]
        self.assertEqual(self.candidates(rows), [])

    def test_missing_or_invalid_activity_does_not_claim_staleness(self):
        for old in (frame(created_at=None), frame(created_at='invalid'),
                    frame(verdict_change={'at': 'invalid'}),
                    frame(verdict='approved', verdict_change=None)):
            rows = [old, frame('pending'), frame('new', batch='Home v2', created_at=RECENT)]
            self.assertEqual(self.candidates(rows), [])

    def test_undo_window_blocks_every_archive_reason(self):
        for undo_until in ((NOW + timedelta(seconds=5)).isoformat(), 'invalid'):
            row = frame(verdict='approved', card_id='x',
                        verdict_change=dict(at=OLD, undo_until=undo_until))
            self.assertEqual(self.candidates([row], [dict(id='x', project='Fictora',
                section='done', title='Work')]), [])
        self.assertEqual(len(self.candidates([frame(verdict='approved',
            verdict_change=dict(at=OLD, undo_until=NOW.isoformat()))])), 1)

    def test_archived_newer_batch_is_evidence_of_supersession(self):
        result = self.candidates([frame(), frame('b', batch='Home v2',
            status='archived', created_at=RECENT)])
        self.assertEqual([r['batch'] for r in result], ['Home v1'])


class Runner(unittest.TestCase):
    def run_pass(self, rows=None, cards=None, pins=None, dry_run=True, responder=None):
        calls = []
        rows = [frame(verdict='approved')] if rows is None else rows

        def transport(action=None, **payload):
            calls.append((action, payload))
            if responder:
                return responder(action, payload, len(calls))
            if action is None:
                return dict(mockups=rows, pins=pins or [])
            return dict(ok=True, archived=len(payload.get('ids', rows)))

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            with patch.dict(os.environ, {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}):
                result = archive.run_pass(dry_run=dry_run, mockup_call=transport,
                    cards_call=lambda **kw: dict(cards=cards if cards is not None else [unrelated_card()]), log_path=log, now=NOW)
            events = [json.loads(s) for s in log.read_text().splitlines()] if log.exists() else []
        return result, calls, events

    def test_dry_run_logs_reason_without_writes(self):
        result, calls, events = self.run_pass()
        self.assertEqual([c[0] for c in calls], [None])
        self.assertEqual(result[0]['event'], 'would_archive')
        self.assertEqual(events[0]['reason'], 'all_reviewed')

    def test_apply_rechecks_and_logs_confirmed_explicit_ids(self):
        result, calls, events = self.run_pass(dry_run=False)
        self.assertEqual(calls, [(None, {}), (None, {}),
            ('archive', dict(ids=['a']))])
        self.assertEqual([e['event'] for e in events], ['archive_attempt', 'archived'])
        self.assertEqual(result[0]['archived'], 1)

    def test_receipt_count_uses_active_ids_and_leaves_archived_rows_out(self):
        rows = [frame(verdict='approved'), frame('old', status='archived')]
        result, calls, events = self.run_pass(rows=rows, dry_run=False)
        self.assertEqual(calls[-1], ('archive', dict(ids=['a'])))
        self.assertEqual(result[0]['event'], 'archived')
        self.assertEqual(result[0]['archived'], 1)

    def test_explicit_id_requests_respect_the_500_id_api_limit(self):
        rows = [frame(str(i), verdict='approved') for i in range(501)]
        requested = []
        def response(action, payload, count):
            if action is None:
                return dict(mockups=rows, pins=[])
            self.assertEqual(set(payload), {'ids'})
            self.assertLessEqual(len(payload['ids']), 500)
            requested.extend(payload['ids'])
            return dict(ok=True, archived=len(payload['ids']))
        result, calls, events = self.run_pass(rows=rows, dry_run=False, responder=response)
        self.assertEqual(result[0]['event'], 'archived')
        self.assertEqual(result[0]['archived'], 501)
        self.assertEqual(len(requested), 501)
        self.assertEqual(set(requested), {row['id'] for row in rows})

    def test_failed_later_id_chunk_logs_only_the_confirmed_partial_count(self):
        rows = [frame(str(i), verdict='approved') for i in range(501)]
        def response(action, payload, count):
            if action is None:
                return dict(mockups=rows, pins=[])
            if count == 4:
                return dict(ok=True, archived=0)
            return dict(ok=True, archived=len(payload['ids']))
        result, calls, events = self.run_pass(rows=rows, dry_run=False, responder=response)
        self.assertEqual(result[0]['event'], 'archive_failed')
        self.assertEqual(result[0]['archived'], 500)

    def test_frame_uploaded_after_final_get_is_never_archived_unseen(self):
        server = [frame(verdict='approved')]
        def response(action, payload, count):
            if action is None:
                return dict(mockups=[dict(row) for row in server], pins=[])
            server.append(frame('unseen', created_at=NOW.isoformat()))
            matched = [row for row in server if row['id'] in payload['ids']] if 'ids' in payload else server
            for row in matched:
                row['status'] = 'archived'
            return dict(ok=True, archived=len(matched))
        result, calls, events = self.run_pass(dry_run=False, responder=response)
        self.assertEqual(server[-1]['status'], 'open')
        self.assertEqual(result[0]['event'], 'archived')
        self.assertEqual(result[0]['archived'], 1)

    def test_pin_feed_is_checked_on_initial_read_and_recheck(self):
        pin = dict(mockup_id='a', resolved=False)
        result, calls, events = self.run_pass(pins=[pin], dry_run=False)
        self.assertEqual(result, [])
        self.assertEqual([action for action, payload in calls], [None])
        def response(action, payload, count):
            self.assertIsNone(action)
            return dict(mockups=[frame(verdict='approved')], pins=[pin] if count > 1 else [])
        result, calls, events = self.run_pass(dry_run=False, responder=response)
        self.assertEqual(result[0]['event'], 'skipped_changed')
        self.assertEqual([action for action, payload in calls], [None, None])

    def test_recent_verdict_on_recheck_prevents_archive(self):
        def response(action, payload, count):
            self.assertIsNone(action)
            changed_at = NOW.isoformat() if count > 1 else OLD
            return dict(mockups=[frame(verdict='approved', verdict_change=dict(at=changed_at))], pins=[])
        result, calls, events = self.run_pass(dry_run=False, responder=response)
        self.assertEqual(result[0]['event'], 'skipped_changed')
        self.assertEqual([action for action, payload in calls], [None, None])

    def test_missing_or_malformed_pin_feed_fails_closed_before_apply(self):
        for pins in (None, 'invalid', [None], [dict(mockup_id='a')],
                     [dict(mockup_id='a', resolved='false')]):
            calls = []
            def response(action, payload, count):
                calls.append(action)
                return dict(mockups=[frame(verdict='approved')], pins=pins)
            with self.assertRaises(ValueError):
                self.run_pass(dry_run=False, responder=response)
            self.assertEqual(calls, [None])
        with self.assertRaises(ValueError):
            self.run_pass(dry_run=False, responder=lambda *args: dict(mockups=[frame(verdict='approved')]))

    def test_invalid_card_envelopes_raise_before_archive_on_initial_read_and_recheck(self):
        invalid = [None, [], {}, {'ok': True}, {'error': 'unavailable'},
                   {'cards': [], 'error': None}, {'cards': [], 'pod_pulse_error': True},
                   {'cards': None}, {'cards': {}}, {'cards': 'invalid'}, {'cards': [None]}]
        valid_card = dict(id='unrelated', project='Test', section='done', title='Other')
        invalid += [dict(cards=[valid_card] * size) for size in (500, 501)]
        for response in invalid:
            for recheck in (False, True):
                for dry_run in ((False,) if recheck else (True, False)):
                    with self.subTest(response_type=type(response).__name__, recheck=recheck,
                                      dry_run=dry_run), tempfile.TemporaryDirectory() as tmp:
                        requests = []; mockup_requests = []
                        def board_call(**payload):
                            requests.append(payload)
                            return {'cards': [unrelated_card()]} if recheck and len(requests) == 1 else response
                        def mockup_call(action=None, **payload):
                            mockup_requests.append(action)
                            return dict(mockups=[frame(verdict='approved')], pins=[])
                        # The old convenience adapter loses the failed envelope.
                        deps = dict(board_client=types.SimpleNamespace(call=board_call, cards=lambda: []))
                        log = Path(tmp) / 'archive.jsonl'
                        with patch.dict(sys.modules, deps), patch.dict(os.environ,
                                {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}):
                            with self.assertRaises(ValueError):
                                archive.run_pass(dry_run=dry_run, mockup_call=mockup_call,
                                                 log_path=log, now=NOW)
                        self.assertEqual(requests, [{'page': True}] * (2 if recheck else 1))
                        self.assertNotIn('archive', mockup_requests)
                        self.assertFalse(log.exists(), 'invalid snapshot reached archive_attempt')

    def test_empty_card_get_envelopes_are_rejected(self):
        for response in ({'cards': []}, {'cards': [], 'pod_pulse': []},
                         {'cards': [], 'pod_pulse_error': False}):
            requests = []
            def call(**payload):
                requests.append(payload)
                return response
            deps = dict(board_client=types.SimpleNamespace(call=call))
            with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, deps):
                with self.assertRaisesRegex(ValueError, 'Card snapshot incomplete'):
                    archive.run_pass(mockup_call=lambda: dict(mockups=[frame(verdict='approved')], pins=[]),
                                     log_path=Path(tmp)/'log', now=NOW)
            self.assertEqual(requests, [{'page': True}])

    def test_empty_card_feed_never_archives_a_reviewed_batch(self):
        for empty_on_recheck in (False, True):
            mockup_requests = []; card_requests = []
            def mockup_call(action=None, **payload):
                mockup_requests.append(action)
                return dict(mockups=[frame(verdict='approved')], pins=[])
            def card_call(**payload):
                card_requests.append(payload)
                if empty_on_recheck and len(card_requests) == 1:
                    return dict(cards=[dict(id='other', project='Other', section='done', title='Unrelated')])
                return dict(cards=[])
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                    {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}):
                log = Path(tmp)/'archive.jsonl'
                with self.assertRaisesRegex(ValueError, 'Card snapshot incomplete'):
                    archive.run_pass(dry_run=False, mockup_call=mockup_call, cards_call=card_call,
                                     log_path=log, now=NOW)
                self.assertNotIn('archive', mockup_requests)
                self.assertFalse(log.exists(), 'empty feed reached archive_attempt')
            self.assertEqual(card_requests, [{'page': True}] * (2 if empty_on_recheck else 1))

    def test_disabled_apply_fails_before_transport_and_heartbeat_does_nothing(self):
        def forbidden(*args, **kwargs):
            self.fail('disabled pass called transport')
        with patch.dict(os.environ, {'TED_MOCKUP_AUTOARCHIVE_ENABLED': ''}):
            with self.assertRaises(RuntimeError):
                archive.run_pass(dry_run=False, mockup_call=forbidden, cards_call=forbidden)
            self.assertEqual(archive.heartbeat_pass(), [])

    def test_changed_batch_is_not_archived(self):
        def response(action, payload, count):
            self.assertIsNone(action)
            return dict(mockups=[frame(verdict='approved')] + ([frame('new')] if count > 1 else []), pins=[])
        result, calls, events = self.run_pass(dry_run=False, responder=response)
        self.assertEqual([c[0] for c in calls], [None, None])
        self.assertEqual(result[0]['event'], 'skipped_changed')

    def test_card_reopened_before_apply_is_not_archived(self):
        calls = []
        cards = iter([[dict(id='x', project='Fictora', section='done', title='build approved: Home v1')],
                      [dict(id='x', project='Fictora', section='up_next', title='build approved: Home v1')]])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}):
            def transport(action=None, **payload):
                calls.append(action)
                return dict(mockups=[frame()], pins=[])
            result = archive.run_pass(dry_run=False, mockup_call=transport,
                cards_call=lambda **kw: dict(cards=next(cards)), log_path=Path(tmp)/'log', now=NOW)
        self.assertEqual(calls, [None, None])
        self.assertEqual(result[0]['event'], 'skipped_changed')

    def test_failed_or_unconfirmed_archive_is_logged_without_private_error(self):
        for receipt in (RuntimeError('secret transport details'), dict(ok=False),
                        dict(ok=True, archived=0), dict(ok=True, archived=True)):
            def response(action, payload, count):
                if action is None:
                    return dict(mockups=[frame(verdict='approved')], pins=[])
                if isinstance(receipt, Exception):
                    raise receipt
                return receipt
            result, calls, events = self.run_pass(dry_run=False, responder=response)
            self.assertEqual(result[0]['event'], 'archive_failed')
            self.assertNotIn('secret transport details', json.dumps(events))

    def test_malformed_read_fails_closed(self):
        for payload in ({}, dict(mockups=None), dict(mockups=[None])):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.run_pass(responder=lambda *args: payload)

    def test_one_failed_archive_does_not_stop_other_batches(self):
        rows = [frame(verdict='approved'), frame('b', batch='Other v1', verdict='approved')]
        def response(action, payload, count):
            if action is None:
                return dict(mockups=rows, pins=[])
            if ('a' in payload.get('ids', []) or payload.get('batch') == 'Home v1'):
                raise RuntimeError('private details')
            return dict(ok=True, archived=1)
        result, calls, events = self.run_pass(rows=rows, dry_run=False, responder=response)
        self.assertEqual([r['event'] for r in result], ['archive_failed', 'archived'])
        self.assertEqual([payload['ids'] for action, payload in calls if action == 'archive'],
                         [['a'], ['b']])

    def test_log_failure_prevents_archive(self):
        calls = []
        def transport(action=None, **payload):
            calls.append(action)
            return dict(mockups=[frame(verdict='approved')], pins=[])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}):
            bad_log = Path(tmp) / 'directory';bad_log.mkdir()
            with self.assertRaises(OSError):
                archive.run_pass(dry_run=False, mockup_call=transport,
                    cards_call=lambda **kw: dict(cards=[unrelated_card()]), log_path=bad_log, now=NOW)
        self.assertNotIn('archive', calls)

    def test_cli_defaults_to_dry_run(self):
        calls = []
        def run_pass(**kwargs):
            calls.append(kwargs['dry_run'])
            return []
        with patch.object(archive, 'run_pass', side_effect=run_pass), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(archive.main([]), 0)
            self.assertEqual(archive.main(['--dry-run']), 0)
            self.assertEqual(archive.main(['--apply']), 0)
        self.assertEqual(calls, [True, True, False])

    def test_cli_reports_missing_snapshot_helper_without_a_traceback(self):
        deps = dict(board_card_snapshot=None,
                    mockup_client=types.SimpleNamespace(call=lambda: dict(mockups=[], pins=[])),
                    board_client=types.SimpleNamespace(call=lambda **kw: dict(cards=[unrelated_card()])))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, deps), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            result = archive.main(['--dry-run', '--log', str(Path(tmp)/'log.jsonl')])
        self.assertEqual(result, 1)
        self.assertNotIn('Traceback', err.getvalue())
        self.assertNotIn('board_card_snapshot', err.getvalue())
        self.assertIn('Mockup auto-archive failed.', err.getvalue())

    def test_cli_reports_invalid_card_body_without_a_type_error(self):
        deps = dict(mockup_client=types.SimpleNamespace(call=lambda: dict(
                        mockups=[frame(verdict='needs_work')], pins=[])),
                    board_client=types.SimpleNamespace(call=lambda **kw: dict(cards=[dict(
                        id='x', project='Fictora', section='done', title='Build', body={'private': 'data'})])))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, deps), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            result = archive.main(['--dry-run', '--log', str(Path(tmp)/'log.jsonl')])
        self.assertEqual(result, 1)
        self.assertNotIn('Traceback', err.getvalue())
        self.assertNotIn('private', err.getvalue())


class PersistentOutcomes(unittest.TestCase):
    def run_pass(self, log, *, outcome=None, rows=None, fresh=None, module=archive, now=NOW):
        initial = [frame(verdict='approved')] if rows is None else rows
        reads = 0
        def transport(action=None, **payload):
            nonlocal reads
            if action is None:
                reads += 1
                return dict(mockups=fresh if reads > 1 and fresh is not None else initial, pins=[])
            if isinstance(outcome, Exception):
                raise outcome
            return dict(ok=True, archived=len(payload['ids']))
        with patch.dict(os.environ, {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}):
            return module.run_pass(dry_run=False, mockup_call=transport, cards_call=lambda **kw: dict(cards=[unrelated_card()]),
                                   log_path=log, now=now)

    def events(self, log):
        return [json.loads(line) for line in log.read_text().splitlines()]

    def test_repeated_failure_logs_once_across_module_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            first = self.run_pass(log, outcome=RuntimeError('first private message'))
            reloaded = load('reloaded_outcomes', 'mockup_autoarchive.py')
            second = self.run_pass(log, outcome=RuntimeError('different private message'), module=reloaded,
                                   now=NOW + timedelta(minutes=10))
            self.assertEqual(first[0]['event'], 'archive_failed')
            self.assertEqual(second[0]['event'], 'archive_failed')
            names = [event['event'] for event in self.events(log)]
            self.assertEqual(names.count('archive_failed'), 1)
            self.assertEqual(names.count('archive_attempt'), 2)

    def test_failure_logs_again_when_error_or_batch_ids_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            self.run_pass(log, outcome=RuntimeError())
            self.run_pass(log, outcome=TimeoutError())
            self.run_pass(log, outcome=TimeoutError(), rows=[frame('b', verdict='approved')])
            self.assertEqual([e['error_type'] for e in self.events(log) if e['event'] == 'archive_failed'],
                             ['RuntimeError', 'TimeoutError', 'TimeoutError'])

    def test_repeated_skipped_change_logs_once_until_observed_state_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            changed = [frame(verdict='approved'), frame('b', verdict='approved')]
            for i in range(2):
                result = self.run_pass(log, fresh=changed, now=NOW + timedelta(minutes=10*i))
                self.assertEqual(result[0]['event'], 'skipped_changed')
            self.run_pass(log, fresh=[frame(verdict='approved'), frame('c', verdict='approved')])
            self.assertEqual([e['event'] for e in self.events(log)], ['skipped_changed', 'skipped_changed'])

    def test_changed_outcome_and_loss_of_eligibility_reset_backoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            self.run_pass(log, outcome=RuntimeError())
            self.run_pass(log)
            self.run_pass(log, outcome=RuntimeError())
            self.run_pass(log, rows=[])
            self.run_pass(log, outcome=RuntimeError())
            names = [e['event'] for e in self.events(log)]
            self.assertEqual(names.count('archive_failed'), 3)
            self.assertEqual(names.count('archived'), 1)

    def test_corrupt_outcome_state_fails_closed_before_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            log.with_suffix('.state.json').write_text('{invalid')
            calls = []
            def transport(*args, **kwargs):
                calls.append(args)
                return dict(mockups=[], pins=[])
            with patch.dict(os.environ, {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}):
                with self.assertRaises(ValueError):
                    archive.run_pass(dry_run=False, mockup_call=transport, cards_call=lambda **kw: dict(cards=[unrelated_card()]),
                                     log_path=log, now=NOW)
            self.assertEqual(calls, [])

    def test_invalid_persisted_cadence_or_outcome_map_fails_closed(self):
        for state in (dict(heartbeat_at='invalid', batches={}), dict(heartbeat_at=None, batches=[]),
                      dict(heartbeat_at=None, batches={'batch': None})):
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / 'archive.jsonl'
                log.with_suffix('.state.json').write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    self.run_pass(log)

    def test_dry_run_creates_only_its_requested_audit_log(self):
        for rows, expected_files in (([], []), ([frame(verdict='approved')], ['archive.jsonl'])):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp);log = root / 'archive.jsonl'
                result = archive.run_pass(dry_run=True, mockup_call=lambda: dict(mockups=rows, pins=[]),
                    cards_call=lambda **kw: dict(cards=[unrelated_card()]), log_path=log, now=NOW)
                self.assertEqual(sorted(p.name for p in root.iterdir()), expected_files)
                self.assertEqual(len(result), len(rows))

    def test_dry_run_preserves_existing_throttle_and_backoff_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);log = root / 'archive.jsonl'
            self.run_pass(log, outcome=RuntimeError())
            state = log.with_suffix('.state.json');lock = state.with_suffix('.lock')
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (state, lock)}
            archive.run_pass(dry_run=True, mockup_call=lambda: dict(mockups=[], pins=[]),
                             cards_call=lambda **kw: dict(cards=[unrelated_card()]), log_path=log, now=NOW)
            after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (state, lock)}
            self.assertEqual(after, before)
            self.run_pass(log, outcome=RuntimeError(), now=NOW + timedelta(minutes=10))
            self.assertEqual([e['event'] for e in self.events(log)].count('archive_failed'), 1)

    def test_dry_run_does_not_read_corrupt_control_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);log = root / 'archive.jsonl';state = log.with_suffix('.state.json')
            state.write_text('{invalid')
            result = archive.run_pass(dry_run=True, mockup_call=lambda: dict(mockups=[], pins=[]),
                                      cards_call=lambda **kw: dict(cards=[unrelated_card()]), log_path=log, now=NOW)
            self.assertEqual(result, [])
            self.assertEqual(state.read_text(), '{invalid')
            self.assertEqual(list(root.iterdir()), [state])


class LockContention(unittest.TestCase):
    def test_busy_lock_times_out_before_transport_or_control_state_change(self):
        calls = []
        def transport(*args, **kwargs):
            calls.append(args)
            return dict(mockups=[], pins=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);log = root/'archive.jsonl';state = log.with_suffix('.state.json')
            state.write_text(json.dumps(dict(heartbeat_at=OLD, batches={})))
            before = (state.read_bytes(), state.stat().st_mtime_ns)
            with patch.dict(os.environ, {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}), \
                    patch.object(archive.fcntl, 'flock', side_effect=BlockingIOError()), \
                    patch('time.monotonic', side_effect=[0.0, 0.0, 1.01]), patch('time.sleep'):
                with self.assertRaises(TimeoutError):
                    archive.run_pass(dry_run=False, mockup_call=transport, cards_call=lambda **kw: dict(cards=[unrelated_card()]),
                                     log_path=log, now=NOW, heartbeat=True)
            self.assertEqual(calls, [])
            self.assertEqual((state.read_bytes(), state.stat().st_mtime_ns), before)
            self.assertFalse(log.exists())

    def test_transient_lock_contention_retries_then_releases_lock(self):
        real_flock = archive.fcntl.flock
        attempts = []
        def briefly_busy(fd, operation):
            attempts.append(operation)
            if len(attempts) == 1:
                raise BlockingIOError()
            return real_flock(fd, operation)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp)/'archive.jsonl'
            with patch.dict(os.environ, {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}), \
                    patch.object(archive.fcntl, 'flock', side_effect=briefly_busy), patch('time.sleep'):
                result = archive.run_pass(dry_run=False,
                    mockup_call=lambda: dict(mockups=[], pins=[]), cards_call=lambda **kw: dict(cards=[unrelated_card()]), log_path=log, now=NOW)
            self.assertEqual(result, [])
            self.assertTrue(all(operation & archive.fcntl.LOCK_NB for operation in attempts))
            with log.with_suffix('.state.lock').open('a') as lock:
                real_flock(lock, archive.fcntl.LOCK_EX | archive.fcntl.LOCK_NB)


class HeartbeatRate(unittest.TestCase):
    def run_heartbeat(self, module, log, at, transport):
        deps = dict(mockup_client=types.SimpleNamespace(call=transport),
                    board_client=types.SimpleNamespace(call=lambda **kw: dict(cards=[unrelated_card()])))
        with patch.dict(os.environ, {'TED_MOCKUP_AUTOARCHIVE_ENABLED': 'true'}), patch.dict(sys.modules, deps):
            return module.heartbeat_pass(now=at, log_path=log)

    def test_ten_minute_limit_persists_across_reloads_and_allows_boundary(self):
        reads = []
        def transport(action=None, **payload):
            self.assertIsNone(action)
            reads.append(action)
            return dict(mockups=[], pins=[])
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            self.run_heartbeat(archive, log, NOW, transport)
            reloaded = load('reloaded_heartbeat', 'mockup_autoarchive.py')
            self.run_heartbeat(reloaded, log, NOW + timedelta(minutes=9, seconds=59), transport)
            self.assertEqual(len(reads), 1)
            self.run_heartbeat(reloaded, log, NOW + timedelta(minutes=10), transport)
            self.assertEqual(len(reads), 2)
            self.run_heartbeat(reloaded, log, NOW + timedelta(minutes=10, seconds=30), transport)
            self.run_heartbeat(reloaded, log, NOW + timedelta(minutes=9), transport)
            self.assertEqual(len(reads), 2)

    def test_failed_pass_is_rate_limited_before_the_network_read(self):
        reads = []
        def transport(*args, **kwargs):
            reads.append('read')
            raise RuntimeError('network unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'archive.jsonl'
            with self.assertRaises(RuntimeError):
                self.run_heartbeat(archive, log, NOW, transport)
            self.assertEqual(self.run_heartbeat(archive, log, NOW + timedelta(seconds=30), transport), [])
            self.assertEqual(len(reads), 1)
            with self.assertRaises(RuntimeError):
                self.run_heartbeat(archive, log, NOW + timedelta(minutes=10), transport)
            self.assertEqual(len(reads), 2)

    def test_future_saved_heartbeat_resets_only_beyond_ten_minutes(self):
        for ahead, resets in ((timedelta(minutes=10), False),
                              (timedelta(minutes=10, microseconds=1), True),
                              (timedelta(days=1), True)):
            reads = []
            def transport(action=None, **payload):
                self.assertIsNone(action)
                reads.append(action)
                return dict(mockups=[], pins=[])
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / 'archive.jsonl'
                self.run_heartbeat(archive, log, NOW + ahead, transport)
                self.run_heartbeat(archive, log, NOW, transport)
                self.assertEqual(len(reads), 2 if resets else 1, ahead)
                self.run_heartbeat(archive, log, NOW + timedelta(seconds=30), transport)
                self.assertEqual(len(reads), 2 if resets else 1)

    def test_disabled_heartbeat_creates_no_state_or_log(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                {'TED_MOCKUP_AUTOARCHIVE_ENABLED': ''}):
            self.assertEqual(archive.heartbeat_pass(now=NOW, log_path=Path(tmp)/'log.jsonl'), [])
            self.assertEqual(list(Path(tmp).iterdir()), [])


@unittest.skipUnless((ROOT / 'jobs_heartbeat.py').exists(), 'private heartbeat candidate required')
class Heartbeat(unittest.TestCase):
    def test_archive_failure_does_not_interrupt_existing_heartbeat(self):
        actions = []
        def call(action, **kwargs):
            actions.append(action)
            return dict(commands=[], ok=True, cleared=[])
        store = types.SimpleNamespace(controls=lambda _: None, tick=lambda: None,
            collect_approvals=lambda: None, sync_approval_status=lambda: None,
            flush=lambda: None, snapshot=lambda: ([], []))
        def fail():
            raise RuntimeError('private transport details')
        deps = dict(board_client=types.SimpleNamespace(call=call, cards=lambda: []),
            sessions=types.SimpleNamespace(Store=lambda: store, identity=lambda _: ''),
            fresh_ted=types.SimpleNamespace(dispatch=lambda: None),
            mockup_autoarchive=types.SimpleNamespace(heartbeat_pass=fail))
        heartbeat = load('candidate_heartbeat', 'jobs_heartbeat.py', deps)
        with patch.object(heartbeat, 'untracked', return_value=[]), patch.dict(sys.modules, deps), \
                contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(heartbeat.main(), 0)
        self.assertIn('Mockup auto-archive failed', err.getvalue())
        self.assertNotIn('private transport details', err.getvalue())
        self.assertEqual(actions, ['control', 'heartbeat', 'veto_clear_due'])


if __name__ == '__main__':
    unittest.main()
