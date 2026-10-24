"""Offline lease and admission integration tests, with no model or transport calls."""
import reconciler_test_support
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('TED_RUNTIME_SOURCE', HERE.parents[1] / 'candidate'))
sys.path.insert(0, str(HERE))


def forbidden(*args, **kwargs):
    raise AssertionError('external operation forbidden in offline test')


def load(name, filename, deps):
    spec = importlib.util.spec_from_file_location(name, SOURCE / filename)
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, deps):
        spec.loader.exec_module(result)
    return result


client = types.SimpleNamespace(BoardConflict=RuntimeError, BoardGone=LookupError, call=forbidden)
live = types.SimpleNamespace(instructions=lambda cid: 'fixture instructions', publish_live=forbidden)
sessions = load('lease_sessions', 'sessions.py', {'board_client': client, 'live_status': live})
worker = load('lease_worker', 'session_worker.py', {'board_client': client, 'sessions': sessions})


class LeaseDispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = sessions.Store(self.tmp.name)
        self.env = patch.dict(os.environ, {'TED_RECONCILER_ENABLED': 'true'}, clear=False)
        self.env.start();self.addCleanup(self.env.stop)
        # All process and network boundaries are forbidden unless a test supplies a fake.
        for owner, name in ((sessions.subprocess, 'run'), (sessions.subprocess, 'Popen'), (sessions, 'deliver')):
            p = patch.object(owner, name, side_effect=forbidden)
            p.start();self.addCleanup(p.stop)
        p = patch.object(sessions, 'publish_live', return_value=True)
        p.start();self.addCleanup(p.stop)

    def enqueue(self, cid='x', **fields):
        card = dict(id=cid, title='Synthetic work', **fields)
        self.store.enqueue(card, 'do fixture work', 'receipt-' + cid, engine='codex')
        return self.store.read()['sessions'][cid]

    def running(self, cid='x', expiry=None, **fields):
        self.enqueue(cid, **fields)
        now = time.time()
        with self.store.locked() as data:
            s = data['sessions'][cid]
            turn = s['queue'].pop(0)
            s.update(status='running', pid=os.getpid(), identity='fixture-identity', turn=turn['id'], active_turn=turn,
                     lease_token='token-' + cid, lease_expires_at=expiry if expiry is not None else now + 150,
                     lease=dict(token='token-' + cid, turn=turn['id'], pid=os.getpid(), identity='fixture-identity', renewed_at=now,
                                expires_at=expiry if expiry is not None else now + 150), last_activity=1)
        return self.store.read()['sessions'][cid]

    def result(self, s, **fields):
        payload = dict(ok=True, text='Verified fixture result', lease_token=s['lease_token'], turn=s['turn'],
                       pid=s['pid'], identity=s['identity'])
        payload.update(fields)
        sessions.atomic(Path(s['cwd']) / (s['turn'] + '.result.json'), payload)

    def tick(self, **patches):
        with patch.object(sessions, 'alive', return_value=True), patch.object(sessions, 'admission_state', return_value=dict(cap=0, reason='fixture')):
            self.store.tick(reconcile=True)

    def store_lock_is_free(self):
        with (self.store.root / '.sessions.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            fcntl.flock(handle, fcntl.LOCK_UN)
            return True

    def test_terminal_publication_runs_after_sessions_lock_is_released(self):
        s = self.running()
        self.result(s)
        observed = []
        with patch.object(sessions, 'publish_live', side_effect=lambda *a, **k: observed.append(self.store_lock_is_free()) or True):
            self.tick(reconcile=True)
        self.assertEqual(observed, [True])

    def test_slow_spawn_publication_does_not_block_peer_lease_renewal(self):
        peer = self.running('peer')
        self.enqueue('new')
        observed = [];threads = [];renewed = []
        def publish(*args, **kwargs):
            done = threading.Event()
            def renew():
                renewed.append(self.store.renew_lease('peer', peer['turn'], peer['pid'], peer['identity'], peer['lease_token']))
                done.set()
            thread = threading.Thread(target=renew);threads.append(thread);thread.start()
            observed.append(done.wait(0.2))
            return True
        with patch.object(sessions, 'identity', return_value='fixture-identity'), patch.object(sessions, 'publish_live', side_effect=publish):
            # dispatch() supplies its own publication double, so retain the real tick here.
            with patch.object(sessions, 'alive', return_value=True), patch.object(sessions, 'admission_state', return_value=dict(cap=16, reason='fixture')), \
                 patch.object(sessions.subprocess, 'Popen', return_value=types.SimpleNamespace(pid=5001)):
                self.store.tick(reconcile=True)
            for thread in threads:
                thread.join(timeout=1)
        self.assertEqual(observed, [True])
        self.assertEqual(renewed, [True])

    def test_failure_publication_runs_without_sessions_lock(self):
        s = self.running();self.result(s, ok=False, text='Worker timed out.', failure_kind='timeout')
        observed = []
        with patch.object(sessions, 'publish_live', side_effect=lambda *a, **k: observed.append(self.store_lock_is_free()) or True):
            self.tick(reconcile=True)
        self.assertEqual(observed, [True])
        self.assertNotIn('failure_publish_pending', self.store.read()['sessions']['x'])

    def test_failed_publication_survives_restart_and_retries_without_new_result(self):
        s = self.running();self.result(s)
        with patch.object(sessions, 'publish_live', return_value=False):
            self.tick(reconcile=True)
        observed = []
        with patch.object(sessions, 'publish_live', side_effect=lambda *a, **k: observed.append((a, k)) or True), \
             patch.object(sessions, 'admission_state', return_value=dict(cap=0, reason='fixture')):
            sessions.Store(self.tmp.name).tick(reconcile=True)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0][0][1:], ('blocked', 'ted review'))
        self.assertEqual(self.store.read()['sessions']['x']['status'], 'done')

    def test_publication_ack_never_discards_newer_turn_publication(self):
        s = self.running();self.result(s)
        def advance(*args, **kwargs):
            with self.store.locked() as data:
                current = data['sessions']['x']
                current.update(turn='new-turn', lease_token='new-token', status='failed', failure_publish_pending=True)
                self.store._queue_publication(data, current, 'blocked', 'new failure', 'failure', section='up_next')
            return True
        with patch.object(sessions, 'publish_live', side_effect=advance):
            self.tick(reconcile=True)
        saved = self.store.read()
        self.assertEqual(saved['publications']['x']['turn'], 'new-turn')
        self.assertEqual(saved['publications']['x']['line'], 'new failure')
        self.assertTrue(saved['sessions']['x']['failure_publish_pending'])

    def test_flush_delivery_runs_unlocked_and_preserves_concurrently_added_note(self):
        with self.store.locked() as data:
            data['outbox'] = [dict(card_id='x', text='first', token='first')]
        observed = [];threads = []
        def deliver(item):
            observed.append(self.store_lock_is_free())
            def append():
                with self.store.locked() as data:
                    data['outbox'].append(dict(card_id='x', text='new', token='new'))
            thread = threading.Thread(target=append);threads.append(thread);thread.start()
            thread.join(timeout=0.1)
            return True
        with patch.object(sessions, 'deliver', side_effect=deliver):
            self.store.flush()
        for thread in threads:
            thread.join(timeout=1)
        self.assertEqual(observed, [True])
        self.assertEqual(self.store.read()['outbox'], [dict(card_id='x', text='new', token='new')])

    def test_flush_preserves_unconfirmed_or_changed_notes(self):
        original = dict(card_id='x', text='first', token='same')
        with self.store.locked() as data:
            data['outbox'] = [original]
        def deliver(item):
            if not self.store_lock_is_free():return False
            with self.store.locked() as data:
                data['outbox'][0]['text'] = 'changed while delivering'
            return True
        with patch.object(sessions, 'deliver', side_effect=deliver):
            self.store.flush()
        self.assertEqual(self.store.read()['outbox'], [dict(card_id='x', text='changed while delivering', token='same')])

    def test_flush_transport_failure_preserves_note_for_retry(self):
        original = dict(card_id='x', text='first', token='same')
        with self.store.locked() as data:
            data['outbox'] = [original]
        with patch.object(sessions, 'deliver', side_effect=RuntimeError('fixture transport failed')):
            self.store.flush()
        self.assertEqual(self.store.read()['outbox'], [original])

    def test_dead_letter_retains_fresh_requests_until_explicit_redrive(self):
        self.enqueue()
        with self.store.locked() as data:
            data['sessions']['x']['status'] = 'dead_letter'
        self.store.enqueue(dict(id='x', title='Fresh request'), 'preserve this request', 'fresh', engine='codex')
        self.assertEqual(self.dispatch(), [])
        saved = self.store.read()['sessions']['x']
        self.assertEqual(saved['status'], 'dead_letter')
        self.assertEqual([t['message'] for t in saved['queue']], ['do fixture work', 'preserve this request'])

    def test_ordinary_watcher_tick_never_consumes_result_or_spawns_when_enabled(self):
        s = self.running('finished');self.result(s)
        self.enqueue('queued')
        before = self.store.read()
        with patch.object(sessions, 'publish_live', side_effect=forbidden), patch.object(sessions, 'alive', side_effect=forbidden):
            self.store.tick()
        self.assertEqual(self.store.read(), before)

    def test_ordinary_watcher_cannot_collect_approvals_when_enabled(self):
        s = self.enqueue()
        with self.store.locked() as data:
            data['sessions']['x'].update(status='done', queue=[])
        (Path(s['cwd']) / 'draft-email.json').write_text('{}')
        self.store.collect_approvals()
        self.assertEqual(self.store.read()['approvals'], {})
        self.store.collect_approvals(reconcile=True)
        self.assertEqual(len(self.store.read()['approvals']), 1)

    def test_watcher_uses_durable_flag_when_environment_does_not_enable_it(self):
        self.enqueue('queued')
        before = self.store.read()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp);(directory / 'jobs').mkdir()
            (directory / 'jobs/reconciler-config.json').write_text('{"enabled":true}')
            with patch.dict(os.environ, {'TED_RECONCILER_ENABLED': 'false'}), patch.dict(sessions.reconciler_enabled.__globals__, {'__file__': str(directory / 'runner_admission.py')}):
                self.store.tick()
        self.assertEqual(self.store.read(), before)

    def test_completed_result_beats_expired_lease_even_with_live_pid(self):
        # Reverting result-first handling leaves the session stuck running.
        s = self.running(expiry=time.time() - 1)
        self.result(s)
        self.tick(reconcile=True)
        data = self.store.read()
        self.assertEqual(data['sessions']['x']['status'], 'done')
        self.assertEqual(len(data['outbox']), 1)
        self.tick(reconcile=True)
        self.assertEqual(len(self.store.read()['outbox']), 1)

    def test_expired_live_worker_is_recovery_work_without_legacy_failure(self):
        self.running(expiry=time.time() - 1)
        self.tick(reconcile=True)
        data = self.store.read();s = data['sessions']['x']
        self.assertEqual(s['recovery_required'], 'lease_expired')
        self.assertEqual(s['status'], 'running')
        self.assertEqual(s['last_activity'], 1)
        self.assertEqual(data['outbox'], [])

    def test_missing_lease_defers_to_reconciler_without_legacy_failure(self):
        s = self.running()
        with self.store.locked() as data:
            for field in ('lease', 'lease_token', 'lease_expires_at'):
                data['sessions']['x'].pop(field)
        self.tick(reconcile=True)
        data = self.store.read()
        self.assertEqual(data['sessions']['x']['recovery_required'], 'lease_missing')
        self.assertEqual(data['outbox'], [])

    def test_dead_process_with_live_lease_is_not_a_legacy_terminal_failure(self):
        self.running()
        with patch.object(sessions, 'alive', return_value=False), patch.object(sessions, 'admission_state', return_value=dict(cap=0, reason='fixture')):
            self.store.tick(reconcile=True)
        data = self.store.read()
        self.assertEqual(data['sessions']['x']['recovery_required'], 'worker_missing')
        self.assertEqual(data['outbox'], [])

    def test_malformed_lease_is_visible_recovery_work(self):
        self.running()
        with self.store.locked() as data:
            data['sessions']['x']['lease'] = 'corrupt'
        self.tick(reconcile=True)
        self.assertEqual(self.store.read()['sessions']['x']['recovery_required'], 'lease_missing')

    def test_inconsistent_nested_lease_never_counts_as_healthy(self):
        self.running()
        with self.store.locked() as data:
            data['sessions']['x']['lease']['token'] = 'wrong-token'
        self.tick(reconcile=True)
        self.assertEqual(self.store.read()['sessions']['x']['recovery_required'], 'lease_missing')

    def test_expired_worker_recovery_status_is_not_republished_running(self):
        self.running(expiry=time.time() - 1)
        with self.store.locked() as data:
            data['sessions']['x']['recovery_section'] = 'up_next'
        with patch.object(sessions, 'publish_live', side_effect=forbidden):
            self.tick(reconcile=True)
        self.assertEqual(self.store.read()['sessions']['x']['recovery_required'], 'lease_expired')

    def test_disabled_mode_keeps_failure_policy_retry(self):
        s = self.running(expiry=time.time() - 1)
        with patch.dict(os.environ, {'TED_RECONCILER_ENABLED': 'false'}), patch.object(sessions, 'alive', return_value=False), \
             patch.object(sessions, 'publish_live', return_value=False):
            self.store.tick(reconcile=True)
        data = self.store.read()
        self.assertEqual(data['sessions']['x']['status'], 'queued')
        self.assertEqual(data['sessions']['x']['queue'][0]['recovery_attempt'], 1)
        self.assertEqual(len(data['outbox']), 1)

    def test_enabled_result_failure_leaves_retry_to_reconciler(self):
        s = self.running()
        self.result(s, ok=False, failure_kind='timeout', text='Worker timed out.')
        self.tick(reconcile=True)
        saved = self.store.read()
        self.assertEqual(saved['sessions']['x']['status'], 'failed')
        self.assertEqual(saved['sessions']['x']['queue'], [])
        self.assertEqual(len(saved['outbox']), 1)

    def test_stale_token_result_cannot_complete_replacement(self):
        s = self.running(expiry=time.time() - 1)
        self.result(s, lease_token='old-token')
        self.tick(reconcile=True)
        self.assertEqual(self.store.read()['sessions']['x']['status'], 'running')
        self.assertEqual(self.store.read()['outbox'], [])

    def test_each_result_fence_is_required(self):
        for field, wrong in (('turn', 'old-turn'), ('pid', -1), ('identity', 'old-identity')):
            with self.subTest(field=field):
                s = self.running(cid=field, expiry=time.time() - 1)
                self.result(s, **{field: wrong})
                self.tick(reconcile=True)
                self.assertEqual(self.store.read()['sessions'][field]['status'], 'running')
        self.assertEqual(self.store.read()['outbox'], [])

    def test_renewal_cannot_resurrect_expired_or_replaced_claim(self):
        s = self.running()
        for mutation in ({'lease_token': 'replacement'}, {'turn': 'new-turn'}, {'identity': 'replacement'}, {'pid': -1}, {'lease_expires_at': time.time() - 1}):
            with self.subTest(mutation=mutation):
                with self.store.locked() as data:
                    data['sessions']['x'] = dict(s, **mutation)
                with patch.object(sessions, 'identity', return_value='fixture-identity'):
                    self.assertFalse(self.store.renew_lease('x', s['turn'], s['pid'], s['identity'], s['lease_token']))

    def test_enqueue_keeps_priority_owner_and_transition_timestamps(self):
        self.enqueue(priority_class='client_revenue', explicit_ask=True, owner='ted', action_started_at='2026-10-01T00:00:00Z',
                     next_action_due='2026-10-02T00:00:00Z', created_at='2026-09-01T00:00:00Z')
        s = self.store.read()['sessions']['x']
        self.assertEqual(s['priority_class'], 'client_revenue')
        self.assertIs(s['explicit_ask'], True)
        self.assertEqual(s['owner'], 'ted')
        self.assertEqual(s['action_started_at'], '2026-10-01T00:00:00Z')
        self.assertEqual(s['next_action_due'], '2026-10-02T00:00:00Z')
        self.assertEqual(s['created_at'], '2026-09-01T00:00:00Z')

    def test_side_effect_classification_survives_enqueue(self):
        self.enqueue(side_effecting=True)
        self.assertIs(self.store.read()['sessions']['x']['side_effecting'], True)

    def test_fresh_ordinary_enqueue_resets_retry_but_automatic_retry_preserves_it(self):
        self.enqueue()
        with self.store.locked() as data:
            data['sessions']['x']['retry_count'] = 2
        card = dict(id='x', title='Fixture')
        self.store.enqueue(card, 'resume', 'reconciler-retry-x-1', engine='codex')
        self.assertEqual(self.store.read()['sessions']['x']['retry_count'], 2)
        self.store.enqueue(card, 'new human instruction', 'new-receipt', engine='codex')
        self.assertEqual(self.store.read()['sessions']['x']['retry_count'], 0)

    def dispatch(self, cap=16):
        sequence = []
        def spawn(command, **kwargs):
            prefix = Path(command[-1])
            sequence.append(json.loads(Path(str(prefix) + '.input.json').read_text())['session']['card_id'])
            return types.SimpleNamespace(pid=5000 + len(sequence))
        with patch.object(sessions, 'alive', return_value=True), patch.object(sessions, 'identity', return_value='fixture-identity'), \
             patch.object(sessions, 'publish_live', return_value=None), patch.object(sessions.subprocess, 'Popen', side_effect=spawn), \
             patch.object(sessions, 'admission_state', return_value=dict(cap=cap, reason='fixture')):
            self.store.tick(reconcile=True)
        return sequence

    def test_priority_dispatch_is_urgent_then_revenue_then_age(self):
        self.enqueue('ordinary-new', created_at='2026-10-02T00:00:00Z')
        self.enqueue('ordinary-old', created_at='2026-10-01T00:00:00Z')
        self.enqueue('revenue', priority_class='client_revenue', created_at='2026-10-03T00:00:00Z')
        self.enqueue('urgent', priority_class='urgent', created_at='2026-10-04T00:00:00Z')
        self.enqueue('explicit', explicit_ask=True, created_at='2026-10-05T00:00:00Z')
        self.assertEqual(self.dispatch(), ['urgent', 'explicit', 'revenue', 'ordinary-old', 'ordinary-new'])

    def test_ordinary_work_leaves_two_reserved_slots_and_urgent_can_use_them(self):
        for i in range(15):
            self.enqueue('ordinary-' + str(i))
        self.assertEqual(len(self.dispatch()), 14)
        self.enqueue('urgent-1', priority_class='urgent')
        self.enqueue('urgent-2', explicit_ask=True)
        self.assertEqual(self.dispatch(), ['urgent-1', 'urgent-2'])
        self.assertEqual(sum(s['status'] == 'running' for s in self.store.read()['sessions'].values()), 16)

    def test_dispatch_honors_retry_at_and_records_full_active_turn_and_fence(self):
        self.enqueue('later')
        self.enqueue('now')
        with self.store.locked() as data:
            data['sessions']['later']['retry_at'] = time.time() + 3600
        self.assertEqual(self.dispatch(), ['now'])
        s = self.store.read()['sessions']['now']
        self.assertEqual(s['active_turn']['message'], 'do fixture work')
        self.assertEqual(s['active_turn']['id'], s['turn'])
        self.assertEqual(s['lease']['pid'], s['pid'])
        self.assertEqual(s['lease']['token'], s['lease_token'])
        self.assertGreater(s['lease_expires_at'], time.time() + 140)

    def test_ordinary_claude_aggregate_does_not_take_third_slot(self):
        for i in range(3):
            self.store.enqueue(dict(id='claude-' + str(i), title='Fixture'), 'work', 'c' + str(i), engine='claude')
        self.assertEqual(len(self.dispatch()), 2)

    def test_wrapper_renews_while_fake_model_runs_and_fences_result(self):
        s = self.running()
        prefix = Path(s['cwd']) / s['turn']
        sessions.atomic(str(prefix) + '.input.json', dict(session=s, prompt='fixture'))
        Path(str(prefix) + '.last.txt').write_text('Complete fixture')
        before = s['lease']['renewed_at']
        def model(command, **kwargs):
            started = self.store.read()['sessions']['x']['lease']['renewed_at']
            self.assertGreater(started, before)
            time.sleep(0.06)
            current = self.store.read()['sessions']['x']
            self.assertGreater(current['lease']['renewed_at'], started)
            return types.SimpleNamespace(returncode=0)
        with patch.object(worker, 'identity', return_value='fixture-identity'), patch.object(sessions, 'identity', return_value='fixture-identity'), \
             patch.object(worker, 'engine_command', return_value=['fake-model']), patch.object(worker.subprocess, 'run', side_effect=model), \
             patch.object(worker, 'LEASE_RENEW_SECONDS', 0.01):
            worker.run(prefix)
        result = json.loads(Path(str(prefix) + '.result.json').read_text())
        self.assertTrue(result['ok'])
        self.assertEqual(result['lease_token'], 'token-x')
        self.assertEqual(result['turn'], s['turn'])
        self.assertEqual(result['pid'], os.getpid())
        self.assertEqual(result['identity'], 'fixture-identity')

    def test_wrapper_does_not_publish_result_after_token_replacement(self):
        s = self.running()
        prefix = Path(s['cwd']) / s['turn']
        sessions.atomic(str(prefix) + '.input.json', dict(session=s, prompt='fixture'))
        def replace_owner(command, **kwargs):
            with self.store.locked() as data:
                data['sessions']['x']['lease_token'] = 'replacement-token'
            return types.SimpleNamespace(returncode=0)
        with patch.object(worker, 'identity', return_value='fixture-identity'), patch.object(sessions, 'identity', return_value='fixture-identity'), \
             patch.object(worker, 'engine_command', return_value=['fake-model']), patch.object(worker.subprocess, 'run', side_effect=replace_owner):
            worker.run(prefix)
        self.assertFalse(Path(str(prefix) + '.result.json').exists())

    def test_expired_wrapper_never_starts_model_command(self):
        s = self.running(expiry=time.time() - 1)
        prefix = Path(s['cwd']) / s['turn']
        sessions.atomic(str(prefix) + '.input.json', dict(session=s, prompt='fixture'))
        with patch.object(worker, 'identity', return_value='fixture-identity'), patch.object(sessions, 'identity', return_value='fixture-identity'), \
             patch.object(worker, 'engine_command', side_effect=forbidden):
            worker.run(prefix)
        self.assertFalse(Path(str(prefix) + '.result.json').exists())

    def test_worker_handshake_rejects_wrong_pid_identity_turn_and_token(self):
        for field, wrong in (('pid', -1), ('identity', 'old-identity'), ('turn', 'old-turn'), ('lease_token', 'old-token')):
            with self.subTest(field=field):
                s = self.running(cid=field)
                prefix = Path(s['cwd']) / s['turn']
                sessions.atomic(str(prefix) + '.input.json', dict(session=s, prompt='fixture'))
                with self.store.locked() as data:
                    data['sessions'][field][field] = wrong
                with patch.object(worker, 'identity', return_value='fixture-identity'), patch.object(sessions, 'identity', return_value='fixture-identity'), \
                     patch.object(worker, 'engine_command', side_effect=forbidden):
                    worker.run(prefix)
                self.assertFalse(Path(str(prefix) + '.result.json').exists())


class AdmissionPressure(unittest.TestCase):
    def helper(self):
        import runner_admission
        return runner_admission

    def test_durable_enabled_flag_applies_without_watcher_environment(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'TED_RECONCILER_ENABLED': 'false'}):
            path = Path(temp) / 'reconciler-config.json'
            self.assertFalse(helper.reconciler_enabled(path))
            path.write_text('{"enabled":true}')
            self.assertTrue(helper.reconciler_enabled(path))
            path.write_text('{"enabled":false}')
            self.assertFalse(helper.reconciler_enabled(path))
            with patch.dict(os.environ, {'TED_RECONCILER_ENABLED': 'true'}):
                self.assertTrue(helper.reconciler_enabled(path))

    def test_invalid_durable_flag_never_silently_restores_legacy_dispatch(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'TED_RECONCILER_ENABLED': 'false'}):
            path = Path(temp) / 'reconciler-config.json'
            for content in ('not json', '{"enabled":"true"}', '[]'):
                path.write_text(content)
                with self.assertRaises(RuntimeError):
                    helper.reconciler_enabled(path)

    def test_load_and_memory_reduce_admission_without_increasing_hard_cap(self):
        helper = self.helper()
        for load, available, expected in ((18, 16, 16), (27, 16, 8), (27.1, 16, 0), (0, 7.9, 0)):
            with self.subTest(load=load, available=available), patch.dict(os.environ, {'TED_RUNNER_MAX_WORKERS': '99'}), \
                 patch.object(helper.os, 'cpu_count', return_value=18), patch.object(helper.os, 'getloadavg', return_value=(load, 0, 0)), \
                 patch.object(helper, 'available_memory', return_value=int(available * 1024 ** 3)):
                self.assertEqual(helper.admission_state()['cap'], expected)

    def test_unavailable_resource_observation_admits_no_new_work(self):
        helper = self.helper()
        with patch.object(helper, 'available_memory', return_value=None):
            self.assertEqual(helper.admission_state()['cap'], 0)

    def test_configured_host_cap_is_respected(self):
        helper = self.helper()
        with patch.dict(os.environ, {'TED_RUNNER_MAX_WORKERS': '5'}), patch.object(helper.os, 'cpu_count', return_value=18), \
             patch.object(helper.os, 'getloadavg', return_value=(1, 0, 0)), patch.object(helper, 'available_memory', return_value=32 * 1024 ** 3):
            self.assertEqual(helper.admission_state()['cap'], 5)

    def test_review_uses_claude_budget_even_for_codex_session(self):
        helper = self.helper()
        current = [dict(engine='claude'), dict(engine='codex', reviewing='approval')]
        with patch.dict(os.environ, {'TED_RUNNER_CLAUDE_CAP': '2'}):
            self.assertFalse(helper.can_admit(dict(engine='codex', priority_class='urgent'), dict(kind='review'), current, 16))

    def test_engine_cap_cannot_be_configured_above_host_limit(self):
        helper = self.helper()
        with patch.dict(os.environ, {'TED_RUNNER_CLAUDE_CAP': '99'}):
            running = [dict(engine='claude', priority_class='urgent') for _ in range(16)]
            self.assertFalse(helper.can_admit(dict(engine='claude', priority_class='urgent'), dict(kind='work'), running, 16))

    def test_vm_stat_page_size_is_used_and_purgeable_is_not_double_counted(self):
        helper = self.helper()
        output = 'Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 100.\nPages inactive: 200.\nPages speculative: 300.\nPages purgeable: 999.\n'
        with patch.object(helper.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout=output)):
            self.assertEqual(helper.available_memory(), 9830400)


if __name__ == '__main__':
    unittest.main()
