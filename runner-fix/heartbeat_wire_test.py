"""Heartbeat wire compatibility, with no real transport or worker execution."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
CANDIDATE=Path(os.environ['RECONCILER_CANDIDATE']).resolve() if os.environ.get('RECONCILER_CANDIDATE') else None
DENO=os.environ.get('DENO',str(Path.home()/'.deno/bin/deno'))


def apply_patch_file(path, destination, patch_file):
    shutil.copyfile(path,destination)
    subprocess.run(['patch','--batch','--fuzz=0','-s',str(destination),'-i',str(patch_file)],check=True,capture_output=True)


@unittest.skipUnless(CANDIDATE,'private heartbeat baseline required')
class HeartbeatEntrypoints(unittest.TestCase):
    def test_legacy_flag_off_projects_new_terminal_states_without_rewriting_ledger(self):
        self.check_entrypoint('reconciler-jobs_heartbeat.patch','legacy')

    def test_managed_projects_new_terminal_states_without_rewriting_ledger(self):
        self.check_entrypoint('reconciler-managed-heartbeat.patch','managed')

    def test_legacy_lanes_snapshot_projects_new_terminal_states_without_rewriting_ledger(self):
        self.check_entrypoint('reconciler-jobs_heartbeat.patch','legacy',lanes_on=True)

    def check_entrypoint(self,patch_name,mode,lanes_on=False):
        # Removing the wire projection is a bug: the real heartbeat then exits
        # unsuccessfully when the transport validates the retained local states.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'heartbeat.py'
            apply_patch_file(CANDIDATE/'legacy-baseline/jobs_heartbeat.py',source,HERE/patch_name)
            helper_patch=HERE/'reconciler-heartbeat-wire.patch'
            if helper_patch.exists():
                subprocess.run(['patch','--batch','--fuzz=0','-s','-p0','-i',str(helper_patch)],cwd=root,check=True,capture_output=True)
            rows={state:dict(id='fixture-'+state,card_id='fixture-'+state,title='Fixture',engine='claude',status=state,last_line='Stored status remains truthful',queue=[],pid=None) for state in ('dead_letter','stopped','running')}
            ledger_root=root/'ledger';ledger_root.mkdir();ledger=ledger_root/'sessions.json'
            approval=dict(id='fixture-approval',card_id='fixture-running',status='pending',kind='db',summary='Fixture decision',content='Fixture SQL packet',digest='a'*64)
            ledger.write_text(json.dumps(dict(sessions=rows,approvals={'fixture-approval':approval},receipts=[],outbox=[],commands=[]),indent=2));before=ledger.read_bytes()
            sent=[]
            validator = """
const {frontdoor}=await import(FRONTDOOR);
const body=await new Response(Deno.stdin.readable).json();
let rpc;
try { await frontdoor({rpc:(name,args)=>{rpc={name,args};return Promise.resolve({data:{ok:true},error:null})}},body);console.log(JSON.stringify({accepted:true,rpc})); }
catch { console.log(JSON.stringify({accepted:false})); }
""".replace('FRONTDOOR',json.dumps((CANDIDATE/'backend/frontdoor.ts').as_uri()))
            def transport(action=None,**body):
                if action=='control':return {'commands':[]}
                if action=='veto_clear_due':return {'ok':True,'cleared':[]}
                if action=='heartbeat':
                    reply=subprocess.run([DENO,'eval','--no-check',validator],input=json.dumps(dict(body,action=action)).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
                    result=json.loads(reply.stdout)
                    if not result['accepted']:raise RuntimeError('Actual frontdoor rejected heartbeat')
                    sent.append(result['rpc']);return {'ok':True}
                raise AssertionError('Unexpected transport action')
            client=types.SimpleNamespace(BoardConflict=RuntimeError,BoardGone=LookupError,call=transport,cards=lambda:[{'id':v['card_id']} for v in rows.values()])
            live=types.SimpleNamespace(instructions=lambda _: 'Fixture',publish_live=lambda *a,**k:True)
            lanes=types.SimpleNamespace(enabled=lambda:lanes_on,summaries=lambda _:[],execution_engine=lambda _:'claude')
            gate=types.SimpleNamespace(reconciler_enabled=lambda:False,read_dispatch_policy=lambda *a,**k:{})
            snapshot_source=CANDIDATE/('reconciler_sessions.py' if mode=='managed' else 'sessions.py')
            sspec=importlib.util.spec_from_file_location('snapshot_'+mode,snapshot_source);snapshot_module=importlib.util.module_from_spec(sspec)
            raw_deps={'board_client':client,'live_status':live,'claude_lanes':lanes,'reconciler_gate':gate}
            with patch.dict(sys.modules,raw_deps),patch.object(sys,'path',[str(CANDIDATE)]+sys.path),patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'false'}):
                sspec.loader.exec_module(snapshot_module)
                raw_store=snapshot_module.Store(ledger_root)
                raw_jobs,raw_approvals=raw_store.snapshot()
            self.assertEqual([j['status'] for j in raw_jobs],['dead_letter','stopped','running'])
            class FixtureStore:
                def controls(self,*a):pass
                def tick(self):pass
                def collect_approvals(self):pass
                def sync_approval_status(self):pass
                def flush(self):pass
                def snapshot(self):return raw_jobs,raw_approvals
            session=types.SimpleNamespace(Store=FixtureStore,identity=lambda pid:'fixture')
            fresh=types.SimpleNamespace(dispatch=lambda:None,health_job=lambda:dict(id='fixture-health',card_id=None,title='Fixture health',engine='claude',status='idle',last_line='Healthy'))
            spec=importlib.util.spec_from_file_location('heartbeat_'+mode,source);module=importlib.util.module_from_spec(spec)
            deps={'board_client':client,'sessions':session,'reconciler_sessions':session,'fresh_ted':fresh,'reconciler_gate':gate}
            with patch.dict(sys.modules,deps),patch.object(sys,'path',[str(root)]+sys.path),patch.dict(os.environ,{'TED_RECONCILER_ENABLED':'false'}):
                sys.modules.pop('heartbeat_wire',None)
                spec.loader.exec_module(module)
                with patch.object(module,'untracked',return_value=[]),contextlib.redirect_stdout(io.StringIO()):
                    try: code=module.main()
                    except RuntimeError: code=1
            self.assertEqual(code,0,'retained terminal states must not break heartbeat')
            self.assertEqual(sent[0]['name'],'ted_board_heartbeat')
            self.assertEqual([j['status'] for j in sent[0]['args']['p_jobs']],['failed','failed','running','idle'])
            self.assertEqual(sent[0]['args']['p_approvals'],raw_approvals)
            self.assertEqual([j['status'] for j in raw_jobs[:3]],['dead_letter','stopped','running'])
            self.assertEqual(ledger.read_bytes(),before)

    def test_legacy_route_remains_exactly_removable(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'heartbeat.py';baseline=CANDIDATE/'legacy-baseline/jobs_heartbeat.py'
            apply_patch_file(baseline,target,HERE/'reconciler-jobs_heartbeat.patch')
            block=rb'^# BEGIN RECONCILER ROUTE\n.*?^# END RECONCILER ROUTE\n'
            self.assertEqual(re.sub(block,b'',target.read_bytes(),flags=re.M|re.S),baseline.read_bytes())


class HeartbeatWireProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
        subprocess.run(['patch','--batch','--fuzz=0','-s','-p0','-i',str(HERE/'reconciler-heartbeat-wire.patch')],cwd=root,check=True,capture_output=True)
        spec=importlib.util.spec_from_file_location('wire_projection_fixture',root/'heartbeat_wire.py');cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_all_older_status_payloads_keep_values_and_object_identity(self):
        jobs=[dict(id=state,status=state) for state in ('idle','queued','running','waiting_approval','done','failed','untracked')]
        result=self.module.heartbeat_transport(lambda *args,**body:body)('heartbeat',jobs=jobs,approvals=[])
        self.assertIs(result['jobs'],jobs)
        self.assertEqual([j['status'] for j in result['jobs']],['idle','queued','running','waiting_approval','done','failed','untracked'])

    def test_projection_preserves_input_rows_and_decision_payloads(self):
        jobs=[dict(id='held',status='dead_letter',last_line='Truthful failure',metadata={'retry_count':3}),dict(id='stop',status='stopped')]
        original=copy.deepcopy(jobs);approvals=[dict(id='decision',status='dead_letter',content='Exact decision')]
        result=self.module.heartbeat_transport(lambda *args,**body:body)(action='heartbeat',jobs=jobs,approvals=approvals)
        self.assertEqual(result['jobs'],[dict(id='held',status='failed',last_line='Truthful failure',metadata={'retry_count':3}),dict(id='stop',status='failed')])
        self.assertEqual(jobs,original);self.assertIs(result['approvals'],approvals)

    def test_other_actions_keep_exact_arguments_and_response(self):
        jobs=[dict(status='dead_letter')];response=object();observed=[]
        def transport(*args,**body):observed.append((args,body));return response
        send=self.module.heartbeat_transport(transport)
        self.assertIs(send('approval_result',True,status='stopped',jobs=jobs),response)
        self.assertEqual(observed[0][0],('approval_result',True));self.assertIs(observed[0][1]['jobs'],jobs);self.assertEqual(observed[0][1]['status'],'stopped')

    def test_unknown_status_and_malformed_jobs_are_not_silently_normalized(self):
        for jobs in ([dict(status='unexpected')],[None],{'status':'dead_letter'},None):
            result=self.module.heartbeat_transport(lambda *args,**body:body)('heartbeat',jobs=jobs)
            self.assertIs(result['jobs'],jobs)

    def test_transport_failures_propagate_without_mutating_inputs(self):
        jobs=[dict(status='dead_letter')]
        def fail(*args,**kwargs):raise RuntimeError('Transport unavailable')
        with self.assertRaisesRegex(RuntimeError,'Transport unavailable'):
            self.module.heartbeat_transport(fail)('heartbeat',jobs=jobs)
        self.assertEqual(jobs,[dict(status='dead_letter')])


if __name__=='__main__':unittest.main()
