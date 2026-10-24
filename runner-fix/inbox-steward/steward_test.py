import contextlib
import io
import os
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

if not os.environ.get('TED_STEWARD_RUNTIME'):
    raise SystemExit('Set TED_STEWARD_RUNTIME to a prepared private candidate. This suite does not run in CI.')
SOURCE = Path(os.environ['TED_STEWARD_RUNTIME'])
sys.path.insert(0, str(SOURCE))
import inbox_steward as steward
import steward_review

NOW = datetime(2026, 10, 23, 2, tzinfo=timezone.utc).timestamp()
OLD = '2026-10-01T00:00:00Z'
RECENT = '2026-10-22T00:00:00Z'


def card(cid='worker', text='Finished the work and opened PR #12.', **kw):
    return dict(id=cid, project='Test', title='Build screens', body='Implement screens',
                section='needs_you', updated_at=OLD, revision=1,
                messages=[dict(who='ted', at=OLD, text=text)], **kw)


class CardRules(unittest.TestCase):
    def target(self, c):
        return steward.plan([c], NOW)['actions']

    def test_worker_reports_go_to_ted_review(self):
        for text in ['Finished.', 'Opened PR #3.', 'Uploaded the screens.',
                     'The patch was applied.', 'Merged PR #3.', 'The page is live.', 'Uploaded 3 screens.']:
            with self.subTest(text=text):
                actions = self.target(card(text=text))
                self.assertEqual([(a['to'], a['reason']) for a in actions], [('up_next', 'Ted review')])

    def test_fyi_goes_done_only_without_an_action(self):
        for text in ['Export completed. No action required.', 'Export completed. Receipt attached.']:
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

    def test_fyi_without_a_dated_worker_message_stays_for_review(self):
        c = card(); c.update(messages=[], title='Export completed', body='Export completed. No action needed.')
        self.assertEqual(self.target(c), [])

    def test_snapshot_protection_checks_draft_and_veto_metadata(self):
        for fields in [dict(approval={'status': 'cleared'}), dict(veto={'status': 'pending'}),
                       dict(pending_approval={'kind': 'spend'})]:
            self.assertEqual(self.target(card(**fields)), [])

    def test_worker_report_with_receipt_is_ted_review_not_fyi(self):
        actions = self.target(card(text='Finished the export service. Uploaded the receipt for the job.'))
        self.assertEqual(actions[0]['to'], 'up_next')
        self.assertEqual(self.target(card(text='Not finished yet. Receipt attached.')), [])

    def test_ordinary_completed_reports_without_decision_signals_can_move(self):
        cases = [
            ('Uploaded the hero. The reference caption says "please welcome the cast".', 'Build the hero.'),
            ('Finished the page.', 'Can you build a settings page?'),
            ('Uploaded the screens. The layout must show five locked worlds.', 'Build the closet.'),
        ]
        for text, body in cases:
            with self.subTest(text=text):
                c = card(text=text); c['body'] = body
                self.assertEqual([a['to'] for a in self.target(c)], ['up_next'])

    def test_real_legacy_requests_remain_protected(self):
        for text, body in [
            ('Finished the draft. Please approve the $500 payment.', 'Prepare the proposal.'),
            ('Uploaded. Can you choose a design?', 'Build a design.'),
            ('Finished. Awaiting your approval.', 'Build the page.'),
            ('Uploaded the deck.', 'Authorize a $500 payment.'),
            ('Uploaded the proposals.', 'You pick one, then we build it.'),
            ('Finished. Which route is best?', 'Build a proposal.'),
            ('Uploaded. Should I send this?', 'Prepare a proposal.'),
        ]:
            with self.subTest(text=text):
                c = card(text=text); c['body'] = body
                self.assertEqual(self.target(c), [])

    def test_delivery_assurances_do_not_negate_a_positive_report(self):
        for text in [
            'Finished the page. It is not live yet.',
            'Uploaded the screens. No code was merged.',
            'Opened PR #14. The patch has not been applied.',
        ]:
            self.assertEqual([a['to'] for a in self.target(card(text=text))], ['up_next'])
        for text in ['The patch has not been applied.', 'Not finished yet.', 'I will upload the screens tomorrow.', 'I will have finished tomorrow.', 'No code was merged.']:
            self.assertEqual(self.target(card(text=text)), [])

    def test_completed_report_variants_are_recognized(self):
        for text in ['PR #14 is open.', 'The screens are up on the board.', 'Implementation completed.',
                     'The page has been deployed.']:
            with self.subTest(text=text):
                self.assertEqual([a['to'] for a in self.target(card(text=text))], ['up_next'])

    def test_pending_copy_choices_are_not_completed_worker_reports(self):
        c = card(text='The batch is up in Mockups. Pin a box and type your version, or say a letter.')
        c['body'] = 'Three starter drafts. Pin and type your version.'
        self.assertEqual(self.target(c), [])

    def test_active_workers_are_not_moved_by_incidental_report_words(self):
        self.assertEqual(self.target(card(text='The PR was merged, continuing the release audit.', live_state='running')), [])

    def test_conditional_merge_instructions_are_not_completed_reports(self):
        self.assertEqual(self.target(card(text='PR will follow. Include the result only if merged by 04:00.')), [])

    def test_uploaded_logo_options_stay_in_needs_you(self):
        self.assertEqual(self.target(card(text='Uploaded 3 logo options for you to look at.')), [])

    def test_uploaded_mockups_requesting_sebastian_choice_stay(self):
        self.assertEqual(self.target(card(text='Uploaded the mockups. Tell Sebastian which he likes.')), [])

    def test_finished_work_waiting_for_sign_off_stays(self):
        self.assertEqual(self.target(card(text='Finished. Ready for your sign-off.')), [])

    def test_uploaded_work_requesting_favorite_stays(self):
        self.assertEqual(self.target(card(text='Uploaded. Reply with your favorite')), [])

    def test_finished_pricing_change_waiting_for_agreement_stays(self):
        self.assertEqual(self.target(card(text='Finished the new pricing page, price goes to $39 if you agree.')), [])

    def test_open_pr_with_monthly_price_change_stays(self):
        self.assertEqual(self.target(card(text='Opened PR #9 to change the price to 19.99 monthly')), [])

    def test_finished_work_with_daily_ad_budget_stays(self):
        self.assertEqual(self.target(card(text='Finished; ad budget raised to 500 per day')), [])

    def test_report_only_gate_rejects_each_ambiguous_input_family(self):
        for tail in ['You can inspect it.', 'Your asset is attached.', 'Sebastian received it.',
                     'Any update?', 'Pick a color.', 'Favorite attached.', 'Prefer the blue.',
                     'Looks like the draft.', 'One option attached.', 'Sign-off pending.',
                     'Approve it.', 'Agree to proceed.', 'Thoughts attached.',
                     'Price unchanged.', 'Pricing is documented.', 'Budget documented.',
                     'Spend is zero.', '500 per day.', '19.99 monthly.', '$39.',
                     'The label is "Any questions?".', 'See https://example.test/?view=1']:
            with self.subTest(tail=tail):
                self.assertEqual(self.target(card(text='Finished. '+tail)), [])

    def test_a_receipt_cannot_bypass_the_report_only_gate(self):
        self.assertEqual(self.target(card(text='Receipt attached. Reply with a favorite.')), [])
        self.assertEqual(self.target(card(text='Payment receipt. Thank you.')), [])
        self.assertEqual(self.target(card(text='Welcome to the newsletter.')), [])

    def test_completion_evidence_is_required_before_any_move(self):
        for text in ['The artifact is attached.', 'Receipt attached.', 'Not completed yet.']:
            self.assertEqual(self.target(card(text=text)), [])

    def test_prices_and_quoted_ui_questions_stay_for_review(self):
        for text in ['Uploaded the final screens. The monthly paywall says $9.99.',
                     'Finished the search screen. Its label is "Is my character here?".']:
            self.assertEqual(self.target(card(text=text)), [])

    def test_bare_dollar_amount_in_card_context_is_protected(self):
        c = card(text='Finished.'); c['body'] = 'Reference amount: $39.'
        self.assertEqual(self.target(c), [])


class Runner(unittest.TestCase):
    def run_steward(self, root, cards, dry=False, move_result=None):
        def apply_move(cid, value, note):
            for row in cards:
                if row['id'] == cid:
                    row['section'] = value
            return move_result or {'ok': True}
        with patch.object(steward, 'fetch_cards', return_value=cards), \
             patch.object(steward, 'move_card', side_effect=apply_move) as move:
            result = steward.run_once(Path(root), dry_run=dry, now=NOW)
        return result, move

    def test_dry_run_has_no_mutations_or_journal_writes(self):
        with tempfile.TemporaryDirectory() as root:
            r, move = self.run_steward(root, [card()], dry=True)
            self.assertEqual(r['planned_moves'], 1)
            self.assertEqual(r['moved'], 0)
            self.assertFalse(move.called)
            self.assertFalse((Path(root)/'steward-log.jsonl').exists())
            self.assertFalse((Path(root)/'steward-overflow.json').exists())

    def test_live_move_is_logged_and_overflow_is_stale_first(self):
        cards = [card()]+[card(str(i), text='A judgment call remains.') for i in range(14)]
        cards[1]['updated_at'] = '2026-10-21T00:00:00Z'
        with tempfile.TemporaryDirectory() as root:
            r, move = self.run_steward(root, cards)
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
             patch.object(steward, 'move_card') as move:
            r = steward.run_once(Path(root), now=NOW)
            self.assertFalse(move.called)
            self.assertEqual(r['deferred'], 1)

    def test_failure_is_recorded_without_printing_raw_error(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(steward, 'fetch_cards', return_value=[card()]), \
             patch.object(steward, 'move_card', side_effect=RuntimeError('secret-token=do-not-print')):
            r = steward.run_once(Path(root), now=NOW)
            self.assertEqual(r['failed'], 1)
            text = (Path(root)/'steward-log.jsonl').read_text()
            self.assertNotIn('do-not-print', text)
            self.assertEqual([json.loads(line)['outcome'] for line in text.splitlines()], ['attempt'])
            self.assertTrue(r['stale'])


    def test_adapters_preserve_raw_envelopes_and_use_page_authorization(self):
        import types
        rows = [card()]; requests = []
        def call(action=None, **kw):
            requests.append((action, kw))
            if action is None:
                return {'ok': True, 'cards': rows}
            rows[0]['section'] = kw['value']
            return {'ok': True}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(sys.modules, board_client=types.SimpleNamespace(call=call)):
            result = steward.run_once(Path(tmp), now=NOW)
        self.assertEqual(result['moved'], 1)
        self.assertEqual([r for r in requests if r[0] == 'move'],
                         [('move', dict(page=True, card_id='worker', value='up_next', note='Ted review'))])
        self.assertTrue(all(kw == {'page': True} for action, kw in requests if action is None))

    def test_empty_overflow_replaces_a_previous_overflow(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'steward-overflow.json'
            path.write_text('{"excess_count": 9}')
            self.run_steward(root, [])
            self.assertEqual(json.loads(path.read_text())['extras'], [])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_incomplete_snapshots_are_refused(self):
        import types
        board = types.SimpleNamespace(call=lambda **kw: {'ok': True, 'cards': [card()]*500})
        with patch.dict(sys.modules, board_client=board):
            with self.assertRaises(RuntimeError):
                steward.fetch_cards()

    def test_unconfirmed_api_response_is_not_counted_as_applied(self):
        with tempfile.TemporaryDirectory() as root:
            result, move = self.run_steward(root, [card()], move_result={'ok': False})
            self.assertEqual(result['failed'], 1)
            self.assertEqual(result['moved'], 0)

    def test_mini_guard_rejects_macbook(self):
        import types
        with patch.object(steward.subprocess, 'run', return_value=types.SimpleNamespace(stdout='MacBook Pro')):
            with self.assertRaises(RuntimeError):
                steward.require_mini()
        with patch.object(steward.subprocess, 'run', return_value=types.SimpleNamespace(stdout='Sebastian Mac Mini')):
            steward.require_mini()

    def test_overflow_sorts_actual_activity_before_rounding_display_age(self):
        rows = [card(str(i), text='Needs judgment.') for i in range(13)]
        for row in rows:
            row['updated_at'] = '2026-10-01T00:00:00Z'
            row['messages'][0]['at'] = '2026-10-01T00:00:00Z'
        rows[0]['updated_at'] = '2026-10-01T00:01:00Z'
        with tempfile.TemporaryDirectory() as root:
            self.run_steward(root, rows)
            result = json.loads((Path(root)/'steward-overflow.json').read_text())
            self.assertEqual(result['ranked'][-1]['id'], '0')

    def test_ambiguous_cards_are_listed_for_ted_even_below_the_cap(self):
        rows = [card('choice', text='Uploaded 3 logo options for you to look at.')]
        with tempfile.TemporaryDirectory() as root:
            self.run_steward(root, rows)
            result = json.loads((Path(root)/'steward-overflow.json').read_text())
            self.assertEqual(result['excess_count'], 0)
            self.assertEqual([r['id'] for r in result['ranked']], ['choice'])
            self.assertEqual([r['id'] for r in result['ambiguous']], ['choice'])

    def test_review_prints_compact_ambiguous_rows_and_redacts_sensitive_text(self):
        c = card(text='See https://example.test/#k=private and token=hidden.')
        out = io.StringIO()
        with patch.object(steward, 'fetch_cards', return_value=[c]), \
             contextlib.redirect_stdout(out):
            steward_review.main([], now=NOW)
        text = out.getvalue()
        self.assertIn('worker', text); self.assertIn('Test', text); self.assertIn('Build screens', text)
        self.assertIn('keep', text); self.assertNotIn('private', text); self.assertNotIn('hidden', text)


class ScopeAndAvailability(unittest.TestCase):
    def test_disabled_run_does_not_read_or_mutate_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'steward.disabled').touch()
            cached = root/'steward-overflow.json'; cached.write_text('{"ranked": ["keep"]}')
            with patch.object(steward, 'fetch_cards', side_effect=AssertionError('network forbidden')):
                result = steward.run_once(root, now=NOW)
            self.assertTrue(result['disabled'])
            self.assertEqual(result['failed'], 0)
            self.assertEqual(cached.read_text(), '{"ranked": ["keep"]}')
            self.assertFalse((root/'steward-log.jsonl').exists())

    def test_global_kill_switch_cannot_be_bypassed_with_another_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'steward.disabled').touch(); alternate = root/'alternate'
            with patch.object(steward, 'ROOT', root), \
                 patch.object(steward, 'fetch_cards', side_effect=AssertionError('network forbidden')):
                result = steward.run_once(alternate, now=NOW)
            self.assertTrue(result['disabled'])
            self.assertFalse(alternate.exists())

    def test_disabled_cli_exits_zero_without_creating_a_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'steward.disabled').touch(); alternate = root/'alternate'
            with patch.object(steward, 'ROOT', root), \
                 patch.object(steward, 'require_mini', side_effect=AssertionError('disabled means no work')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(steward.main(['--root', str(alternate)]), 0)
            self.assertFalse(alternate.exists())

    def test_api_down_marks_cached_data_stale_and_preserves_first_failure_time(self):
        for dry in [False, True]:
            with self.subTest(dry=dry), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root/'steward-overflow.json'
                path.write_text(json.dumps({'at': OLD, 'ranked': [{'id': 'retained'}], 'needs_you': 1}))
                with patch.object(steward, 'fetch_cards', side_effect=RuntimeError('token=private')):
                    result = steward.run_once(root, dry_run=dry, now=NOW)
                    first = json.loads(path.read_text())
                    steward.run_once(root, dry_run=dry, now=NOW+3600)
                last = json.loads(path.read_text())
                self.assertTrue(result['stale'])
                self.assertEqual(first['stale_since'], '2026-10-23T02:00:00+00:00')
                self.assertEqual(last['stale_since'], first['stale_since'])
                self.assertEqual(last['at'], OLD)
                self.assertEqual(last['ranked'], [{'id': 'retained'}])
                self.assertNotIn('private', path.read_text())

    def test_api_down_without_cache_writes_a_stale_marker(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(steward, 'fetch_cards', side_effect=RuntimeError('offline')):
            root = Path(tmp); steward.run_once(root, now=NOW)
            result = json.loads((root/'steward-overflow.json').read_text())
            self.assertEqual(result['stale_since'], '2026-10-23T02:00:00+00:00')
            self.assertIsNone(result['needs_you'])

    def test_successful_refresh_clears_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'steward-overflow.json'
            path.write_text(json.dumps({'stale_since': OLD, 'ranked': [{'id': 'old'}]}))
            with patch.object(steward, 'fetch_cards', return_value=[]):
                result = steward.run_once(root, now=NOW)
            refreshed = json.loads(path.read_text())
            self.assertFalse(result['stale'])
            self.assertIsNone(refreshed['stale_since'])
            self.assertEqual(refreshed['ranked'], [])

    def test_run_has_no_mockup_transport_dependency(self):
        import types
        forbidden = types.SimpleNamespace(call=lambda *a, **kw: self.fail('mockup transport forbidden'))
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(sys.modules, mockup_client=forbidden), \
             patch.object(steward, 'fetch_cards', return_value=[]):
            result = steward.run_once(Path(tmp), now=NOW)
            self.assertEqual(result['failed'], 0)

    def test_protected_projects_never_move_even_with_clear_reports(self):
        for project in ['personal', 'PERSONAL', ' money ']:
            with self.subTest(project=project):
                row = card(); row['project'] = project
                self.assertIsNone(steward.classify_card(row, NOW)[0])

    def test_protected_sections_never_move_even_with_clear_reports(self):
        for section in ['ted_doing', 'up_next', 'done', 'killed']:
            row = card(); row['section'] = section
            self.assertIsNone(steward.classify_card(row, NOW)[0])

    def test_api_down_before_recheck_prevents_the_move_and_marks_stale(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(steward, 'fetch_cards', side_effect=[[card()], RuntimeError('offline')]), \
             patch.object(steward, 'move_card') as move:
            root = Path(tmp); result = steward.run_once(root, now=NOW)
            self.assertFalse(move.called)
            self.assertTrue(result['stale'])
            self.assertEqual(json.loads((root/'steward-overflow.json').read_text())['stale_since'], '2026-10-23T02:00:00+00:00')

    def test_api_down_after_a_confirmed_move_preserves_the_move_count(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(steward, 'fetch_cards', side_effect=[[card()], [card()], RuntimeError('offline')]), \
             patch.object(steward, 'move_card', return_value={'ok': True}):
            result = steward.run_once(Path(tmp), now=NOW)
            self.assertEqual(result['moved'], 1)
            self.assertTrue(result['stale'])
            self.assertIsNone(result['needs_you_after'])

    def test_kill_switch_appearing_during_fetch_prevents_every_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def fetch():
                (root/'steward.disabled').touch()
                return [card()]
            with patch.object(steward, 'fetch_cards', side_effect=fetch), \
                 patch.object(steward, 'move_card') as move:
                result = steward.run_once(root, now=NOW)
            self.assertTrue(result['disabled']); self.assertFalse(move.called)
            self.assertFalse((root/'steward-overflow.json').exists())
            self.assertFalse((root/'steward-log.jsonl').exists())

    def test_project_becoming_protected_before_move_is_deferred(self):
        changed = card(); changed['project'] = 'personal'
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(steward, 'fetch_cards', side_effect=[[card()], [changed], [changed]]), \
             patch.object(steward, 'move_card') as move:
            result = steward.run_once(Path(tmp), now=NOW)
            self.assertFalse(move.called)
            self.assertEqual(result['deferred'], 1)


class StructuralBoundary(unittest.TestCase):
    def test_writers_without_a_run_snapshot_cannot_mutate(self):
        import types
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sent = []
            action = dict(card_id='c1', project='Test', **{'from': 'needs_you'},
                          to='up_next', reason='Ted review')
            operations = [lambda: steward.journal(root, action, 'attempt', NOW),
                          lambda: steward.write_overflow(root, [], NOW),
                          lambda: steward.mark_stale(root, NOW),
                          lambda: steward.move_card('c1', 'up_next', 'Ted review')]
            board = types.SimpleNamespace(call=lambda *a, **kw: sent.append((a, kw)))
            with patch.dict(sys.modules, board_client=board):
                for operation in operations:
                    with self.assertRaises(RuntimeError):
                        operation()
            self.assertEqual(sent, [])
            self.assertEqual(list(root.iterdir()), [])

    def test_expired_snapshot_cannot_authorize_a_move(self):
        import types
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sent = []; clock = [0.0]
            real_journal = steward.journal
            def journal(*args):
                real_journal(*args)
                if args[2] == 'attempt':
                    clock[0] += 3600
            board = types.SimpleNamespace(call=lambda *a, **kw: sent.append((a, kw)))
            with patch.object(steward, 'fetch_cards', return_value=[card()]), \
                 patch.object(steward.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(steward, 'journal', side_effect=journal), \
                 patch.dict(sys.modules, board_client=board):
                result = steward.run_once(root, now=NOW)
            self.assertEqual(sent, [])
            self.assertEqual(result['failed'], 1)
            self.assertTrue(result['stale'])
            self.assertTrue(json.loads((root/'steward-overflow.json').read_text())['stale'])

    def test_stale_recovery_permission_cannot_authorize_other_writes(self):
        import types
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sent = []; denied = []
            real_mark_stale = steward.mark_stale
            action = dict(card_id='c1', project='Test', **{'from': 'needs_you'},
                          to='up_next', reason='Ted review')
            def recover(*args):
                operations = [lambda: steward.journal(root, action, 'attempt', NOW),
                              lambda: steward.write_overflow(root, [], NOW),
                              lambda: steward.move_card('c1', 'up_next', 'Ted review')]
                for operation in operations:
                    try:
                        operation()
                    except RuntimeError:
                        denied.append(True)
                real_mark_stale(*args)
            with patch.object(steward, 'fetch_cards', side_effect=RuntimeError('offline')), \
                 patch.object(steward, 'mark_stale', side_effect=recover), \
                 patch.dict(sys.modules, board_client=types.SimpleNamespace(call=lambda *a, **kw: sent.append(kw))):
                result = steward.run_once(root, now=NOW)
            self.assertEqual(denied, [True, True, True])
            self.assertEqual(sent, [])
            self.assertFalse((root/'steward-log.jsonl').exists())
            self.assertTrue(result['stale'])
            self.assertTrue(json.loads((root/'steward-overflow.json').read_text())['stale'])

    def test_switch_before_atomic_promotion_preserves_the_old_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'steward-overflow.json'
            original = '{"needs_you": 8, "ranked": ["retained"]}'
            path.write_text(original)
            real_fsync = steward.os.fsync
            def fsync(fd):
                real_fsync(fd)
                (root/'steward.disabled').touch()
            with patch.object(steward, 'fetch_cards', return_value=[]), \
                 patch.object(steward.os, 'fsync', side_effect=fsync):
                result = steward.run_once(root, now=NOW)
            self.assertTrue(result['disabled'])
            self.assertEqual(path.read_text(), original)

    def test_recovery_write_failure_returns_failure_without_recursion_or_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(steward, 'fetch_cards', side_effect=RuntimeError('offline')), \
             patch.object(steward.os, 'open', side_effect=OSError('token=hidden')):
            result = steward.run_once(Path(tmp), now=NOW)
        self.assertEqual(result['failed'], 1)
        self.assertTrue(result['stale_write_failed'])
        self.assertNotIn('hidden', json.dumps(result))

    def test_incomplete_raw_envelopes_preserve_cached_count_and_mark_stale(self):
        import types
        for response in [None, [], {'ok': True, 'cards': [None]}, {}, {'ok': False}, {'ok': True}, {'ok': True, 'cards': None},
                         {'ok': True, 'cards': {}}, {'cards': []}, {'ok': 1, 'cards': []}]:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root/'steward-overflow.json'
                path.write_text(json.dumps({'at': OLD, 'needs_you': 7, 'ranked': [{'id': 'keep'}]}))
                board = types.SimpleNamespace(cards=lambda: [], call=lambda *a, **kw: response)
                with patch.dict(sys.modules, board_client=board):
                    result = steward.run_once(root, now=NOW)
                cached = json.loads(path.read_text())
                self.assertTrue(result['stale'])
                self.assertEqual(result['failed'], 1)
                self.assertEqual(cached['needs_you'], 7)
                self.assertEqual(cached['ranked'], [{'id': 'keep'}])
                self.assertTrue(cached['stale'])

    def test_valid_empty_raw_envelope_can_clear_the_overflow(self):
        import types
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = types.SimpleNamespace(call=lambda *a, **kw: {'ok': True, 'cards': []})
            with patch.dict(sys.modules, board_client=board):
                result = steward.run_once(root, now=NOW)
            self.assertEqual(result['failed'], 0)
            cached = json.loads((root/'steward-overflow.json').read_text())
            self.assertEqual(cached['needs_you'], 0)
            self.assertFalse(cached['stale'])

    def test_null_messages_remain_ambiguous_without_crashing_activity(self):
        row = card(); row['messages'] = None
        with tempfile.TemporaryDirectory() as tmp, patch.object(steward, 'fetch_cards', return_value=[row]):
            root = Path(tmp); result = steward.run_once(root, now=NOW)
            self.assertEqual(result['failed'], 0)
            cached = json.loads((root/'steward-overflow.json').read_text())
            self.assertEqual(cached['needs_you'], 1)
            self.assertEqual(cached['ambiguous'][0]['id'], 'worker')

    def test_any_post_fetch_failure_marks_stale_and_stops_the_run(self):
        # Removing the outer exception boundary must break each stage.
        for stage in ['plan', 'journal', 'write_overflow']:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp, \
                 patch.object(steward, 'fetch_cards', return_value=[card()]), \
                 patch.object(steward, stage, side_effect=RuntimeError('token=hidden')), \
                 patch.object(steward, 'move_card', return_value={'ok': True}) as move:
                root = Path(tmp); result = steward.run_once(root, now=NOW)
                self.assertEqual(result['failed'], 1)
                self.assertTrue(result['stale'])
                cached = json.loads((root/'steward-overflow.json').read_text())
                self.assertTrue(cached['stale'])
                self.assertNotIn('hidden', json.dumps(result)+json.dumps(cached))
                if stage != 'write_overflow':
                    self.assertFalse(move.called)

    def test_failed_fetch_after_switch_activation_cannot_mark_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root/'steward-overflow.json'
            original = '{"at": "retained", "needs_you": 9}'
            path.write_text(original)
            def fetch():
                (root/'steward.disabled').touch()
                raise RuntimeError('offline')
            with patch.object(steward, 'fetch_cards', side_effect=fetch):
                result = steward.run_once(root, now=NOW)
            self.assertTrue(result['disabled'])
            self.assertEqual(path.read_text(), original)
            self.assertFalse((root/'steward-log.jsonl').exists())
            self.assertFalse((root/'steward-overflow.json.tmp').exists())

    def test_switch_after_attempt_journal_blocks_real_move_adapter(self):
        import types
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sent = []
            real_journal = steward.journal
            def journal(*args):
                real_journal(*args)
                if args[2] == 'attempt':
                    (root/'steward.disabled').touch()
            def call(*args, **kw):
                sent.append((args, kw))
                return {'ok': True}
            with patch.object(steward, 'fetch_cards', return_value=[card()]), \
                 patch.object(steward, 'journal', side_effect=journal), \
                 patch.dict(sys.modules, board_client=types.SimpleNamespace(call=call)):
                result = steward.run_once(root, now=NOW)
            self.assertEqual(sent, [])
            self.assertTrue(result['disabled'])
            self.assertEqual(result['moved'], 0)
            self.assertFalse((root/'steward-overflow.json').exists())
            self.assertEqual([json.loads(line)['outcome'] for line in
                              (root/'steward-log.jsonl').read_text().splitlines()], ['attempt'])

    def test_failed_move_stops_before_later_actions_and_keeps_cache_stale(self):
        attempted = []
        def fail(cid, *args):
            attempted.append(cid)
            raise RuntimeError('unconfirmed')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(steward, 'fetch_cards', return_value=[card('first'), card('second')]), \
             patch.object(steward, 'move_card', side_effect=fail):
            root = Path(tmp); result = steward.run_once(root, now=NOW)
            self.assertEqual(attempted, ['first'])
            self.assertEqual(result['failed'], 1)
            self.assertTrue(result['stale'])
            self.assertTrue(json.loads((root/'steward-overflow.json').read_text())['stale'])


if __name__ == '__main__':
    unittest.main()
