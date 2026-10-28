"""Offline report fallback regressions, using the real snapshot and planner."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

if os.environ.get('TED_RUNTIME_SOURCE'):
    sys.path.insert(0, os.environ['TED_RUNTIME_SOURCE'])
else:
    import reconciler_test_support
import reconciler_runtime as runtime


class ReportReviewStatusTests(unittest.TestCase):
    def snapshot(self, report, workflow=None, sql=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'jobs/card-finished'
            directory.mkdir(parents=True)
            (root / 'jobs/sessions.json').write_text(json.dumps({'sessions': {}}))
            (directory / 'REPORT.md').write_text(report)
            if workflow is not None:
                (directory / 'workflow.json').write_text(json.dumps(workflow))
            if sql:
                (directory / 'apply.sql').write_text('-- fixture only, never executed\n')
            card = dict(id='finished', section='done', owner='ted', project='Test',
                        updated_at='2026-10-24T08:23:33.601+00:00')
            return runtime.local_snapshot(root, [card])

    def assert_finished(self, report):
        observed = self.snapshot(report)
        self.assertNotIn('finished', observed['workflows'])
        result = runtime.plan(observed, now=1800000000)
        self.assertFalse(any(row.get('card_id') == 'finished' for row in result['items']))

    def test_completed_review_does_not_reopen_finished_card(self):
        self.assert_finished("Ted's completed review closes v1.")

    def test_selected_reviews_do_not_reopen_finished_card(self):
        self.assert_finished('The selected reviews fit proposed blocks.')

    def test_no_pending_review_does_not_reopen_finished_installation(self):
        self.assert_finished('There is no pending review, PR, migration, or delegated process.')

    def test_unanchored_review_mentions_do_not_create_work(self):
        for report in ('The old step needed Ted review.',
                       'Historical record: needs ted review.',
                       '> needs ted review', '"pending review" was the old state.'):
            with self.subTest(report=report):
                self.assert_finished(report)

    def test_line_start_review_hold_remains_open(self):
        for phrase in ('NEEDS TED REVIEW', 'pending review', 'PR pending', 'Ted review'):
            with self.subTest(phrase=phrase):
                observed = self.snapshot('Prior result.\n  ' + phrase + ': inspect the packet.')
                self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), True)
                result = runtime.plan(observed, now=1800000000)
                self.assertIn('card:finished', [row['id'] for row in result['items']])

    def test_live_status_can_contain_a_current_review_hold(self):
        for status in ('needs ted review', 'blocked; needs ted review',
                       'blocked on Ted review', 'blocked, PR pending'):
            with self.subTest(status=status):
                observed = self.snapshot('LIVE_STATE: blocked\nLIVE_STATUS: ' + status)
                self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), True)

    def test_negated_or_completed_status_does_not_create_review_work(self):
        for value in ('no pending review', 'not pending review', 'without pending review',
                      'completed review closes v1', 'selected reviews are complete',
                      'needs ted review completed', 'pending review closes today',
                      'no remaining work or pending review', 'not live'):
            for prefix in ('', 'LIVE_STATUS: '):
                with self.subTest(value=value, prefix=prefix):
                    self.assert_finished(prefix + value)

    def test_negation_of_other_work_does_not_hide_a_real_status_hold(self):
        observed = self.snapshot('LIVE_STATUS: no SQL or sends; needs ted review')
        self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), True)

    def test_markdown_line_start_holds_remain_visible(self):
        for prefix, suffix in (('# ', ''), ('## ', ''), ('- ', ''),
                               ('1. ', ''), ('**', '**'), ('Status: ', '')):
            with self.subTest(prefix=prefix):
                observed = self.snapshot(prefix + 'Needs Ted review' + suffix)
                self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), True)

    def test_latest_live_status_supersedes_an_older_status_line(self):
        self.assert_finished('LIVE_STATUS: needs ted review\nLIVE_STATUS: done, merged')

    def test_unrelated_completion_and_no_op_words_do_not_negate_hold(self):
        for status in ('needs ted review before the PR closes',
                       'needs ted review of the no-op fix'):
            with self.subTest(status=status):
                observed = self.snapshot('LIVE_STATUS: ' + status)
                self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), True)

    def test_pending_design_selection_remains_a_review_hold(self):
        observed = self.snapshot('LIVE_STATE: blocked\nLIVE_STATUS: finals uploaded; awaiting design selection')
        self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), True)
        result = runtime.plan(observed, now=1800000000)
        self.assertIn('card:finished', [row['id'] for row in result['items']])

    def test_negated_first_clause_cannot_promote_later_ordinary_prose(self):
        self.assert_finished('pending review completed; historical needs ted review')

    def test_code_fences_do_not_turn_status_examples_into_live_holds(self):
        for fence in ('```', '~~~'):
            with self.subTest(fence=fence):
                self.assert_finished(fence + '\nLIVE_STATUS: needs ted review\n' + fence)

    def test_explicit_workflow_review_state_is_primary(self):
        for value in (True, False):
            with self.subTest(value=value):
                observed = self.snapshot('LIVE_STATUS: needs ted review',
                                         workflow={'review_required': value})
                self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), value)
        observed = self.snapshot('LIVE_STATUS: no pending review',
                                 workflow={'review_required': True})
        self.assertIs(observed['workflows'].get('finished', {}).get('review_required'), True)

    def test_pending_sql_and_real_delivery_chain_remain_visible(self):
        for kwargs in ({'sql': True}, {'workflow': {'pr_url':
                       'https://github.com/example/project/pull/1'}}):
            with self.subTest(kwargs=kwargs):
                observed = self.snapshot('LIVE_STATUS: no pending review', **kwargs)
                result = runtime.plan(observed, now=1800000000)
                self.assertIn('card:finished', [row['id'] for row in result['items']])
                if kwargs.get('sql'):
                    self.assertTrue(observed['workflows']['finished']['sql_pending'])


if __name__ == '__main__':
    unittest.main()
