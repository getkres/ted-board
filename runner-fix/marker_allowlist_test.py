"""Runner provenance, exact templates, and protected inbox departures, offline only."""
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import failure_routing_test as fixture
import inbox_policy as policy

card=fixture.card
client=fixture.client
live=fixture.live
sessions=fixture.sessions
worker=fixture.worker
steward=fixture.steward
reaper=fixture.reaper
NOW=policy.stamp('2026-10-24T22:00:00Z')
NOTE='[ted-runner-failure:v1:timeout] worker run finished with a timeout; ted owns recovery from the job files. one retry is queued from the job files.'


def marked(**extra):
    return card(**dict(dict(section='needs_you',live_state='blocked',messages=[dict(who='ted',at='2026-10-24T21:00:00Z',text=NOTE)]),**extra))


class Allowlist(unittest.TestCase):
    def test_all_four_runner_failure_templates_are_eligible(self):
        notes=(NOTE,
               '[ted-runner-failure:v1:no_result] worker run finished without a final result; ted owns recovery from the job files. one retry is queued from the job files.',
               '[ted-runner-failure:v1:startup_failure] worker run finished with a startup failure; ted owns recovery from the job files. no automatic retry remains.',
               '[ted-runner-failure:v1:crash] worker run finished with a crash; ted owns recovery from the job files. no automatic retry remains.')
        for note in notes:
            with self.subTest(note=note):
                c=marked(messages=[dict(who='ted',at='2026-10-24T21:00:00Z',text=note)])
                self.assertEqual(steward.plan([c],[],[],NOW)['actions'][0]['to'],'up_next')

    def test_only_an_exact_latest_runner_template_can_authorize_a_move(self):
        self.assertEqual(policy.disposition(marked())[0],'up_next')
        self.assertEqual(steward.plan([marked()],[],[],NOW)['actions'][0]['to'],'up_next')
        for text in ('Worker timed out.','Superseded by v2.','Export completed.',
                     'Confirm the $500 ad spend.','Need your OK to go live.',
                     'Go ahead and launch when ready.',NOTE+' Confirm the $20 plan.',NOTE.replace('timeout]','unknown]')):
            with self.subTest(text=text):
                c=marked(messages=[dict(who='ted',at='2026-10-24T21:00:00Z',text=text)])
                self.assertIsNone(policy.disposition(c)[0])
                self.assertEqual(steward.plan([c],[],[],NOW)['actions'],[])

    def test_kind_pending_human_newer_or_ambiguous_message_retains(self):
        fields=[dict(decision_kind=k) for k in ('send_email','spend_money','other','')]
        fields += [dict(pending_approval=True),dict(live_state='waiting_on_you'),
                   dict(messages=[dict(who='seb',at='2026-10-20T00:00:00Z',text=NOTE)]),
                   dict(messages=[dict(who='ted',at='2026-10-24T21:00:00Z',text=NOTE),dict(who='seb',at='2026-10-24T21:01:00Z',text='Proceed.')]),
                   dict(messages=[dict(who='ted',at='2026-10-24T21:00:00Z',text=NOTE),dict(who='seb',at='2026-10-24T21:00:00Z',text='Proceed.')]),
                   dict(messages=[dict(who='ted',text=NOTE)])]
        for extra in fields:
            with self.subTest(extra=extra):
                self.assertIsNone(policy.disposition(marked(**extra))[0])
        incomplete=marked();incomplete.pop('decision_kind')
        self.assertIsNone(policy.disposition(incomplete)[0])

    def test_runner_failure_from_doing_still_goes_to_ted(self):
        with patch.object(client,'cards',return_value=[card(decision_kind='other')]),patch.object(live,'call',return_value=dict(ok=True,card=card(section='up_next'))) as send:
            result=live.update('x','blocked',NOTE,section='up_next')
            self.assertEqual(result['section'],'up_next')
            self.assertEqual(send.call_args.kwargs['expected_section'],'ted_doing')

    def test_every_nonmarker_status_is_retained_through_live_update(self):
        for line in ('Confirm the $500 ad spend.','Superseded by v2. Confirm the $20 plan.',
                     'Worker failed.','Export completed.'):
            with self.subTest(line=line),patch.object(client,'cards',return_value=[marked(messages=[])]),patch.object(live,'call') as send:
                result=live.update('x','done',line,section='done',expected_section='needs_you',expected_updated_at='2026-10-20T00:00:00Z')
                self.assertEqual(result['section'],'needs_you')
                send.assert_not_called()

    def test_marked_failure_does_not_pull_a_decision_kind_card_out(self):
        with patch.object(client,'cards',return_value=[marked(decision_kind='send_email')]),patch.object(live,'call') as send:
            result=live.update('x','blocked',NOTE,section='up_next')
            self.assertEqual(result['section'],'needs_you')
            send.assert_not_called()

    def test_old_sebastian_authored_fyi_stays_in_inbox(self):
        c=card(section='needs_you',messages=[dict(who='sebastian',at='2026-10-20T00:00:00Z',text='Export completed.')])
        self.assertEqual(steward.plan([c],[],[],NOW)['actions'],[])


class CrashAndReaper(unittest.TestCase):
    session=fixture.Runner.session
    setUp=fixture.Runner.setUp

    def test_returncode_one_with_empty_output_stays_crash_and_never_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            with store.locked() as data:data['sessions']['x']['pid']=os.getpid()
            s=store.read()['sessions']['x'];prefix=Path(s['cwd'])/'turn'
            sessions.atomic(str(prefix)+'.input.json',dict(session=s,prompt='fixture'))
            with patch.object(worker,'identity',return_value='fixture'),patch.object(worker,'engine_command',return_value=['fixture']),patch.object(worker.subprocess,'run',return_value=types.SimpleNamespace(returncode=1)):
                worker.run(prefix)
            self.assertEqual(json.loads(Path(str(prefix)+'.result.json').read_text())['failure_kind'],'crash')
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'identity',return_value='fixture'),patch.object(sessions,'publish_live',return_value=True),patch.object(sessions.subprocess,'Popen',return_value=Mock(pid=456)) as spawn:
                store.tick();spawn.assert_not_called()
            saved=store.read()['sessions']['x']
            self.assertEqual(saved['failure_kind'],'crash')
            self.assertEqual(saved['queue'],[])

    def test_pending_email_approval_precedes_stale_failed_worker_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'card-x';d.mkdir()
            (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d),status='failed',failure_kind='timeout',queue=[])},approvals={'a':dict(card_id='x',kind='email',status='pending')})))
            with patch.object(reaper,'update') as send:
                self.assertEqual(reaper.reap([card(decision_kind='send_email')],root,NOW),(1,0))
            self.assertEqual(send.call_args.kwargs['section'],'needs_you')
            self.assertEqual(send.call_args.args[1],'waiting_on_you')

    def test_wordless_report_confirmations_are_never_demoted(self):
        for text in ('Confirm the $500 ad spend.','Need your OK to go live.',
                     'Go ahead and launch when ready.','Superseded by v2. Confirm the $20 plan.'):
            with self.subTest(text=text),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);d=root/'card-x';d.mkdir()
                (d/'REPORT.md').write_text('LIVE_STATE: waiting_on_you\nLIVE_STATUS: '+text)
                (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d),status='idle',queue=[],started_at=1)})))
                with patch.object(reaper,'update') as send:
                    self.assertEqual(reaper.reap([card(live_state='running')],root,NOW),(1,0))
                self.assertEqual(send.call_args.kwargs['section'],'needs_you')

    def test_dispatcher_note_is_an_exact_runner_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,failure_kind='timeout',text='Worker timed out.'))
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=False):store.tick()
            note=store.read()['outbox'][0]['text']
            self.assertEqual(policy.disposition(marked(messages=[dict(who='ted',at='2026-10-24T21:00:00Z',text=note)]))[0],'up_next')
            self.assertTrue(note.startswith('[ted-runner-failure:v1:timeout] '))


class StewardDelivery(unittest.TestCase):
    def test_retained_card_is_not_reported_as_a_successful_move(self):
        with patch.object(client,'cards',return_value=[marked(decision_kind='send_email')]),patch.object(live,'call') as send,self.assertRaises(RuntimeError):
            steward.move_card('x','up_next',NOTE,'2026-10-20T00:00:00Z')
        send.assert_not_called()

    def test_a_move_exception_is_counted_and_later_moves_continue(self):
        cards=[marked(id='x'),marked(id='y')]
        with tempfile.TemporaryDirectory() as tmp,patch.object(steward,'snapshot',return_value=(cards,[],[])),patch.object(steward,'fetch_cards',return_value=cards),patch.object(steward,'move_card',side_effect=[RuntimeError('fixture failure'),dict(ok=True)]) as move:
            result=steward.run_once(tmp,now=NOW)
            self.assertEqual((result['planned_moves'],result['failed'],result['moved']),(2,1,1))
            self.assertEqual(move.call_count,2)


if __name__=='__main__':unittest.main()
