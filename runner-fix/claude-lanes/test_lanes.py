"""Offline candidate-runtime integration tests. Models and network are replaced."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(os.environ.get('TED_LANES_RUNTIME', Path.home() / 'ted-ops/ted-board'))
sys.path.insert(0, str(SOURCE))
client = types.SimpleNamespace(call=Mock(side_effect=AssertionError('network forbidden')),
                               BoardConflict=RuntimeError, BoardGone=LookupError)
live = types.SimpleNamespace(instructions=lambda _: '', publish_live=Mock())
with patch.dict(sys.modules, {'board_client': client, 'live_status': live}):
    import sessions
    import session_worker as worker


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        for name in ('.claude', '.claude-acct2', '.claude-acct3'):
            (self.home / name).mkdir(parents=True)
        self.config = self.root / 'config.json'
        self.config.write_text('{"enabled": true}')
        self.store = sessions.Store(self.root / 'jobs')
        self.card = dict(id='x', title='Design mockups', body='Synthetic brief')
        self.spawns = []
        self.addCleanup(patch.stopall)
        patch.object(Path, 'home', return_value=self.home).start()
        patch.dict(os.environ, {'TED_CLAUDE_LANES_CONFIG': str(self.config)}, clear=True).start()
        patch.object(sessions, 'publish_live').start()
        patch.dict(sessions.admission_state.__globals__, {'available_memory': lambda: 32 * 1024 ** 3}).start()
        patch.object(sessions, 'identity', return_value='fixture').start()
        patch.object(sessions, 'alive', return_value=True).start()
        patch.object(sessions.os, 'getloadavg', return_value=(0, 0, 0)).start()
        patch.object(sessions.os, 'cpu_count', return_value=8).start()
        patch.object(sessions.subprocess, 'Popen', side_effect=self.spawn).start()
        patch.object(sessions.subprocess, 'run', side_effect=self.cli).start()

    def cli(self, command, **kwargs):
        directory = kwargs['env']['CLAUDE_CONFIG_DIR']
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(dict(
            loggedIn=True, authMethod='claude.ai', subscriptionType='max', configDirectory=directory)))

    def spawn(self, command, **kwargs):
        inp = json.loads(Path(command[-1] + '.input.json').read_text())
        self.spawns.append((inp, kwargs['env']))
        return Mock(pid=100 + len(self.spawns))

    def enqueue(self, engine='claude', **card):
        self.store.enqueue(dict(self.card, **card), 'do the work', 'receipt-' + str(len(self.store.read()['receipts'])), engine)

    def state(self, cid='x'):
        return self.store.read()['sessions'][cid]

    def finish(self, result):
        s = self.state()
        sessions.atomic(Path(s['cwd']) / (s['turn'] + '.result.json'), result)
        with patch.object(sessions, 'alive', return_value=False):
            self.store.tick()

    def test_claude_design_receives_account_two_without_credentials(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'fixture-secret', 'CLAUDE_CODE_OAUTH_TOKEN': 'fixture-secret', 'ANTHROPIC_BASE_URL': 'https://invalid', 'HTTPS_PROXY': 'https://invalid'}):
            self.enqueue(); self.store.tick()
        inp, env = self.spawns[0]
        self.assertEqual(env.get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude-acct2'))
        self.assertFalse(any(key in env for key in ('ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'HTTPS_PROXY')))
        self.assertEqual(inp['session'].get('active_claude_lane'), 'design')
        self.assertIn('opus', sessions.engine_command(inp['session'], 'fixture', Path('fixture')))

    def test_research_and_review_gate_receive_account_three(self):
        self.enqueue(title='Long research and analysis'); self.store.tick()
        self.assertEqual(self.spawns[0][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude-acct3'))

    def test_default_engine_is_codex_and_never_gets_account_environment(self):
        self.store.enqueue(self.card, 'implement', 'default')
        self.store.tick()
        self.assertEqual(self.state()['engine'], 'codex')
        self.assertNotIn('CLAUDE_CONFIG_DIR', self.spawns[0][1])

    def test_disabled_flag_preserves_existing_claude_environment(self):
        self.config.write_text('{"enabled": false}')
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.home / '.claude'), 'ANTHROPIC_API_KEY': 'fixture'}):
            self.enqueue(); self.store.tick()
        self.assertEqual(self.spawns[0][1].get('ANTHROPIC_API_KEY'), 'fixture')
        self.assertEqual(self.spawns[0][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude'))

    def test_legacy_resume_stays_on_main_when_flag_is_enabled(self):
        self.enqueue()
        with self.store.locked() as data:
            data['sessions']['x']['session_id'] = 'legacy-session'
        self.store.tick()
        self.assertEqual(self.spawns[0][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude'))

    def test_inherited_directory_cannot_move_an_enabled_legacy_session(self):
        self.enqueue()
        with self.store.locked() as data:
            data['sessions']['x']['session_id'] = 'legacy-session'
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.home / '.claude-acct3')}):
            self.store.tick()
        self.assertEqual(self.spawns[0][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude'))

    def test_disable_after_assignment_waits_without_moving_conversation(self):
        self.enqueue(); self.store.tick()
        self.finish(dict(ok=True, text='done', session_id='design-session'))
        self.config.write_text('{"enabled": false}')
        self.enqueue(title='Research now'); self.store.tick()
        self.assertEqual(len(self.spawns), 1)
        self.assertEqual(self.state()['status'], 'queued')
        self.assertEqual(self.state()['session_id'], 'design-session')

    def test_limit_requeues_same_turn_and_waits_on_same_account(self):
        self.enqueue(); self.store.tick()
        turn = self.state()['turn']
        self.finish(dict(ok=False, text='limited', session_id='design-session', lane_usage=dict(limited=True, resets_at=9999999999, input_tokens=12)))
        self.assertEqual(self.state()['status'], 'queued')
        self.assertEqual(self.state()['queue'][0]['id'], turn)
        self.assertEqual(len(self.spawns), 1)
        self.assertEqual(self.store.read()['outbox'], [])
        self.enqueue(id='research', title='Research competitors'); self.store.tick()
        self.assertEqual(len(self.spawns), 2)
        self.assertEqual(self.spawns[-1][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude-acct3'))
        with patch('time.time', return_value=10000000000):
            self.store.tick()
        self.assertEqual(self.spawns[-1][0]['session']['session_id'], 'design-session')
        self.assertEqual(self.spawns[-1][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude-acct2'))

    def test_busy_design_does_not_block_research_or_codex(self):
        self.enqueue(); self.enqueue(id='y'); self.enqueue(id='z', title='Research'); self.enqueue(engine='codex', id='impl')
        self.store.tick()
        self.assertEqual([item[0]['session']['card_id'] for item in self.spawns], ['x', 'y', 'z', 'impl'])
        self.assertEqual(self.state('y')['status'], 'running')

    def test_missing_account_or_malformed_config_waits_without_fallback(self):
        for mode in ('missing', 'malformed'):
            with self.subTest(mode=mode):
                if mode == 'missing': (self.home / '.claude-acct2').rmdir()
                else: self.config.write_text('{')
                self.enqueue(); self.store.tick()
                self.assertEqual(self.spawns, [])
                self.assertEqual(self.state()['status'], 'queued')

    def test_wrong_auth_method_never_launches_a_dedicated_job(self):
        with patch.object(sessions.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout='{"loggedIn":true,"authMethod":"api_key"}')):
            self.enqueue(); self.store.tick()
        self.assertEqual(self.spawns, [])

    def test_non_object_login_status_queues_claude_without_blocking_codex(self):
        self.enqueue()
        self.enqueue(engine='codex', id='implementation')
        for value in ('[]', 'null', '"unexpected"', '0'):
            with self.subTest(response=value), patch.object(sessions.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout=value)):
                try:
                    self.store.tick()
                except Exception as exc:
                    self.fail('Malformed auth status escaped the dispatcher: ' + type(exc).__name__)
                self.assertEqual(self.state()['status'], 'queued')
                self.assertEqual([s[0]['session']['card_id'] for s in self.spawns], ['implementation'])

    def test_summary_uses_existing_job_contract_and_omits_identity(self):
        self.enqueue(); self.store.tick()
        self.finish(dict(ok=True, text='done', session_id='sid', lane_usage=dict(input_tokens=12, output_tokens=3)))
        rows = [j for j in self.store.snapshot()[0] if j['id'].startswith('claude-lane-')]
        self.assertEqual(len(rows), 3)
        design = next(j for j in rows if j['id'] == 'claude-lane-design')
        self.assertEqual(design['lane_usage']['input_tokens'], 12)
        self.assertIsNone(design['card_id'])
        self.assertEqual(design['status'], 'idle')
        self.assertNotIn(str(self.home), json.dumps(rows))

    def approve(self, engine='codex', title='Analysis gate'):
        self.enqueue(engine=engine, title=title)
        with self.store.locked() as data:
            s = data['sessions']['x']
            s.update(status='done', queue=[])
            (Path(s['cwd']) / 'draft-email.json').write_text('{"fixture": true}')
        self.store.collect_approvals()
        aid, a = next(iter(self.store.read()['approvals'].items()))
        with patch.object(sessions, 'call', return_value={}):
            self.store.controls([dict(id='cmd', card_id='x', target=aid, action='approve', payload=a)])
        return aid

    def test_review_limit_retries_approved_snapshot_on_same_lane(self):
        aid = self.approve()
        self.store.tick()
        self.assertEqual(self.spawns[0][1]['CLAUDE_CONFIG_DIR'], str(self.home / '.claude-acct3'))
        self.finish(dict(ok=False, text='limit', session_id='review-session', lane_usage=dict(limited=True, resets_at=9999999999)))
        self.assertEqual(self.store.read()['approvals'][aid]['status'], 'reviewing')
        self.assertIsNone(self.state()['session_id'])
        with patch('time.time', return_value=10000000000):
            self.store.tick()
        inp = self.spawns[-1][0]
        self.assertTrue(inp['review'])
        self.assertIn('review-session', sessions.engine_command(inp['session'], 'retry', Path('fixture'), True))
        self.finish(dict(ok=True, text='APPLY_OK', session_id='review-session'))
        self.assertEqual(self.store.read()['approvals'][aid]['status'], 'done')
        self.assertNotIn('review_session_id', self.state())

    def test_design_review_uses_verified_review_account(self):
        self.approve(title='Mockup design review'); self.store.tick()
        self.assertEqual(self.spawns[0][1]['CLAUDE_CONFIG_DIR'], str(self.home / '.claude-acct3'))

    def test_changed_approval_artifact_is_refused_even_after_limit(self):
        aid = self.approve(); self.store.tick()
        self.finish(dict(ok=False, text='limit', session_id='review-sid', lane_usage=dict(limited=True, resets_at=9999999999)))
        (Path(self.state()['cwd']) / 'draft-email.json').write_text('{"changed": true}')
        with patch('time.time', return_value=10000000000):
            self.store.tick()
        self.assertEqual(len(self.spawns), 1)
        self.assertEqual(self.store.read()['approvals'][aid]['status'], 'superseded')

    def test_symlink_account_is_refused(self):
        account = self.home / '.claude-acct2'
        account.rmdir(); account.symlink_to(self.home / '.claude')
        self.enqueue(); self.store.tick()
        self.assertEqual(self.spawns, [])

    def test_unknown_cli_values_stay_unknown_and_no_raw_data_is_published(self):
        import claude_lanes
        info = claude_lanes.observe([None, [], dict(type='result', usage=dict(input_tokens=True, output_tokens=-1), result='private fixture', is_error=False), dict(type='rate_limit_event', rate_limit_info=dict(status='rejected', resetsAt=9999999999, secret='fixture'))])
        self.assertEqual(info, dict(limited=True, limit_status='rejected', resets_at=9999999999))

    def test_worker_collects_usage_and_preserves_lane_environment(self):
        self.enqueue(); self.store.tick(); s = self.state()
        prefix = Path(s['cwd']) / s['turn']
        observed_env = []
        def model(command, **kwargs):
            observed_env.append(kwargs['env'])
            kwargs['stdout'].write(json.dumps(dict(type='result', session_id='new-sid', result='fixture result', usage=dict(input_tokens=42, output_tokens=7))) + '\n')
            return types.SimpleNamespace(returncode=0)
        with self.store.locked() as data:
            data['sessions']['x'].update(pid=os.getpid(), identity='fixture')
        with patch.object(worker, 'identity', return_value='fixture'), patch.object(worker.subprocess, 'run', side_effect=model):
            worker.run(prefix)
        result = json.loads(Path(str(prefix) + '.result.json').read_text())
        self.assertTrue(result['ok'])
        self.assertEqual(result['lane_usage'], dict(input_tokens=42, output_tokens=7))
        self.assertEqual(observed_env[0]['CLAUDE_CONFIG_DIR'], str(self.home / '.claude-acct2'))

    def test_invalid_review_cannot_contaminate_following_codex_environment(self):
        aid = self.approve()
        with self.store.locked() as data:
            data['approvals'][aid]['status'] = 'rejected'
            data['sessions']['x']['queue'].append(dict(id='next', kind='work', message='implement'))
        self.store.tick(); self.store.tick()
        self.assertNotIn('CLAUDE_CONFIG_DIR', self.spawns[0][1])
        self.assertNotIn('active_claude_lane', self.spawns[0][0]['session'])

    def test_veto_turn_does_not_select_a_model_lane(self):
        self.enqueue()
        with self.store.locked() as data:
            data['sessions']['x']['queue'][0]['veto_proposal_id'] = 'fixture'
            data['sessions']['x']['queue'][0]['veto_card_revision'] = 1
        self.config.write_text('{')
        self.store.tick()
        self.assertEqual(self.spawns[0][0]['veto_proposal_id'], 'fixture')
        self.assertNotIn('CLAUDE_CONFIG_DIR', self.spawns[0][1])

    def test_retry_cannot_consume_the_previous_limit_result_after_a_crash(self):
        self.enqueue(); self.store.tick()
        self.finish(dict(ok=False, text='limit', session_id='sid', lane_usage=dict(limited=True, resets_at=9999999999)))
        with patch('time.time', return_value=10000000000):
            self.store.tick()
            with patch.object(sessions, 'alive', return_value=False):
                self.store.tick()
        if hasattr(sessions.Store, '_worker_failure'):
            # The folded legacy recovery policy permits one no-result retry,
            # with a fresh turn, rather than re-reading the old usage-limit result.
            self.assertEqual(self.state()['active_turn']['recovery_attempt'], 1)
            self.assertNotEqual(self.state()['turn'], self.spawns[0][0]['session']['turn'])
            with patch.object(sessions, 'alive', return_value=False):
                self.store.tick()
        self.assertEqual(self.state()['status'], 'failed')
        self.assertEqual(self.state()['queue'], [])

    def test_success_after_transient_limit_is_never_replayed(self):
        self.enqueue(); self.store.tick()
        self.finish(dict(ok=True, text='completed', session_id='sid', lane_usage=dict(limited=True)))
        self.assertEqual(self.state()['status'], 'done')
        self.assertEqual(self.state()['queue'], [])

    def test_changed_limited_review_cannot_leak_identity_to_next_turn(self):
        aid = self.approve(); self.store.tick()
        self.finish(dict(ok=False, text='limit', session_id='old-review', lane_usage=dict(limited=True, resets_at=9999999999)))
        (Path(self.state()['cwd']) / 'draft-email.json').write_text('{"changed":true}')
        with patch('time.time', return_value=10000000000):
            self.store.tick()
        self.assertNotIn('reviewing', self.state())
        self.assertNotIn('review_session_id', self.state())
        self.assertNotIn('active_claude_lane', self.state())

    def test_approval_limit_without_resume_identity_requires_outcome_review(self):
        aid = self.approve(); self.store.tick()
        self.finish(dict(ok=False, text='limit', lane_usage=dict(limited=True)))
        with patch('time.time', return_value=10000000000):
            self.store.tick()
        self.assertEqual(len(self.spawns), 1)
        self.assertEqual(self.store.read()['approvals'][aid]['status'], 'failed')

    def test_stopping_limited_review_clears_affinity_before_codex_continuation(self):
        aid = self.approve(); self.store.tick()
        self.finish(dict(ok=False, text='limit', session_id='old-review', lane_usage=dict(limited=True, resets_at=9999999999)))
        s = self.state()
        with patch.object(sessions, 'call', return_value={}), patch.object(sessions, 'safe_kill', return_value=False), patch.object(sessions, 'alive', return_value=False):
            self.store.controls([dict(id='kill-review', card_id='x', action='kill', target='card-x', payload=dict(pid=s['pid'], identity=s['identity']))])
        self.assertEqual(self.store.read()['approvals'][aid]['status'], 'failed')
        self.assertNotIn('reviewing', self.state())
        self.assertNotIn('review_session_id', self.state())
        self.assertNotIn('active_claude_lane', self.state())
        self.enqueue(engine='codex'); self.store.tick()
        inp, env = self.spawns[-1]
        self.assertFalse(inp['review'])
        self.assertNotIn('CLAUDE_CONFIG_DIR', env)
        self.assertNotIn('active_claude_lane', inp['session'])
        self.finish(dict(ok=True, text='implementation complete', session_id='codex-thread'))
        self.assertEqual(self.state()['session_id'], 'codex-thread')

    def fill(self, engine, count, legacy=False):
        for i in range(count):
            cid = engine + '-' + str(i)
            self.enqueue(engine=engine, id=cid, title='Worker task')
            if legacy:
                with self.store.locked() as data:
                    data['sessions'][cid]['session_id'] = 'existing-' + cid

    def test_two_accounts_route_all_claude_and_sonnet_workers_to_account_two(self):
        (self.home / '.claude-acct3').rmdir()
        self.enqueue(title='Long research')
        self.enqueue(engine='sonnet', id='sonnet', title='Analysis and review')
        self.enqueue(id='art', title='Design art')
        self.store.tick()
        self.assertEqual(len(self.spawns), 3)
        self.assertEqual({env.get('CLAUDE_CONFIG_DIR') for _, env in self.spawns}, {str(self.home / '.claude-acct2')})
        s = self.state('sonnet')
        command = sessions.engine_command(s, 'fixture', Path('fixture'))
        self.assertEqual(command[command.index('--model') + 1], 'sonnet')

    def test_optional_account_three_needs_successful_auth_before_split(self):
        def login(command, **kwargs):
            if kwargs['env']['CLAUDE_CONFIG_DIR'].endswith('.claude-acct3'):
                return types.SimpleNamespace(returncode=1, stdout='{"loggedIn":false}')
            return self.cli(command, **kwargs)
        with patch.object(sessions.subprocess, 'run', side_effect=login):
            self.enqueue(title='Research'); self.store.tick()
        self.assertEqual(len(self.spawns), 1)
        self.assertEqual(self.spawns[0][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude-acct2'))
        self.enqueue(id='new', title='Research'); self.store.tick()
        self.assertEqual(self.spawns[-1][1].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude-acct3'))

    def test_account_three_arrival_never_moves_an_existing_account_two_session(self):
        (self.home / '.claude-acct3').rmdir()
        self.enqueue(title='Research'); self.store.tick()
        self.assertEqual(len(self.spawns), 1)
        self.finish(dict(ok=True, text='first turn', session_id='account-two-session'))
        (self.home / '.claude-acct3').mkdir()
        self.enqueue(title='Research'); self.enqueue(id='new', title='Research'); self.store.tick()
        continued = next(item for item in self.spawns[1:] if item[0]['session']['card_id'] == 'x')
        self.assertEqual(continued[0]['session']['session_id'], 'account-two-session')
        self.assertEqual(continued[1]['CLAUDE_CONFIG_DIR'], str(self.home / '.claude-acct2'))
        self.assertEqual(self.spawns[-1][1]['CLAUDE_CONFIG_DIR'], str(self.home / '.claude-acct3'))

    def test_two_account_approval_review_uses_account_two(self):
        (self.home / '.claude-acct3').rmdir()
        self.approve(engine='sonnet', title='Design review'); self.store.tick()
        self.assertTrue(self.spawns[0][0]['review'])
        self.assertEqual(self.spawns[0][1]['CLAUDE_CONFIG_DIR'], str(self.home / '.claude-acct2'))
        command = sessions.engine_command(self.spawns[0][0]['session'], 'fixture', Path('fixture'), True)
        self.assertEqual(command[command.index('--model') + 1], 'opus')

    def test_active_account_two_allows_four_opus_and_sixteen_sonnet_jobs(self):
        (self.home / '.claude-acct3').rmdir()
        self.fill('claude', 5); self.fill('sonnet', 17); self.fill('codex', 1)
        self.store.tick()
        engines = [item[0]['session']['engine'] for item in self.spawns]
        self.assertEqual((engines.count('claude'), engines.count('sonnet'), engines.count('codex')), (4, 16, 1))
        self.assertEqual(self.state('claude-4')['status'], 'queued')
        self.assertEqual(self.state('sonnet-16')['status'], 'queued')

    def test_disabled_lanes_keep_two_opus_and_eight_sonnet_caps(self):
        self.config.write_text('{"enabled": false}')
        self.fill('claude', 3); self.fill('sonnet', 9); self.fill('codex', 1)
        self.store.tick()
        engines = [item[0]['session']['engine'] for item in self.spawns]
        self.assertEqual((engines.count('claude'), engines.count('sonnet'), engines.count('codex')), (2, 8, 1))

    def test_unverified_account_two_does_not_raise_legacy_caps(self):
        self.fill('claude', 3, legacy=True); self.fill('sonnet', 9, legacy=True)
        def login(command, **kwargs):
            if kwargs['env']['CLAUDE_CONFIG_DIR'].endswith('.claude-acct2'):
                return types.SimpleNamespace(returncode=1, stdout='{"loggedIn":false}')
            return self.cli(command, **kwargs)
        with patch.object(sessions.subprocess, 'run', side_effect=login):
            self.store.tick()
        engines = [item[0]['session']['engine'] for item in self.spawns]
        self.assertEqual((engines.count('claude'), engines.count('sonnet')), (2, 8))

    def test_legacy_main_account_keeps_its_own_conservative_cap(self):
        self.fill('claude', 4, legacy=True)
        for i in range(4): self.enqueue(id='new-' + str(i))
        self.store.tick()
        directories = [env.get('CLAUDE_CONFIG_DIR') for _, env in self.spawns]
        self.assertEqual(directories.count(str(self.home / '.claude')), 2)
        self.assertEqual(directories.count(str(self.home / '.claude-acct2')), 2)

    def test_reviews_are_exempt_from_opus_worker_caps(self):
        self.approve(engine='sonnet'); self.fill('claude', 5); self.store.tick()
        self.assertEqual(len(self.spawns), 5)
        self.assertEqual(sum(bool(inp['review']) for inp, _ in self.spawns), 1)
        self.assertEqual(sum(inp['session']['engine'] == 'claude' for inp, _ in self.spawns), 4)

    def test_global_sixty_four_worker_limit_is_preserved(self):
        self.config.write_text('{"enabled": false}')
        self.fill('codex', 65); self.store.tick()
        self.assertEqual(len(self.spawns), 64)
        self.assertEqual(self.state('codex-64')['status'], 'queued')

    def test_load_guard_prevents_new_jobs_even_with_account_two_active(self):
        self.fill('codex', 1); self.fill('claude', 1); self.fill('sonnet', 1)
        with patch.object(sessions.os, 'getloadavg', return_value=(17, 0, 0)):
            self.store.tick()
        self.assertEqual(self.spawns, [])

    def test_sonnet_worker_retains_twelve_hour_timeout_and_usage_parsing(self):
        (self.home / '.claude-acct3').rmdir()
        self.enqueue(engine='sonnet'); self.store.tick(); s = self.state()
        prefix = Path(s['cwd']) / s['turn']
        observed = []
        def model(command, **kwargs):
            observed.append((command, kwargs))
            kwargs['stdout'].write(json.dumps(dict(type='result', session_id='sonnet-session', result='complete', usage=dict(input_tokens=13, output_tokens=5))) + '\n')
            return types.SimpleNamespace(returncode=0)
        with self.store.locked() as data: data['sessions']['x'].update(pid=os.getpid(), identity='fixture')
        with patch.object(worker, 'identity', return_value='fixture'), patch.object(worker.subprocess, 'run', side_effect=model): worker.run(prefix)
        result = json.loads(Path(str(prefix) + '.result.json').read_text())
        self.assertTrue(result['ok'])
        self.assertEqual(result['session_id'], 'sonnet-session')
        self.assertEqual(result['lane_usage'], dict(input_tokens=13, output_tokens=5))
        self.assertEqual(observed[0][1]['timeout'], 43200)
        self.assertEqual(observed[0][1]['env'].get('CLAUDE_CONFIG_DIR'), str(self.home / '.claude-acct2'))

    def test_sonnet_snapshot_uses_the_existing_heartbeat_engine_contract(self):
        self.enqueue(engine='sonnet'); self.store.tick()
        job = next(j for j in self.store.snapshot()[0] if j.get('card_id') == 'x')
        self.assertEqual(job['engine'], 'claude')
        self.assertEqual(job['worker_engine'], 'sonnet')
        self.assertEqual(self.state()['engine'], 'sonnet')

    def test_two_account_summary_reports_shared_workers_and_optional_account_three(self):
        (self.home / '.claude-acct3').rmdir()
        self.enqueue(title='Research'); self.store.tick()
        jobs = {j['id']: j for j in self.store.snapshot()[0]}
        self.assertEqual(jobs['claude-lane-design'].get('lane_role'), 'all_managed')
        self.assertIn('not configured', jobs['claude-lane-research']['last_line'])

    def test_claude_research_selects_opus_and_sonnet_design_keeps_sonnet(self):
        self.enqueue(title='Research'); self.enqueue(engine='sonnet', id='art', title='Design art'); self.store.tick()
        for cid, model in (('x', 'opus'), ('art', 'sonnet')):
            command = sessions.engine_command(self.state(cid), 'fixture', Path('fixture'))
            self.assertIn('--model', command)
            self.assertEqual(command[command.index('--model') + 1], model)
            self.assertEqual(command.count('--model'), 1)

    def test_approval_snapshot_reports_opus_even_on_a_sonnet_card(self):
        self.approve(engine='sonnet'); self.store.tick()
        job = next(j for j in self.store.snapshot()[0] if j.get('card_id') == 'x')
        self.assertEqual(job['engine'], 'claude')
        self.assertNotEqual(job.get('worker_engine'), 'sonnet')

    def test_expired_account_three_login_never_falls_back_for_a_pinned_session(self):
        self.enqueue(title='Research'); self.store.tick()
        self.finish(dict(ok=True, text='first turn', session_id='account-three-session'))
        def login(command, **kwargs):
            if kwargs['env']['CLAUDE_CONFIG_DIR'].endswith('.claude-acct3'):
                return types.SimpleNamespace(returncode=1, stdout='{"loggedIn":false}')
            return self.cli(command, **kwargs)
        with patch.object(sessions.subprocess, 'run', side_effect=login):
            self.enqueue(title='Research'); self.store.tick()
        self.assertEqual(len(self.spawns), 1)
        self.assertEqual(self.state()['status'], 'queued')
        self.assertEqual(self.state()['session_id'], 'account-three-session')


if __name__ == '__main__':
    unittest.main()
