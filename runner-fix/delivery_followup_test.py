"""Deleted failure receipts and compatibility of every runner-owned template."""
import tempfile
import types
import sys
import unittest
from unittest.mock import Mock, patch
import failure_routing_test as fixture
import inbox_policy as policy


class DeliveryFollowup(unittest.TestCase):
    def test_deleted_failure_note_is_dropped_but_transient_errors_are_retained(self):
        failure=dict(card_id='deleted',text=policy.FAILURE_LINE,token='failure-1',
                     runner_failure=dict(failure_kind='crash',recovery='held'))
        ordinary=dict(card_id='other',text='ordinary reply',token='reply-1')
        for error,want in ((fixture.client.BoardGone('gone'),[ordinary]),
                           (RuntimeError('offline'),[failure,ordinary])):
            with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as tmp:
                store=fixture.sessions.Store(tmp)
                with store.locked() as data:data['outbox']=[failure,ordinary]
                with patch.object(fixture.sessions,'call',side_effect=error),patch.dict(sys.modules,board_reply=types.SimpleNamespace(main=Mock(return_value=1))):
                    store.flush();store.flush()
                self.assertEqual(store.read()['outbox'],want)

    def test_all_twelve_failure_templates_pass_both_steward_report_gates(self):
        self.assertEqual(len(policy.FAILURE_MESSAGES),12)
        for text in policy.FAILURE_MESSAGES:
            with self.subTest(text=text):
                self.assertIsNone(fixture.steward.report_only_reason(text))
                self.assertTrue(fixture.steward.positive_completion(text))


if __name__=='__main__':unittest.main()
