"""Offline regressions for Ted's second review of PR 44."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import failure_routing_test as fixture
import inbox_policy as policy

card=fixture.card
live=fixture.live
client=fixture.client
sessions=fixture.sessions
steward=fixture.steward
NOW=policy.stamp('2026-10-24T18:00:00Z')
RECENT='2026-10-24T17:59:00Z'

MIXED_ASKS=(
    'Worker timed out; approve sending the email?',
    'Worker failed, approve the 400 dollar spend to retry?',
    'Worker stopped, pick which headline you want for the lander.',
)
SUPERSEDED_ASK='Superseded by v2. Pick which headline you want for the lander.'


class RetainDecisions(unittest.TestCase):
    def test_failure_wording_in_the_same_sentence_cannot_hide_an_ask(self):
        for text in MIXED_ASKS:
            with self.subTest(text=text):
                self.assertIsNone(policy.failure_kind(text))
                self.assertIsNone(policy.disposition(card(body=text))[0])
                c=card(section='needs_you',body=text)
                self.assertEqual(steward.plan([c],[],[],NOW)['actions'],[])

    def test_supersession_cannot_override_any_ask_sentence(self):
        for text in (SUPERSEDED_ASK,'Choose the next route. Superseded by v2.'):
            with self.subTest(text=text):
                self.assertIsNone(policy.disposition(card(body=text))[0])
                self.assertEqual(steward.plan([card(section='needs_you',body=text)],[],[],NOW)['actions'],[])

    def test_live_status_preserves_same_sentence_and_superseded_asks(self):
        for text in MIXED_ASKS+(SUPERSEDED_ASK,):
            with self.subTest(text=text),patch.object(client,'cards',return_value=[card()]),patch.object(live,'call',return_value=dict(ok=True,card=card())) as send:
                live.update('x','waiting_on_you',text,section='needs_you')
                self.assertEqual(send.call_args.kwargs['section'],'needs_you')
                self.assertEqual(send.call_args.kwargs['state'],'waiting_on_you')

    def test_decision_kind_retains_wordless_financial_and_email_notices(self):
        for kind in ('spend_money','send_email','other'):
            with self.subTest(kind=kind):
                c=card(section='needs_you',body='Export completed.',decision_kind=kind)
                self.assertIsNone(steward.classify_card(c,NOW)[0])
                self.assertEqual(steward.plan([c],[],[],NOW)['actions'],[])

    def test_recent_human_reply_or_answer_retains_a_completed_card(self):
        fields=(dict(messages=[dict(who='sebastian',at=RECENT,text='Looks fine.')]),
                dict(answer=dict(created_at=RECENT,choice='note')))
        for extra in fields:
            with self.subTest(extra=extra):
                c=card(section='needs_you',body='Export completed.',**extra)
                self.assertEqual(steward.plan([c],[],[],NOW)['actions'],[])

    def test_existing_protection_guards_are_required_before_any_move(self):
        fields=(dict(live_state='running'),dict(pending_approval=True),dict(amount_cents=40000),
                dict(options=['yes','no']),dict(steps=['confirm']),dict(veto=dict(status='pending')))
        for extra in fields:
            with self.subTest(extra=extra):
                c=card(section='needs_you',body='Export completed.',**extra)
                self.assertEqual(steward.plan([c],[],[],NOW)['actions'],[])

    def test_ask_in_other_visible_card_text_or_thread_retains_the_card(self):
        fields=(dict(title='Which route do you prefer?'),
                dict(body='Approve sending the email?',live_status='Worker failed: OSError.'),
                dict(messages=[dict(who='ted',at='2026-10-01T00:00:00Z',text='Which headline do you prefer?'),
                               dict(who='ted',at='2026-10-02T00:00:00Z',text='Export completed.')]))
        for extra in fields:
            with self.subTest(extra=extra):
                c=card(section='needs_you',**dict(dict(body='Export completed.'),**extra))
                self.assertEqual(steward.plan([c],[],[],NOW)['actions'],[])

    def test_unmarked_notices_are_retained_under_the_marker_allowlist(self):
        for text in ('Worker stopped without a final result.','Superseded by v2.','Export completed.'):
            with self.subTest(text=text):
                actions=steward.plan([card(section='needs_you',body=text)],[],[],NOW)['actions']
                self.assertEqual(actions,[])


class DeletedCardRecovery(unittest.TestCase):
    session=fixture.Runner.session
    setUp=fixture.Runner.setUp

    def test_deleted_card_cancels_recovery_and_clears_failure_publication(self):
        for missing_at_read in (True,False):
            with self.subTest(missing_at_read=missing_at_read),tempfile.TemporaryDirectory() as tmp:
                store,s=self.session(tmp)
                sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,failure_kind='timeout',text='Worker timed out.'))
                with patch.object(client,'cards',return_value=[] if missing_at_read else [card()]),patch.object(sessions,'publish_live',side_effect=live.publish_live),patch.object(live,'call',side_effect=client.BoardGone('Card no longer exists')) as send,patch.object(sessions,'alive',return_value=False),patch.object(sessions.subprocess,'Popen',return_value=Mock(pid=456)) as spawn:
                    store.tick();store.tick()
                    self.assertEqual(send.call_count,0 if missing_at_read else 1)
                    spawn.assert_not_called()
                saved=store.read()['sessions']['x']
                self.assertNotIn('failure_publish_pending',saved)
                self.assertEqual(saved['queue'],[])
                self.assertEqual(saved['status'],'failed')
                self.assertIn('deleted',saved['last_line'])


if __name__=='__main__':unittest.main()
