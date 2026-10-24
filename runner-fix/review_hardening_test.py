"""Regression coverage for the review of 82038e8. All transport is offline."""
import json
from pathlib import Path
import tempfile
import sys
import types
import unittest
from unittest.mock import Mock, patch
import failure_routing_test as fixture
import inbox_policy as policy
from marker_allowlist_test import NOTE, marked, NOW

sessions=fixture.sessions
live=fixture.live
client=fixture.client
steward=fixture.steward
card=fixture.card


class QueuePreservation(unittest.TestCase):
    session=fixture.Runner.session
    setUp=fixture.Runner.setUp

    def test_failure_outbox_uses_server_publication_instead_of_plain_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=False):store.tick()
            item=store.read()['outbox'][0]
            self.assertEqual(item['runner_failure'],dict(failure_kind='no_result',recovery='retry'))
            with patch.object(sessions,'call',return_value=dict(ok=True,card=card())) as send,patch.dict(sys.modules,board_reply=types.SimpleNamespace(main=Mock(side_effect=AssertionError('plain reply forbidden')))):
                self.assertTrue(sessions.deliver(item))
            self.assertEqual(send.call_args.args,('runner_failure',))
            self.assertEqual(send.call_args.kwargs,dict(card_id='x',failure_kind='no_result',recovery='retry',token=item['token']))

    def test_empty_cards_for_an_existing_card_defer_without_eating_queued_reply(self):
        for rows in ([],None,{},[None],[card(id='y'),card(id='y')],AttributeError('invalid envelope'),client.BoardGone('feed missing'),[card(id='y'+str(i)) for i in range(500)]):
            with self.subTest(shape=type(rows).__name__),tempfile.TemporaryDirectory() as tmp:
                store,s=self.session(tmp)
                queued=dict(id='sebastian-reply',kind='work',message='keep this reply')
                with store.locked() as data:data['sessions']['x']['queue']=[queued]
                sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,failure_kind='timeout',text='timeout'))
                probe=patch.object(client,'cards',side_effect=rows) if isinstance(rows,Exception) else patch.object(client,'cards',return_value=rows)
                with probe,patch.object(sessions,'publish_live',side_effect=live.publish_live),patch.object(live,'call',return_value=dict(ok=True,card=card())),patch.object(sessions,'alive',return_value=False),patch.object(sessions.subprocess,'Popen') as spawn:
                    store.tick();store.tick();spawn.assert_not_called()
                saved=store.read()['sessions']['x']
                self.assertEqual(saved['queue'],[queued])
                self.assertTrue(saved['failure_publish_pending'])

    def test_a_returned_card_is_confirmed_even_when_the_list_hits_its_cap(self):
        rows=[card(id='y'+str(i)) for i in range(499)]+[card()]
        with patch.object(client,'cards',return_value=rows),patch.object(live,'call',return_value=dict(ok=True,card=card(section='up_next'))) as send:
            result=live.update('x','blocked',policy.failure_message('crash'),section='up_next')
        self.assertEqual(result['section'],'up_next')
        self.assertEqual(send.call_args.kwargs['expected_section'],'ted_doing')

    def test_nonempty_valid_snapshot_can_confirm_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,failure_kind='timeout',text='timeout'))
            with patch.object(client,'cards',return_value=[card(id='other')]),patch.object(sessions,'publish_live',side_effect=live.publish_live),patch.object(sessions,'alive',return_value=False),patch.object(sessions.subprocess,'Popen') as spawn:
                store.tick();spawn.assert_not_called()
            saved=store.read()['sessions']['x']
            self.assertNotIn('failure_publish_pending',saved)
            self.assertEqual(saved['queue'],[])

    def test_all_approval_execution_failures_never_queue_recovery(self):
        for kind in ('email','spend','db'):
            for failure in ('timeout','no_result'):
                with self.subTest(kind=kind,failure=failure),tempfile.TemporaryDirectory() as tmp:
                    store,s=self.session(tmp)
                    with store.locked() as data:
                        data['sessions']['x']['reviewing']='approval'
                        data['approvals']['approval']=dict(id='approval',card_id='x',kind=kind,status='reviewing')
                    sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,failure_kind=failure,text='failed'))
                    with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=True),patch.object(sessions.subprocess,'Popen') as spawn:
                        store.tick();spawn.assert_not_called()
                    self.assertEqual(store.read()['sessions']['x']['queue'],[])


class Provenance(unittest.TestCase):
    def test_a_worker_copying_template_text_without_server_flag_is_retained(self):
        c=marked();c['messages'][0].pop('runner_failure',None)
        self.assertIsNone(policy.runner_failure(c))
        self.assertIsNone(policy.disposition(c)[0])

    def test_newer_or_invalid_live_status_retains_a_flagged_failure(self):
        for at in ('2026-10-24T21:00:01Z','invalid'):
            with self.subTest(at=at):
                c=marked(live_status_at=at)
                c['messages'][0]['runner_failure']=True
                self.assertIsNone(policy.runner_failure(c))

    def test_equal_or_older_live_status_allows_a_flagged_failure(self):
        for at in (None,'2026-10-24T20:59:59Z','2026-10-24T21:00:00Z'):
            with self.subTest(at=at):
                c=marked(live_status_at=at);c['messages'][0]['runner_failure']=True
                self.assertEqual(policy.disposition(c)[0],'up_next')

    def test_positive_completion_recognizes_completed_and_negated_work(self):
        for text,want in [('Finished the work.',True),('The patch was applied.',True),
                          ('Not finished yet.',False),('The migration has not been applied.',False),
                          ('Will upload tomorrow.',False),('Waiting for results.',False)]:
            with self.subTest(text=text):self.assertEqual(steward.positive_completion(text),want)


if __name__=='__main__':unittest.main()
