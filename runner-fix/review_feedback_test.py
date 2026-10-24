"""Regression cases from Ted's review, using real routing and offline boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import failure_routing_test as fixture
import inbox_policy as policy

card=fixture.card
live=fixture.live
client=fixture.client
sessions=fixture.sessions
worker=fixture.worker
reaper=fixture.reaper
steward=fixture.steward

UNKNOWN_ASKS=(
    'Approve sending the Slack message?',
    'Apply this production migration?',
    'Apply the prod migration?',
    'Choose the best conference topic?',
    'Pick your favorite product name?',
    'Which route should we take?',
)
PREFIXES=(
    'Ted review done.',
    'PR 44 review finished.',
    'Queued for a worker slot.',
    'Waiting for CI.',
    'Worker failed: OSError.',
    'Worker stopped without a final result.',
)


class PolicyReview(unittest.TestCase):
    def test_unknown_asks_remain_in_the_inbox(self):
        for text in UNKNOWN_ASKS:
            with self.subTest(text=text):
                c=card(section='needs_you',body=text)
                self.assertEqual(policy.disposition(c),(None,'ambiguous, retain'))
                self.assertEqual(steward.plan([c],[],[],2000000000)['actions'],[])

    def test_operational_sentence_does_not_hide_a_later_email_ask(self):
        for prefix in PREFIXES:
            with self.subTest(prefix=prefix):
                text=prefix+' Approve sending the email?'
                c=card(section='needs_you',body=text,live_state='running')
                self.assertEqual(policy.decision(c),'send_email')
                self.assertIsNone(policy.failure_kind(text))
                self.assertIsNone(policy.disposition(c)[0])
                self.assertEqual(steward.plan([c],[],[],2000000000)['actions'],[])

    def test_unknown_ask_after_failure_also_remains(self):
        for ask in UNKNOWN_ASKS:
            with self.subTest(ask=ask):
                text='Worker failed: OSError. '+ask
                self.assertIsNone(policy.failure_kind(text))
                self.assertIsNone(policy.disposition(card(section='needs_you',body=text))[0])

    def test_running_worker_without_a_runner_marker_is_retained(self):
        for text in UNKNOWN_ASKS:
            with self.subTest(text=text):
                self.assertIsNone(policy.disposition(card(body=text,live_state='running'))[0])
        self.assertIsNone(policy.disposition(card(live_state='running',live_status='checking the native build'))[0])

    def test_unmarked_start_failure_text_is_not_routing_evidence(self):
        self.assertIsNone(policy.failure_kind('Worker could not start after a timeout.'))


class ClientReview(unittest.TestCase):
    def test_unknown_and_mixed_email_asks_reach_needs_you(self):
        for text in UNKNOWN_ASKS+tuple(p+' Approve sending the email?' for p in PREFIXES):
            with self.subTest(text=text),patch.object(client,'cards',return_value=[card()]),patch.object(live,'call',return_value=dict(ok=True,card=card())) as send:
                live.update('x','waiting_on_you',text,section='needs_you')
                self.assertEqual(send.call_args.kwargs['section'],'needs_you')

    def test_up_next_and_done_failures_are_already_handled(self):
        for section in ('up_next','done'):
            with self.subTest(section=section),patch.object(client,'cards',return_value=[card(section=section)]),patch.object(live,'call') as send:
                result=live.update('x','blocked',policy.failure_message('no_result'),section='up_next')
                self.assertEqual(result['section'],section)
                send.assert_not_called()
        with patch.object(client,'cards',return_value=[]),self.assertRaises(client.BoardGone):
            live.update('x','blocked',policy.failure_message('startup_failure'))


class DispatcherReview(unittest.TestCase):
    session=fixture.Runner.session
    setUp=fixture.Runner.setUp

    def test_existing_queue_suppresses_retry_and_explains_it_in_the_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            with store.locked() as data:
                data['sessions']['x']['queue']=[dict(id='new-request',kind='work',message='newer request')]
            sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,failure_kind='timeout',text='Worker timed out.'))
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=True),patch.object(sessions.os,'getloadavg',return_value=(100000,0,0)):
                store.tick();store.tick()
            saved=store.read()
            self.assertEqual([t['id'] for t in saved['sessions']['x']['queue']],['new-request'])
            notes=[n for n in saved['outbox'] if n['token'].startswith('worker-failure-')]
            self.assertEqual(len(notes),1)
            self.assertIn('retry suppressed',notes[0]['text'].lower())
            self.assertIn('queued',notes[0]['text'].lower())

    def test_already_handled_failure_does_not_hold_the_retry_forever(self):
        for section in ('up_next','done'):
            with self.subTest(section=section),tempfile.TemporaryDirectory() as tmp:
                store,s=self.session(tmp)
                with patch.object(client,'cards',return_value=[card(section=section)]),patch.object(sessions,'publish_live',side_effect=live.publish_live),patch.object(live,'call',return_value=dict(ok=True,card=card())):
                    with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'identity',return_value='fixture'),patch.object(sessions.subprocess,'Popen',return_value=Mock(pid=456)):
                        store.tick()
                saved=store.read()['sessions']['x']
                self.assertEqual(saved['status'],'running')
                self.assertNotIn('failure_publish_pending',saved)
                self.assertEqual(saved['active_turn']['recovery_attempt'],1)

    def test_legacy_start_failure_with_timeout_text_does_not_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,text='Worker could not start after a timeout.'))
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=True),patch.object(sessions,'identity',return_value='fixture'),patch.object(sessions.subprocess,'Popen',return_value=Mock(pid=456)) as spawn:
                store.tick();spawn.assert_not_called()
            self.assertEqual(store.read()['sessions']['x']['queue'],[])

    def test_worker_preserves_twelve_hour_timeout_and_matching_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            with store.locked() as data:data['sessions']['x']['pid']=os.getpid()
            s=store.read()['sessions']['x'];prefix=Path(s['cwd'])/'turn'
            sessions.atomic(str(prefix)+'.input.json',dict(session=s,prompt='fixture'))
            def execute(*args,**kwargs):
                self.assertEqual(kwargs['timeout'],43200)
                raise subprocess.TimeoutExpired(['fixture'],43200)
            with patch.object(worker,'identity',return_value='fixture'),patch.object(worker,'engine_command',return_value=['fixture']),patch.object(worker.subprocess,'run',side_effect=execute):
                worker.run(prefix)
            result=json.loads(Path(str(prefix)+'.result.json').read_text())
            self.assertEqual(result['failure_kind'],'timeout')
            self.assertIn('twelve-hour',result['text'])


class ReaperReview(unittest.TestCase):
    def report_job(self,root,text):
        d=root/'card-x';d.mkdir()
        (d/'REPORT.md').write_text('LIVE_STATE: waiting_on_you\nLIVE_STATUS: '+text+'\n')
        (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d),status='idle',queue=[],started_at=1)})))

    def test_report_asks_are_not_demoted_by_unknown_categories_or_old_failures(self):
        for text in UNKNOWN_ASKS+tuple(p+' Approve sending the email?' for p in PREFIXES):
            with self.subTest(text=text),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.report_job(root,text)
                with patch.object(reaper,'update') as send:
                    changed,failed=reaper.reap([card()],root,now=2000000000)
                self.assertEqual((changed,failed),(1,0))
                self.assertEqual(send.call_args.kwargs['section'],'needs_you')

    def test_mockup_transport_and_shape_failures_count_once_and_continue(self):
        mockups=sys.modules['mockup_client']
        for response in (RuntimeError('private failure'),{},dict(mockups=None),dict(mockups='bad'),dict(mockups=[None])):
            with self.subTest(response=type(response).__name__),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.report_job(root,'pick a mockup from the fresh batch')
                probe=patch.object(mockups,'call',side_effect=response) if isinstance(response,Exception) else patch.object(mockups,'call',return_value=response)
                with probe,patch.object(reaper,'update') as send:
                    changed,failed=reaper.reap([card(),card(id='y')],root,now=2000000000)
                self.assertEqual((changed,failed),(1,1))
                self.assertEqual(send.call_count,1)
                self.assertEqual(send.call_args.args[0],'y')

    def test_client_only_mockup_probe_failures_also_count_in_the_reaper(self):
        mockups=sys.modules['mockup_client']
        for response in (RuntimeError('private failure'),dict(mockups=None),dict(mockups=[None])):
            with self.subTest(response=type(response).__name__),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.report_job(root,'Choose the best conference topic?')
                probe=patch.object(mockups,'call',side_effect=response) if isinstance(response,Exception) else patch.object(mockups,'call',return_value=response)
                with probe,patch.object(client,'cards',return_value=[card()]),patch.object(live,'call') as send:
                    changed,failed=reaper.reap([card()],root,now=2000000000)
                self.assertEqual((changed,failed),(0,1))
                send.assert_not_called()


if __name__=='__main__':unittest.main()
