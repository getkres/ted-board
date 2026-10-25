#!/usr/bin/env python3
"""Test disposable adapted private runtimes. All provider boundaries are isolated."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

SOURCE = None


class CurrentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.out = []
        client = types.ModuleType('board_client')
        client.BoardConflict = RuntimeError
        client.BoardGone = LookupError
        client.call = lambda *a, **k: self.fail('provider access forbidden')
        live = types.ModuleType('live_status')
        live.instructions = lambda *a: ''
        live.publish_live = lambda *a, **k: self.out.append((a,k)) or True
        self.modules = mock.patch.dict(sys.modules, board_client=client, live_status=live)
        self.modules.start(); self.addCleanup(self.modules.stop)
        self.runtime = self.root/'runtime'
        self.runtime.mkdir()
        self.marker = self.root/'ran'
        worker = 'from pathlib import Path\nimport sys\nPath(%r).touch()\nPath(sys.argv[1]+".ran").touch()\n' % str(self.marker)
        for name in ('session_worker.py','reconciler_worker.py'):
            (self.runtime/name).write_text(worker)
        self.children=[]
        self.addCleanup(self.reap)
        self.stderr = io.StringIO()
        patch = mock.patch('sys.stderr', self.stderr)
        patch.start();self.addCleanup(patch.stop)

    def reap(self):
        for child in self.children:
            child.wait(timeout=10)

    def load(self, managed=True, lanes=True):
        name='reconciler_sessions' if managed else 'sessions'
        spec=importlib.util.spec_from_file_location('candidate_'+name,SOURCE/(name+'.py'))
        self.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.ROOT=self.runtime
        self.module.PYTHON=sys.executable
        self.managed=managed
        self.lanes=lanes
        self.store=self.module.Store(self.root/'jobs')
        directory=self.store.root/'card-sample';directory.mkdir()
        self.turn=dict(id='t',kind='work',message='synthetic')
        session=dict(card_id='sample',engine='codex',cwd=str(directory),status='queued',
                     queue=[dict(self.turn)],title='synthetic',turn='old',started_at=None,last_activity=0,
                     pid=None,identity='',seen_artifacts=[],claude_lane='design',claude_config_dir='dedicated')
        with self.store.locked() as data:data['sessions']['sample']=session
        capacity=dict(total_workers=64,load_per_cpu=3,engines=dict(claude=4,sonnet=16))
        layout=dict(enabled=lanes,account2_ready=True,account3_ready=False,capacity=capacity)
        patches=[mock.patch.object(self.module.lanes,'topology',return_value=layout),
                 mock.patch.object(self.module.lanes,'enabled',return_value=lanes),
                 mock.patch.object(self.module.lanes,'dedicated',return_value=False),
                 mock.patch.object(self.module,'publish_live',side_effect=lambda *a,**k:self.out.append((a,k)) or True),
                 mock.patch.object(self.module.os,'getloadavg',return_value=(0,0,0))]
        if managed:
            patches += [mock.patch.object(self.module,'reconciler_enabled',return_value=True),
                        mock.patch.object(self.module,'admission_state',return_value=dict(cap=64)),
                        mock.patch.object(self.module,'can_admit',return_value=True),
                        mock.patch.object(self.module,'read_dispatch_policy',return_value={}),
                        mock.patch.object(self.store,'_initial_dispatch_permissions',return_value=set()),
                        mock.patch.object(self.store,'_flush_publications',return_value=None)]
        else:
            patches.append(mock.patch.object(self.module,'dispatch_paused',return_value=False))
        for patch in patches:patch.start();self.addCleanup(patch.stop)
        from scripts import shared_admission
        self.admission=shared_admission
        self.gate=shared_admission.Gate(self.root/'budget',sample=lambda:dict(
            cores=18,load=0,available_bytes=1024**3,total_bytes=64*1024**3))

    def tick(self):
        popen=subprocess.Popen
        def start(*a,**k):
            child=popen(*a,**k);self.children.append(child);return child
        with mock.patch.object(self.admission,'Gate',return_value=self.gate),mock.patch.object(self.module.subprocess,'Popen',side_effect=start):
            self.store.tick(**({'reconcile':True} if self.managed else {}))

    def test_pressure_refusal_restores_turn_and_drops_unstarted_managed_lease(self):
        self.load()
        with self.store.locked() as data:
            data['sessions']['sample']['queue'][0].update(automatic=True)
        # Exercise automatic retry without relying on a remote first-start query.
        with self.store.locked() as data:
            data['sessions']['sample']['queue'][0]['id']='reconciler-retry-t'
            data['sessions']['sample']['automatic_dispatch_count']=2
        self.tick()
        s=self.store.read()['sessions']['sample']
        self.assertEqual(s['status'],'queued')
        self.assertEqual(s['queue'][0]['id'],'reconciler-retry-t')
        self.assertEqual(s['admission_deferred']['reason'],'MemoryCapacity')
        self.assertEqual(s['automatic_dispatch_count'],2)
        self.assertFalse(self.marker.exists())
        for key in ('lease','lease_token','lease_expires_at','active_turn','active_veto_revision'):
            self.assertNotIn(key,s)
        self.assertEqual(s['claude_lane'],'design')
        self.assertEqual(s['claude_config_dir'],'dedicated')

    def test_legacy_lane_and_nonlane_dispatch_both_refuse_without_execution(self):
        for lanes in (True,False):
            with self.subTest(lanes=lanes):
                self.load(managed=False,lanes=lanes)
                self.tick()
                s=self.store.read()['sessions']['sample']
                self.assertEqual(s['queue'],[self.turn])
                self.assertEqual(s['admission_deferred']['reason'],'MemoryCapacity')
                self.assertNotIn('active_turn',s)
                self.assertFalse(self.marker.exists())
                # Use another store to keep each subcase independent.
                self.root=self.root/'next';self.root.mkdir()
                self.runtime=self.root/'runtime';self.runtime.mkdir()

    def test_admitted_managed_worker_pid_matches_model_lease_and_reservation(self):
        self.load()
        self.gate.sample=lambda:dict(cores=18,load=0,available_bytes=32*1024**3,total_bytes=64*1024**3)
        self.tick()
        self.reap()
        s=self.store.read()['sessions']['sample']
        self.assertTrue(self.marker.exists())
        self.assertEqual(s['status'],'running')
        self.assertEqual(s['lease']['pid'],s['pid'])
        self.assertEqual(s['lease']['identity'],s['identity'])
        leases=json.loads((self.root/'budget/leases.json').read_text())['leases']
        self.assertEqual(leases[0]['pgid'],s['pid'])
        self.assertEqual(s['queue'],[])

    def test_refused_review_rechecks_changed_artifact_before_any_second_spawn(self):
        self.load()
        with self.store.locked() as data:
            s=data['sessions']['sample'];s['queue'][0].update(kind='review',approval_id='a')
            s.update(review_session_id='prior-resume',review_claude_lane='research',review_claude_config_dir='dedicated')
            data['approvals']['a']=dict(id='a',card_id='sample',status='approved',kind='email',digest='safe',content='synthetic')
        def prepare(s,*a):s.update(active_claude_lane='research',active_claude_config_dir='dedicated',active_claude_managed=True)
        with mock.patch.object(self.module.lanes,'prepare',side_effect=prepare),mock.patch.object(self.module.lanes,'environment',side_effect=lambda s,e:e),mock.patch.object(self.module,'artifact',return_value=dict(digest='safe')):
            self.tick()
        s=self.store.read()['sessions']['sample']
        self.assertEqual(s['review_session_id'],'prior-resume')
        self.assertEqual(s['review_claude_lane'],'research')
        self.assertNotIn('reviewing',s)
        self.assertEqual(self.store.read()['approvals']['a']['status'],'approved')
        with mock.patch.object(self.module,'artifact',return_value=dict(digest='changed')):
            self.tick()
        s=self.store.read()['sessions']['sample']
        self.assertEqual(s['queue'],[])
        self.assertEqual(s['artifact_error'],'approved artifact changed, fresh approval required')
        self.assertFalse(self.marker.exists())

    def test_missing_cwd_fails_one_managed_session_and_later_work_still_starts(self):
        self.load()
        self.gate.sample=lambda:dict(cores=18,load=0,available_bytes=32*1024**3,total_bytes=64*1024**3)
        directory=self.store.root/'card-next';directory.mkdir()
        with self.store.locked() as data:
            first=data['sessions']['sample']
            data['sessions']['next']=dict(first,card_id='next',cwd=str(directory),queue=[dict(id='next',kind='work',message='synthetic')])
            first['cwd']=str(self.root/'missing')
        self.tick();self.reap()
        data=self.store.read()
        self.assertEqual(data['sessions']['sample']['status'],'failed')
        self.assertEqual(data['sessions']['sample']['failure_kind'],'start_failure')
        self.assertEqual(data['sessions']['next']['status'],'running')
        self.assertTrue((directory/'next.ran').exists())

    def test_aged_managed_deferral_queues_blocked_status_without_needs_you(self):
        self.load()
        with self.store.locked() as data:
            data['sessions']['sample']['admission_deferred']=dict(turn='t',since=1,count=2,alerted=False)
        self.tick()
        publications=list(self.store.read().get('publications',{}).values())
        self.assertEqual(len(publications),1)
        self.assertEqual(publications[0]['state'],'blocked')
        self.assertEqual(publications[0]['kwargs']['section'],'up_next')
        self.assertNotIn('needs_you',json.dumps(publications))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',required=True,type=Path)
    args,remaining=parser.parse_known_args()
    SOURCE=args.runtime_root.resolve()
    sys.path.insert(0,str(SOURCE))
    unittest.main(argv=[sys.argv[0],*remaining])
