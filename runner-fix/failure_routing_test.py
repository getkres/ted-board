"""Offline regression suite. Network, model execution, and production writes are forbidden."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(os.environ['TED_RUNTIME_SOURCE'])
sys.path.insert(0, str(ROOT))
client = types.SimpleNamespace(
    BoardConflict=RuntimeError, BoardGone=LookupError, RuleResolutionRequired=RuntimeError,
    DECISION_KINDS=('send_email', 'spend_money', 'approve_design', 'other'),
    call=Mock(side_effect=AssertionError('network forbidden')), cards=lambda: [],
    resolve_rule=lambda *a, **k: dict(outcome='ask', reason=None))
sys.modules['board_client'] = client
sys.modules['mockup_client'] = types.SimpleNamespace(call=lambda: dict(mockups=[]))
import live_status as live
import sessions
import session_worker as worker
import board_live as reaper
import inbox_steward as steward

def card(**extra):
    return dict(dict(id='x', project='Fixture', title='Fixture task', body='', section='ted_doing',
                     updated_at='2026-10-20T00:00:00Z', decision_kind=None, messages=[], options=[]), **extra)

class Routing(unittest.TestCase):
    def test_failures_cannot_be_asked_even_with_a_decision_kind(self):
        for text in ('Worker exceeded the three-hour limit. Reply to continue.',
                     'Worker stopped without a final result. Reply to retry.',
                     'Worker could not start. Reply to retry.', 'Worker failed: RuntimeError. Reply to retry.'):
            with self.subTest(text=text), patch.object(client, 'cards', return_value=[card(decision_kind='send_email')]), \
                 patch.object(live, 'call', return_value=dict(ok=True, card=card())) as send:
                live.update('x', 'waiting_on_you', text, section='needs_you', ask_anyway_reason='Needs review')
                self.assertEqual(send.call_args.kwargs.get('section'), 'up_next')
                self.assertEqual(send.call_args.kwargs['state'], 'blocked')

    def test_unclassified_requests_are_retained_for_review(self):
        for text in ('review the pending approval on this card', 'approve this PR',
                     'fix the unsafe approval artifact', 'please sign in and verify the build'):
            with self.subTest(text=text), patch.object(client, 'cards', return_value=[card(decision_kind='other')]), \
                 patch.object(live, 'call', return_value=dict(ok=True, card=card())) as send:
                live.update('x', 'waiting_on_you', text, section='needs_you', ask_anyway_reason='Needs review')
                self.assertEqual(send.call_args.kwargs.get('section'), 'needs_you')
                self.assertNotIn('ask_anyway_reason', send.call_args.kwargs)

    def test_allowed_decisions_reach_rule_resolution(self):
        asks = [('approve spending $50 on the campaign', 'spend_money'),
                ('approve sending the drafted email', 'send_email'),
                ('sign the contract after legal review', None),
                ('choose the subscription price', None),
                ('approve the gated production database write', None),
                ('write your version of the headline', None)]
        for line, kind in asks:
            with self.subTest(line=line), patch.object(client, 'cards', return_value=[card(decision_kind=kind)]), \
                 patch.object(client, 'resolve_rule', return_value=dict(outcome='ask', reason=None)) as resolve, \
                 patch.object(live, 'call', return_value=dict(ok=True, card=card())) as send:
                live.update('x', 'waiting_on_you', line, section='needs_you')
                self.assertEqual(send.call_args.kwargs.get('section'), 'needs_you')
                self.assertEqual(resolve.call_count, 1)

    def test_manual_move_is_not_overwritten(self):
        with patch.object(client, 'cards', return_value=[card(section='done')]), patch.object(live, 'call') as send:
            result=live.update('x', 'waiting_on_you', 'Worker could not start', section='needs_you')
            self.assertEqual(result['section'],'done')
            send.assert_not_called()

    def test_waiting_without_a_section_still_uses_the_decision_route(self):
        with patch.object(client, 'cards', return_value=[card()]), patch.object(live, 'call', return_value=dict(ok=True, card=card())) as send:
            live.update('x', 'waiting_on_you', 'waiting for CI')
            self.assertEqual(send.call_args.kwargs.get('section'), 'needs_you')
            self.assertEqual(send.call_args.kwargs.get('state'), 'waiting_on_you')

    def test_failure_without_waiting_state_still_routes_to_ted(self):
        with patch.object(client,'cards',return_value=[card()]),patch.object(live,'call',return_value=dict(ok=True,card=card())) as send:
            live.update('x','blocked','Worker could not start. Reply to retry.')
            self.assertEqual(send.call_args.kwargs.get('section'),'up_next')

    def test_existing_inbox_failure_is_removed_without_asking_again(self):
        with patch.object(client,'cards',return_value=[card(section='needs_you')]),patch.object(live,'call',return_value=dict(ok=True,card=card())) as send:
            live.update('x','waiting_on_you','Worker could not start. Reply to retry.',section='needs_you')
            self.assertEqual(send.call_args.kwargs.get('section'),'up_next')
            self.assertEqual(send.call_args.kwargs.get('expected_section'),'needs_you')

    def test_valid_rule_application_still_avoids_an_ask(self):
        with patch.object(client,'cards',return_value=[card(decision_kind='send_email')]), \
             patch.object(client,'resolve_rule',return_value=dict(outcome='rule_applied',rule_id='r')), \
             patch.object(live,'call') as send:
            result=live.update('x','waiting_on_you','approve sending the drafted email',section='needs_you',apply_rule_id='r')
            self.assertEqual(result['outcome'],'rule_applied');send.assert_not_called()

    def test_lost_failure_ack_is_idempotently_confirmed(self):
        with patch.object(client,'cards',return_value=[card(section='up_next',live_state='blocked',live_status='worker failed, ted will review recovery from the job files')]),patch.object(live,'call') as send:
            result=live.update('x','blocked','worker failed, ted will review recovery from the job files',section='up_next')
            self.assertEqual(result['section'],'up_next');send.assert_not_called()

    def test_matching_rule_holds_for_ted_without_an_automatic_override_reason(self):
        with patch.object(client,'cards',return_value=[card(decision_kind='send_email')]),patch.object(client,'resolve_rule',side_effect=client.RuleResolutionRequired) as resolve,patch.object(live,'call',return_value=dict(ok=True,card=card())) as send:
            live.update('x','waiting_on_you','approve sending the drafted email',section='needs_you',expected_updated_at='2026-10-20T00:00:00Z')
            self.assertIsNone(resolve.call_args.args[-1])
            self.assertEqual(send.call_args.kwargs.get('section'),'up_next')

class Runner(unittest.TestCase):
    def setUp(self):
        self.load = patch.object(sessions.os, 'getloadavg', return_value=(0, 0, 0))
        self.load.start(); self.addCleanup(self.load.stop)

    def session(self, root, **extra):
        store = sessions.Store(root)
        store.enqueue(card(), 'do the work', 'receipt', engine='codex')
        with store.locked() as data:
            data['sessions']['x'].update(status='running', pid=123, identity='fixture', turn='turn', queue=[],
                                         started_at=1, **extra)
        return store, store.read()['sessions']['x']

    def test_timeout_and_no_result_retry_once_durably_then_hold(self):
        for failure in ('timeout', 'no_result'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                store, s = self.session(tmp)
                prefix = Path(s['cwd']) / 'turn'
                if failure == 'timeout':
                    sessions.atomic(str(prefix)+'.result.json', dict(ok=False, failure_kind='timeout', text='worker timeout'))
                with patch.object(sessions, 'alive', return_value=False), \
                     patch.object(sessions, 'publish_live', return_value=True) as publish, \
                     patch.object(sessions, 'identity', return_value='fixture'), \
                     patch.object(sessions.subprocess, 'Popen', return_value=Mock(pid=456)):
                    store.tick()
                    retry = store.read()['sessions']['x']
                    self.assertEqual(retry['status'], 'running')
                    inp = json.loads((Path(s['cwd']) / (retry['turn']+'.input.json')).read_text())
                    self.assertIn('resume from your files', inp['prompt'].lower())
                    sessions.atomic(Path(s['cwd']) / (retry['turn']+'.result.json'), dict(ok=False, failure_kind=failure, text='failed again'))
                    sessions.Store(tmp).tick()
                    store.tick()
                saved = store.read()
                self.assertEqual(saved['sessions']['x']['status'], 'failed')
                self.assertEqual(saved['sessions']['x']['queue'], [])
                notes = [x for x in saved['outbox'] if x.get('token', '').startswith('worker-failure-')]
                self.assertEqual(len(notes), 1)
                self.assertNotIn('reply to', notes[0]['text'].lower())
                self.assertTrue(any(p.kwargs.get('section') == 'up_next' and p.args[1] == 'blocked' for p in publish.call_args_list))
                self.assertFalse(any(p.kwargs.get('section') == 'needs_you' for p in publish.call_args_list))

    def test_start_failure_crash_and_malformed_result_hold_without_retry(self):
        for result in (dict(ok=False, failure_kind='crash', text='Worker failed: crash'), 'invalid'):
            with self.subTest(result=result), tempfile.TemporaryDirectory() as tmp:
                store, s = self.session(tmp)
                p = Path(s['cwd'])/'turn.result.json'
                p.write_text(result if isinstance(result, str) else json.dumps(result))
                with patch.object(sessions, 'alive', return_value=False), patch.object(sessions, 'publish_live', return_value=True) as publish:
                    store.tick()
                self.assertEqual(store.read()['sessions']['x']['status'], 'failed')
                self.assertEqual(publish.call_args.kwargs['section'], 'up_next')
        with tempfile.TemporaryDirectory() as tmp:
            store = sessions.Store(tmp); store.enqueue(card(), 'work', 'receipt')
            with patch.object(sessions.subprocess, 'Popen', side_effect=OSError), patch.object(sessions, 'publish_live', return_value=True) as publish:
                store.tick()
            self.assertEqual(store.read()['sessions']['x']['status'], 'failed')
            self.assertEqual(publish.call_args.kwargs['section'], 'up_next')

    def test_failed_turn_cannot_offer_stale_approval_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, s = self.session(tmp)
            (Path(s['cwd'])/'draft-email.json').write_text('{}')
            sessions.atomic(Path(s['cwd'])/'turn.result.json', dict(ok=False, failure_kind='crash', text='crash'))
            with patch.object(sessions, 'alive', return_value=False), patch.object(sessions, 'publish_live', return_value=True):
                store.tick(); store.collect_approvals()
            self.assertEqual(store.read()['approvals'], {})

    def test_db_artifact_is_ted_review_without_explicit_prod_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, s = self.session(tmp)
            with store.locked() as data: data['sessions']['x']['status'] = 'done'
            (Path(s['cwd'])/'apply.sql').write_text('-- offline fixture')
            store.collect_approvals()
            saved = store.read()
            self.assertEqual(saved['approvals'], {})
            self.assertNotIn('Approval needed', str(saved['outbox']))

    def test_empty_codex_result_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, s = self.session(tmp)
            with store.locked() as data: data['sessions']['x']['pid'] = os.getpid()
            s = store.read()['sessions']['x']; prefix = Path(s['cwd'])/'turn'
            sessions.atomic(str(prefix)+'.input.json', dict(session=s, prompt='fixture'))
            with patch.object(worker, 'identity', return_value='fixture'), patch.object(worker, 'engine_command', return_value=['fixture']), \
                 patch.object(worker.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)):
                worker.run(prefix)
            result = json.loads(Path(str(prefix)+'.result.json').read_text())
            self.assertFalse(result['ok'])
            self.assertEqual(result['failure_kind'], 'no_result')

    def test_retry_waits_for_confirmed_failure_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=False),patch.object(sessions.subprocess,'Popen') as spawn:
                store.tick();store.tick()
                spawn.assert_not_called()
            saved=store.read()['sessions']['x']
            self.assertEqual(len(saved['queue']),1)
            self.assertTrue(saved['failure_publish_pending'])
            with patch.object(sessions,'publish_live',return_value=True),patch.object(sessions,'identity',return_value='fixture'),patch.object(sessions.subprocess,'Popen',return_value=Mock(pid=456)) as spawn:
                sessions.Store(tmp).tick()
                self.assertEqual(spawn.call_count,1)

    def test_review_veto_and_user_stop_never_auto_retry(self):
        for mode in ('review','veto','stop'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                store,s=self.session(tmp)
                with store.locked() as data:
                    job=data['sessions']['x']
                    if mode=='review':
                        job['reviewing']='a';data['approvals']['a']=dict(id='a',card_id='x',status='reviewing',kind='email')
                    elif mode=='veto':job['active_veto_revision']=1
                    else:job['kill_requested_at']=1
                sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=False,failure_kind='timeout',text='worker timeout'))
                with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=True),patch.object(sessions.subprocess,'Popen') as spawn:
                    store.tick();spawn.assert_not_called()
                self.assertEqual(store.read()['sessions']['x']['queue'],[])

    def test_retry_start_status_is_retried_after_transport_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',side_effect=[True,False]),patch.object(sessions,'identity',return_value='fixture'),patch.object(sessions.subprocess,'Popen',return_value=Mock(pid=456)):
                store.tick()
            with patch.object(sessions,'alive',return_value=True),patch.object(sessions,'publish_live',return_value=True) as publish:
                sessions.Store(tmp).tick()
            self.assertEqual(publish.call_args.kwargs.get('expected_section'),'up_next')
            self.assertEqual(publish.call_args.args[1],'running')

    def test_legacy_empty_success_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,s=self.session(tmp)
            sessions.atomic(Path(s['cwd'])/'turn.result.json',dict(ok=True,text='Worker returned no final answer. Reply to retry.'))
            with patch.object(sessions,'alive',return_value=False),patch.object(sessions,'publish_live',return_value=True),patch.object(sessions,'identity',return_value='fixture'),patch.object(sessions.subprocess,'Popen',return_value=Mock(pid=456)):
                store.tick()
            retry=store.read()['sessions']['x']
            self.assertEqual(retry['status'],'running')
            self.assertEqual(retry['active_turn']['recovery_attempt'],1)

class Reaper(unittest.TestCase):
    def test_orphans_artifact_errors_and_dead_workers_go_to_ted(self):
        for job in (None, dict(status='failed'), dict(status='failed', artifact_error='unsafe'), dict(status='done')):
            with self.subTest(job=job), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); d = root/'card-x'; d.mkdir()
                if job is not None:
                    (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d), queue=[], **job)})))
                with patch.object(reaper, 'update') as publish:
                    reaper.reap([card()], root, now=2000000000)
                self.assertEqual(publish.call_args.kwargs.get('section'), 'up_next')
                self.assertEqual(publish.call_args.args[1], 'blocked')

    def test_failure_wins_over_fresh_done_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'card-x';d.mkdir();(d/'REPORT.md').write_text('# Done\nMerged.')
            (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d), queue=[], status='failed', failure_kind='timeout')})))
            with patch.object(reaper, 'update') as publish:reaper.reap([card()],root,now=2000000000)
            self.assertEqual(publish.call_args.args[1],'blocked')
            self.assertEqual(publish.call_args.kwargs['section'],'up_next')

    def test_pending_approval_without_his_kind_goes_to_ted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'card-x';d.mkdir()
            (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d),queue=[],status='waiting_approval')})))
            with patch.object(reaper,'update') as publish:reaper.reap([card()],root,now=2000000000)
            self.assertEqual(publish.call_args.kwargs['section'],'up_next')

    def test_real_email_approval_remains_an_explicit_send_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'card-x';d.mkdir()
            (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d),queue=[],status='waiting_approval')},approvals={'a':dict(card_id='x',kind='email',status='pending')})))
            with patch.object(reaper,'update') as publish:reaper.reap([card()],root,now=2000000000)
            self.assertEqual(publish.call_args.kwargs['section'],'needs_you')
            self.assertIn('sending',publish.call_args.args[2])

    def test_known_veto_gate_refusal_keeps_its_required_email_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'card-x';d.mkdir()
            (root/'sessions.json').write_text(json.dumps(dict(sessions={'x':dict(cwd=str(d),queue=[],status='failed',veto_outcome=dict(status='uncertain',revision=1))})))
            with patch.object(reaper,'update') as publish:reaper.reap([card(revision=1,decision_kind='send_email')],root,now=2000000000)
            self.assertEqual(publish.call_args.kwargs['section'],'needs_you')
            self.assertIn('Gmail Sent',publish.call_args.args[2])

class WorkerResults(unittest.TestCase):
    session=Runner.session
    setUp=Runner.setUp
    # Exercise result parsing, with only the process execution boundary replaced.
    def test_worker_structures_timeout_crash_and_empty_claude_result(self):
        for engine,outcome in [('codex','timeout'),('codex','crash'),('claude','empty'),('claude','complete')]:
            with self.subTest(engine=engine,outcome=outcome),tempfile.TemporaryDirectory() as tmp:
                store,s=self.session(tmp)
                with store.locked() as data:data['sessions']['x'].update(pid=os.getpid(),engine=engine)
                s=store.read()['sessions']['x'];prefix=Path(s['cwd'])/'turn'
                sessions.atomic(str(prefix)+'.input.json',dict(session=s,prompt='fixture'))
                def execute(*a,**kw):
                    if outcome=='timeout':raise subprocess.TimeoutExpired(['fixture'],1)
                    if outcome=='crash':raise OSError('private detail must not be copied')
                    kw['stdout'].write(json.dumps(dict(type='result',result='finished' if outcome=='complete' else '',is_error=False))+'\n')
                    return types.SimpleNamespace(returncode=0)
                with patch.object(worker,'identity',return_value='fixture'),patch.object(worker,'engine_command',return_value=['fixture']),patch.object(worker.subprocess,'run',side_effect=execute):worker.run(prefix)
                result=json.loads(Path(str(prefix)+'.result.json').read_text())
                self.assertEqual(result['ok'],outcome=='complete')
                if outcome!='complete':self.assertEqual(result['failure_kind'],dict(timeout='timeout',crash='crash',empty='no_result')[outcome])
                self.assertNotIn('private detail',str(result))

class Steward(unittest.TestCase):
    def action(self, c, mockups=()):
        return steward.plan([c], list(mockups), [], 2000000000)['actions']

    def test_failures_override_old_options_and_other_kind(self):
        for text in ('Worker exceeded the three-hour limit. Reply to continue.',
                     'Worker stopped without a final result. Reply to retry.',
                     'Worker could not start. Reply to retry.', 'Worker failed: OSError. Reply to retry.'):
            c = card(section='needs_you',decision_kind='other',options=['retry'],
                     messages=[dict(who='ted',at='2026-10-22T00:00:00Z',text=text)])
            actions=self.action(c)
            self.assertEqual(len(actions),1,text)
            self.assertEqual(actions[0]['to'],'up_next')

    def test_archived_batch_and_explicit_supersession_leave_inbox(self):
        c=card(section='needs_you',decision_kind='approve_design',title='Review mockups',body='Pick batch "Launch v2"')
        rows=[dict(id='m',project='Fixture',batch='Launch v2',status='archived',created_at='2026-10-01T00:00:00Z')]
        self.assertEqual(self.action(c,rows)[0]['to'],'done')
        c=card(section='needs_you',decision_kind='other',live_status='superseded by the new launch card')
        self.assertEqual(self.action(c)[0]['to'],'done')

    def test_fyi_with_historical_money_or_other_kind_has_no_ask(self):
        c=card(section='needs_you',decision_kind='other',title='Payment receipt for $25',body='Payment completed. No action required.')
        self.assertEqual(self.action(c)[0]['to'],'done')

    def test_only_running_worker_evidence_moves_an_unclassified_report(self):
        c=card(section='needs_you',live_state='running',live_status='checking the native build')
        self.assertEqual(self.action(c)[0]['to'],'up_next')
        c=card(section='needs_you',live_state='blocked',live_status='pr 42 awaits ted review and deployment')
        self.assertEqual(self.action(c),[])

    def test_allowed_decisions_and_fresh_taste_picks_survive(self):
        for body,kind in [('Approve spending $50','spend_money'),('Approve sending the drafted email','send_email'),
                          ('Please sign the contract',None),('Choose the subscription price',None),
                          ('Approve the gated production database write',None),('Write your version of the headline',None)]:
            self.assertEqual(self.action(card(section='needs_you',body=body,decision_kind=kind)),[],body)
        c=card(section='needs_you',decision_kind='approve_design',body='Pick batch "Launch v2"')
        rows=[dict(id='m',project='Fixture',batch='Launch v2',status='open',verdict=None,created_at='2026-10-22T00:00:00Z')]
        self.assertFalse(any(a['kind']=='move' for a in self.action(c,rows)))

    def test_new_real_ask_wins_over_historical_worker_failure(self):
        c=card(section='needs_you',body='Please sign the contract',
               messages=[dict(who='ted',at='2026-10-20T00:00:00Z',text='Worker failed: OSError'),
                         dict(who='ted',at='2026-10-22T00:00:00Z',text='Please sign the contract')])
        self.assertEqual(self.action(c),[])

    def test_archived_copy_is_not_mistaken_for_pricing_due_to_background_text(self):
        c=card(section='needs_you',body='Batch "Launch v2". Type your version of the headline. I need to confirm the current price first.')
        rows=[dict(id='m',project='Fixture',batch='Launch v2',status='archived',created_at='2026-10-01T00:00:00Z')]
        self.assertEqual(self.action(c,rows)[0]['to'],'done')

    def test_unclassified_reports_and_unrelated_questions_are_retained(self):
        for text in ('Uploaded the screens. The monthly paywall says $9.99.',
                     'Finished the search screen. Its label is "Is my character here?".',
                     'Uploaded the hero. The reference caption says "please welcome the cast".'):
            c=card(section='needs_you',body=text,decision_kind='other')
            self.assertEqual(self.action(c),[])

    def test_dry_run_and_snapshot_race_have_no_mutations(self):
        c=card(section='needs_you',live_status='Worker could not start')
        changed=card(section='needs_you',body='Please sign the contract',live_status='Please sign the contract',updated_at='2026-10-23T00:00:00Z')
        with tempfile.TemporaryDirectory() as tmp,patch.object(steward,'snapshot',return_value=([c],[],[])),patch.object(steward,'move_card') as move,patch.object(steward,'archive_batch') as archive:
            result=steward.run_once(tmp,dry_run=True,now=2000000000)
            self.assertEqual(result['planned_moves'],1);move.assert_not_called();archive.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()),[])
        with tempfile.TemporaryDirectory() as tmp,patch.object(steward,'snapshot',side_effect=[([c],[],[]),([changed],[],[])]),patch.object(steward,'fetch_cards',return_value=[changed]),patch.object(steward,'move_card') as move:
            result=steward.run_once(tmp,now=2000000000)
            self.assertEqual(result['deferred'],1);move.assert_not_called()

    def test_steward_move_sets_blocked_with_exact_snapshot_guard(self):
        with patch.object(live,'call',return_value=dict(ok=True,card=card())) as send:
            steward.move_card('x','up_next','ted review','2026-10-23T00:00:00Z')
            self.assertEqual(send.call_args.kwargs['expected_section'],'needs_you')
            self.assertEqual(send.call_args.kwargs['expected_updated_at'],'2026-10-23T00:00:00Z')
            self.assertEqual(send.call_args.kwargs['state'],'blocked')

    def test_running_build_still_protects_its_batch_from_archive(self):
        c=card(section='ted_doing',live_state='running',body='Implement batch "Launch v2"')
        rows=[dict(id='m',project='Fixture',batch='Launch v2',status='open',verdict='approved',created_at='2026-10-01T00:00:00Z')]
        self.assertFalse(any(a['kind']=='archive' for a in steward.plan([c],rows,[],2000000000)['actions']))

if __name__=='__main__':unittest.main()
