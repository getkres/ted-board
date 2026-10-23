import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inbox_steward as steward
import steward_review

NOW = datetime(2026, 10, 23, 2, tzinfo=timezone.utc).timestamp()
OLD = '2026-10-01T00:00:00Z'
RECENT = '2026-10-22T00:00:00Z'


def card(cid='worker', text='Finished the work and opened PR #12.', **kw):
    return dict(id=cid, project='Test', title='Build screens', body='Implement screens',
                section='needs_you', updated_at=OLD, revision=1,
                messages=[dict(who='ted', at=OLD, text=text)], **kw)


def image(batch='Study v1', mid='m1', **kw):
    return dict(dict(id=mid, project='Test', batch=batch, title='Screen',
                     status='open', created_at=OLD, verdict=None), **kw)


class CardRules(unittest.TestCase):
    def target(self, c):
        return steward.plan([c], [], [], NOW)['actions']

    def test_worker_reports_go_to_ted_review(self):
        for text in ['Finished.', 'Opened PR #3.', 'Uploaded the screens.',
                     'The patch was applied.', 'Merged PR #3.', 'The page is live.']:
            with self.subTest(text=text):
                actions = self.target(card(text=text))
                self.assertEqual([(a['to'], a['reason']) for a in actions], [('up_next', 'Ted review')])

    def test_fyi_goes_done_only_without_an_action(self):
        for text in ['Export completed. No action required.', 'Payment receipt. Thank you.',
                     'Welcome to the newsletter.', 'Subscription confirmation. No action needed.']:
            with self.subTest(text=text):
                self.assertEqual(self.target(card(text=text))[0]['to'], 'done')
        for text in ['Receipt attached. Please approve the charge.',
                     'Subscription notice: update your payment method.',
                     'Export completed. Please review the failed rows.']:
            self.assertEqual(self.target(card(text=text)), [])

    def test_approvals_and_decisions_win_over_completed_words(self):
        cases = [dict(decision_kind='other'), dict(decision_kind='send_email'),
                 dict(pending_approval=True), dict(approval={'status': 'pending'}),
                 dict(options=[{'label': 'Yes', 'value': 'yes'}]),
                 dict(steps=[{'text': 'Apply SQL'}]), dict(amount_cents=5000)]
        for fields in cases:
            with self.subTest(fields=fields):
                self.assertEqual(self.target(card(**fields)), [])
        for text in ['Uploaded. Awaiting your pick.', 'Finished. Approval needed: send the exact email.',
                     'Opened PR #3. Blocked at the database gate. Review apply.sql.',
                     'Uploaded. Choose a design.', 'Not finished yet.',
                     'The migration has not been applied.', 'The page is not live yet.']:
            with self.subTest(text=text):
                self.assertEqual(self.target(card(text=text)), [])
        c = card(); c['body'] = 'Contract signature needed.'
        self.assertEqual(self.target(c), [])

    def test_recent_sebastian_reply_and_answer_are_protected(self):
        for who in ['seb', 'sebastian']:
            c = card(); c['messages'].insert(0, dict(who=who, at=RECENT, text='Keep this.'))
            self.assertEqual(self.target(c), [])
        self.assertEqual(self.target(card(answer={'created_at': RECENT, 'choice': 'note'})), [])
        self.assertEqual(self.target(card(created_by='ted', created_at=RECENT, needs_you=True)), [])
        self.assertEqual(self.target(card(text='Finished.', created_by='ted', created_at=OLD, needs_you=True))[0]['to'], 'up_next')

    def test_latest_message_uses_timestamp_and_requires_worker_author(self):
        c = card(); c['messages'].insert(0, dict(who='ted', at='2026-10-20T00:00:00Z', text='Awaiting your approval.'))
        self.assertEqual(self.target(c), [])
        for who in ['seb', 'unknown']:
            c = card(); c['messages'][0]['who'] = who
            self.assertEqual(self.target(c), [])
        c = card(); c['messages'][0]['at'] = 'bad'
        self.assertEqual(self.target(c), [])
        c = card(); c['section'] = 'up_next'
        self.assertEqual(self.target(c), [])

    def test_notices_with_pending_actions_or_email_drafts_stay_put(self):
        for text in ['Subscription notice: payment failed.', 'Receipt: outstanding balance due.',
                     'Confirmation: you must verify your account.', 'Finished draft-email.json.',
                     'Finished. Send email needs approval.', 'Subscription notices: cancellation required.']:
            with self.subTest(text=text):
                self.assertEqual(self.target(card(text=text)), [])

    def test_fyi_without_messages_can_use_card_body(self):
        c = card(); c.update(messages=[], title='Export completed', body='Export completed. No action needed.')
        self.assertEqual(self.target(c)[0]['to'], 'done')

    def test_snapshot_protection_checks_draft_and_veto_metadata(self):
        for fields in [dict(approval={'status': 'cleared'}), dict(veto={'status': 'pending'}),
                       dict(pending_approval={'kind': 'spend'})]:
            self.assertEqual(self.target(card(**fields)), [])

    def test_worker_report_with_receipt_is_ted_review_not_fyi(self):
        actions = self.target(card(text='Finished the export service. Uploaded the receipt for the job.'))
        self.assertEqual(actions[0]['to'], 'up_next')
        self.assertEqual(self.target(card(text='Not finished yet. Receipt attached.')), [])


class MockupRules(unittest.TestCase):
    def actions(self, rows, cards=None, pins=None):
        return steward.plan(cards or [], rows, pins or [], NOW)['actions']

    def test_newer_same_base_batch_archives_older_in_same_project(self):
        rows = [image('Study v2'), image('Study FINAL restart', 'm2')]
        rows[1]['created_at'] = '2026-10-10T00:00:00Z'
        a = self.actions(rows)
        self.assertEqual([(x['project'], x['batch']) for x in a], [('Test', 'Study v2')])
        rows[1]['project'] = 'Other'
        self.assertEqual(self.actions(rows), [])

    def test_version_only_normalization_does_not_merge_different_studies(self):
        rows = [image('Study v2: hair'), image('Study v3: brows', 'm2')]
        rows[1]['created_at'] = RECENT
        self.assertEqual(self.actions(rows), [])
        rows = [image(), image('Study v2', 'm2')]
        self.assertEqual(self.actions(rows), [])
        rows[1]['created_at'] = 'bad'
        self.assertEqual(self.actions(rows), [])

    def test_all_verdicts_archive_but_partial_verdicts_do_not(self):
        rows = [image(verdict='approved'), image(mid='m2', verdict='scrapped')]
        self.assertEqual(len(self.actions(rows)), 1)
        rows[1]['verdict'] = None
        self.assertEqual(self.actions(rows), [])
        rows[1]['status'] = 'picked'
        self.assertEqual(len(self.actions(rows)), 1)

    def test_pending_build_approvals_and_recent_feedback_block_archives(self):
        rows = [image(verdict='approved')]
        build = card('build'); build.update(title='build approved: Study v1', section='ted_doing')
        self.assertEqual(self.actions(rows, [build]), [])
        build['section'] = 'done'
        self.assertEqual(len(self.actions(rows, [build])), 1)
        decision = card('decision', decision_kind='approve_design'); decision['body'] = 'Review Study v1'
        self.assertEqual(self.actions(rows, [decision]), [])
        pin = dict(mockup_id='m1', resolved=True, created_at=OLD,
                   thread=[dict(who='seb', at=RECENT, text='Keep it.')])
        self.assertEqual(self.actions(rows, pins=[pin]), [])
        pin.update(resolved=False, thread=[])
        self.assertEqual(self.actions(rows, pins=[pin]), [])

    def test_old_just_looking_studies_archive_after_last_activity(self):
        for name in ['Reference lock', 'Inventory', 'Side-by-side']:
            rows = [image(name)]
            self.assertEqual(len(self.actions(rows)), 1)
            pin = dict(mockup_id='m1', resolved=True, created_at=OLD,
                       thread=[dict(who='ted', at=RECENT, text='Updated.')])
            self.assertEqual(self.actions(rows, pins=[pin]), [])
        self.assertEqual(self.actions([image('App screens')]), [])

    def test_archived_rows_never_generate_actions(self):
        row = image(verdict='approved'); row['status'] = 'archived'
        self.assertEqual(self.actions([row]), [])

    def test_inventory_screen_in_real_app_batch_is_not_a_study(self):
        row = image('New app'); row['title'] = 'Inventory screen'
        self.assertEqual(self.actions([row]), [])

    def test_undated_activity_cannot_make_a_study_look_stale(self):
        row = image('Inventory')
        pin = dict(mockup_id='m1', resolved=True, created_at=OLD,
                   thread=[dict(who='ted', text='Recently reviewed.')])
        self.assertEqual(self.actions([row], pins=[pin]), [])

    def test_recent_verdict_is_recent_sebastian_activity(self):
        row = image(verdict='approved', verdict_change={'at': RECENT})
        self.assertEqual(self.actions([row]), [])


class Runner(unittest.TestCase):
    def run_steward(self, root, cards, mockups=None, pins=None, dry=False, move_result=None):
        payload = dict(mockups=mockups or [], pins=pins or [])
        def apply_move(cid, value, note):
            for row in cards:
                if row['id'] == cid:
                    row['section'] = value
            return move_result or {'ok': True}
        with patch.object(steward, 'fetch_cards', return_value=cards), \
             patch.object(steward, 'fetch_mockups', return_value=payload), \
             patch.object(steward, 'move_card', side_effect=apply_move) as move, \
             patch.object(steward, 'archive_batch', return_value={'ok': True, 'archived': 1}) as archive:
            result = steward.run_once(Path(root), dry_run=dry, now=NOW)
        return result, move, archive

    def test_dry_run_has_no_mutations_or_journal_writes(self):
        with tempfile.TemporaryDirectory() as root:
            r, move, archive = self.run_steward(root, [card()], dry=True)
            self.assertEqual(r['planned_moves'], 1)
            self.assertEqual(r['moved'], 0)
            self.assertFalse(move.called or archive.called)
            self.assertFalse((Path(root)/'steward-log.jsonl').exists())
            self.assertFalse((Path(root)/'steward-overflow.json').exists())

    def test_live_move_is_logged_and_overflow_is_stale_first(self):
        cards = [card()]+[card(str(i), text='A judgment call remains.') for i in range(14)]
        cards[1]['updated_at'] = '2026-10-21T00:00:00Z'
        with tempfile.TemporaryDirectory() as root:
            r, move, archive = self.run_steward(root, cards)
            self.assertEqual(r['moved'], 1)
            self.assertEqual(move.call_args.args, ('worker', 'up_next', 'Ted review'))
            log = [json.loads(x) for x in (Path(root)/'steward-log.jsonl').read_text().splitlines()]
            done = [x for x in log if x['outcome'] == 'applied']
            self.assertEqual([(x['card_id'], x['from'], x['to']) for x in done], [('worker', 'needs_you', 'up_next')])
            overflow = json.loads((Path(root)/'steward-overflow.json').read_text())
            self.assertEqual(overflow['excess_count'], 2)
            self.assertEqual(len(overflow['extras']), 2)
            self.assertEqual(len(overflow['ranked']), 14)
            self.assertNotEqual(overflow['ranked'][0]['id'], '0')

    def test_snapshot_change_defers_action(self):
        c = card(); changed = card(); changed['messages'].append(dict(who='seb', at=RECENT, text='Keep.'))
        with tempfile.TemporaryDirectory() as root, \
             patch.object(steward, 'fetch_cards', side_effect=[[c], [changed], [changed]]), \
             patch.object(steward, 'fetch_mockups', return_value=dict(mockups=[], pins=[])), \
             patch.object(steward, 'move_card') as move:
            r = steward.run_once(Path(root), now=NOW)
            self.assertFalse(move.called)
            self.assertEqual(r['deferred'], 1)

    def test_failure_is_recorded_without_printing_raw_error(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(steward, 'fetch_cards', return_value=[card()]), \
             patch.object(steward, 'fetch_mockups', return_value=dict(mockups=[], pins=[])), \
             patch.object(steward, 'move_card', side_effect=RuntimeError('secret-token=do-not-print')):
            r = steward.run_once(Path(root), now=NOW)
            self.assertEqual(r['failed'], 1)
            text = (Path(root)/'steward-log.jsonl').read_text()
            self.assertNotIn('do-not-print', text)
            self.assertIn('uncertain', text)

    def test_archive_uses_exact_project_and_batch_and_journals_it(self):
        with tempfile.TemporaryDirectory() as root:
            r, move, archive = self.run_steward(root, [], [image(verdict='scrapped')])
            self.assertEqual(r['archived_batches'], 1)
            self.assertEqual(archive.call_args.args, ('Test', 'Study v1'))
            self.assertIn('archived', (Path(root)/'steward-log.jsonl').read_text())

    def test_adapters_use_existing_transports_and_page_key_only_for_moves(self):
        import types
        board = types.SimpleNamespace(cards=lambda: [], call=lambda *a, **kw: (a, kw))
        mockups = types.SimpleNamespace(call=lambda *a, **kw: (a, kw))
        with patch.dict(sys.modules, board_client=board, mockup_client=mockups):
            self.assertEqual(steward.move_card('c1', 'up_next', 'Ted review'),
                             (('move',), dict(page=True, card_id='c1', value='up_next', note='Ted review')))
            self.assertEqual(steward.archive_batch('Test', 'Study'),
                             (('archive',), dict(project='Test', batch='Study')))

    def test_batch_changed_before_archive_is_deferred(self):
        row = image(verdict='approved')
        pin = dict(mockup_id='m1', resolved=True, created_at=OLD,
                   thread=[dict(who='seb', at=RECENT, text='Keep this.')])
        with tempfile.TemporaryDirectory() as root, \
             patch.object(steward, 'fetch_cards', return_value=[]), \
             patch.object(steward, 'fetch_mockups', side_effect=[dict(mockups=[row], pins=[]), dict(mockups=[row], pins=[pin])]), \
             patch.object(steward, 'archive_batch') as archive:
            result = steward.run_once(Path(root), now=NOW)
            self.assertEqual(result['deferred'], 1)
            self.assertFalse(archive.called)

    def test_empty_overflow_replaces_a_previous_overflow(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'steward-overflow.json'
            path.write_text('{"excess_count": 9}')
            self.run_steward(root, [])
            self.assertEqual(json.loads(path.read_text())['extras'], [])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_incomplete_snapshots_are_refused(self):
        import types
        board = types.SimpleNamespace(cards=lambda: [card()]*500)
        mockups = types.SimpleNamespace(call=lambda: dict(mockups=[]))
        with patch.dict(sys.modules, board_client=board, mockup_client=mockups):
            with self.assertRaises(RuntimeError):
                steward.fetch_cards()
            with self.assertRaises(RuntimeError):
                steward.fetch_mockups()

    def test_unconfirmed_api_response_is_not_counted_as_applied(self):
        with tempfile.TemporaryDirectory() as root:
            result, move, archive = self.run_steward(root, [card()], move_result={'ok': False})
            self.assertEqual(result['failed'], 1)
            self.assertEqual(result['moved'], 0)

    def test_mini_guard_rejects_macbook(self):
        import types
        with patch.object(steward.subprocess, 'run', return_value=types.SimpleNamespace(stdout='MacBook Pro')):
            with self.assertRaises(RuntimeError):
                steward.require_mini()
        with patch.object(steward.subprocess, 'run', return_value=types.SimpleNamespace(stdout='Sebastian Mac Mini')):
            steward.require_mini()

    def test_review_prints_compact_ambiguous_rows_and_redacts_sensitive_text(self):
        c = card(text='See https://example.test/#k=private and token=hidden.')
        out = io.StringIO()
        with patch.object(steward, 'fetch_cards', return_value=[c]), \
             patch.object(steward, 'fetch_mockups', return_value=dict(mockups=[], pins=[])), \
             contextlib.redirect_stdout(out):
            steward_review.main([], now=NOW)
        text = out.getvalue()
        self.assertIn('worker', text); self.assertIn('Test', text); self.assertIn('Build screens', text)
        self.assertIn('keep', text); self.assertNotIn('private', text); self.assertNotIn('hidden', text)


if __name__ == '__main__':
    unittest.main()
