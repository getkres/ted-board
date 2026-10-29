#!/usr/bin/env python3
"""Exercise current lane and managed adapters without provider or live state access."""
import ast
import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def adapter():
    spec = importlib.util.spec_from_file_location('prepare_shared_admission', HERE / 'prepare_shared_admission.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Synthetic statement surfaces only. Actual private runtimes are validated separately.
LEGACY = '''import uuid
class Store:
 def _tick_lanes(self,layout):
  with self.locked() as data:
   overloaded=os.getloadavg()[0]>capacity['load_per_cpu']*(os.cpu_count() or 8)
   for s in data['sessions'].values():
    if running>=capacity['total_workers'] or overloaded:break
    turn=s['queue'][0]
    prefix=Path(s['cwd'])/s['turn']
    Path(str(prefix)+'.result.json').unlink(missing_ok=True)
    atomic(str(prefix)+'.input.json',dict(session=s,prompt=turn['message'],review=turn['kind']=='review',veto_proposal_id=turn.get('veto_proposal_id')))
    env=lanes.environment(s,env)
    try:
     with open(str(prefix)+'.log','a') as log:
      os.chmod(log.name,0o600)
      p=subprocess.Popen([PYTHON,str(ROOT/'session_worker.py'),str(prefix)],cwd=s['cwd'],env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
     s.update(pid=p.pid,identity=identity(p.pid),status='running',started_at=time.time(),last_activity=time.time())
    except OSError:
     s.update(status='failed',pid=None);self._worker_failure(data,s,'start_failure');self._publish_failure(s)
'''
MANAGED = '''import uuid
class Store:
 def tick(self,reconcile=False):
  managed=True
  with self.locked() as data:
   for s in pending:
    turn=s['queue'][0]
    prefix=Path(s['cwd'])/s['turn']
    Path(str(prefix)+'.result.json').unlink(missing_ok=True)
    atomic(str(prefix)+'.input.json',dict(session=s,prompt=turn['message'],review=turn['kind']=='review',veto_proposal_id=turn.get('veto_proposal_id')))
    env=lanes.environment(s,env)
    launches+=1;retry_launches+=retrying
    if automatic:s['automatic_dispatch_count']=int(s.get('automatic_dispatch_count') or 0)+1
    try:
     with open(str(prefix)+'.log','a') as log:
      os.chmod(log.name,0o600)
      p=subprocess.Popen([PYTHON,str(ROOT/'reconciler_worker.py'),str(prefix)],cwd=s['cwd'],env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
     s.update(pid=p.pid,identity=identity(p.pid),status='running',started_at=time.time(),last_activity=time.time())
     if managed:s['lease'].update(pid=s['pid'],identity=s['identity'])
    except OSError:
     s.update(status='failed',pid=None);self._worker_failure(data,s,'start_failure');self._publish_failure(s,data if managed else None)
'''

MANAGED += """
 def _flush_publications(self):
  with self.locked() as lock:
   for cid,item in pending.items():
    with self.locked() as data:
     s=data['sessions'][cid]
     current=data['publications'].get(cid,{})
     valid=not s.get('stop_requested') and current.get('id')==item['id'] and all(s.get(key)==item.get(key) for key in ('turn','lease_token','status'))
     if valid and item['state']=='running':
      valid=True
     if not valid:
      if current.get('id')==item['id']:data['publications'].pop(cid,None)
      continue
    try:confirmed=publish_live(cid,item['state'],item['line'],raise_gone=True,**item['kwargs'])
    except RuntimeError:confirmed=False
    if not confirmed:continue
    with self.locked() as data:
     if current.get('id')!=item['id']:continue
     data['publications'].pop(cid,None)
     if item['kind']=='failure':s.pop('failure_publish_pending',None);s['recovery_section']='up_next'
     elif item['kind'] in ('start','resume'):s.pop('recovery_section',None)
 def _publish_failure(self,s,data=None):
  pass
"""


COMPANY = '''import uuid
import sys
from pathlib import Path
import subprocess

def stop_group(process):
    pass

def execute(argv, cwd, timeout, stdout, stderr, env=None, on_start=None, heartbeat=None):
    with open(stdout, 'wb') as out, open(stderr, 'wb') as err:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True)

def run_task(store, task_id, owner, argv, timeout=120, env=None, validator=None, input_messages=None, stream=False):
    try:
        code = execute(argv, 'fixture', timeout, 'out', 'err', env,
                       on_start=lambda pid: store.start(task_id, token, pid),
                       heartbeat=lambda: store.renew(task_id, token, 30))
    except Exception as exc:
        return store.fail(task_id, token, 'failed', 1, str(exc) + '; evidence: ' + str(folder))

def _run_opus(store, task_id, repo, timeout):
    result = run_task(store, task_id, 'opus', command, timeout, env,
                      validate_opus, [m['id'] for m in incoming], stream=active)
    return result

def main():
        print(json.dumps(result, indent=2))
        if isinstance(result, dict):
            return 0
'''


class AdapterTests(unittest.TestCase):
    def publication_store(self, session, current=None):
        """Execute the generated publisher, with only storage and I/O isolated."""
        item=dict(id='old',card_id='sample',turn='old',lease_token='lease',status='done',
                  state='blocked',line='ted review',kind='complete',kwargs={'section':'up_next'})
        data=dict(sessions={'sample':session},publications={'sample':current or dict(item)},approvals={})
        source=adapter().adapt(MANAGED,managed=True)
        cls=next(node for node in ast.parse(source).body if isinstance(node,ast.ClassDef))
        cls.body=[node for node in cls.body if node.name in ('_flush_publications','_completion_eligible')]
        namespace=dict(json=json,pending={'sample':item},publish_live=lambda *a,**k:self.fail('unexpected provider write'))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'generated-publisher','exec'),namespace)
        store=namespace['Store']()
        @contextlib.contextmanager
        def locked():
            yield data
        store.locked=locked
        return store,data,item

    def test_obsolete_completion_is_discarded_before_provider_access(self):
        session=dict(card_id='sample',turn='new',lease_token='lease',status='done',queue=[],pid=None)
        store,data,_=self.publication_store(session)
        store._flush_publications()
        self.assertEqual(data['publications'],{})
        self.assertEqual(data['sessions']['sample']['turn'],'new')

    def test_current_completion_with_unfinished_work_remains_pending(self):
        session=dict(card_id='sample',turn='old',lease_token='lease',status='done',queue=[{'id':'next'}],pid=None)
        store,data,item=self.publication_store(session)
        store._flush_publications()
        self.assertEqual(data['publications'],{'sample':item})

    def test_stop_hold_with_matching_completion_fence_remains_pending(self):
        session=dict(card_id='sample',turn='old',lease_token='lease',status='done',queue=[],pid=None,stop_requested=True)
        store,data,item=self.publication_store(session)
        store._flush_publications()
        self.assertEqual(data['publications'],{'sample':item})

    def test_status_change_alone_keeps_unresolved_completion_pending(self):
        session=dict(card_id='sample',turn='old',lease_token='lease',status='queued',queue=[],pid=None)
        store,data,item=self.publication_store(session)
        store._flush_publications()
        self.assertEqual(data['publications'],{'sample':item})

    def test_stale_snapshot_cannot_discard_replacement_publication(self):
        session=dict(card_id='sample',turn='new',lease_token='lease',status='done',queue=[],pid=None)
        replacement=dict(id='new',turn='new',kind='complete')
        store,data,_=self.publication_store(session,replacement)
        store._flush_publications()
        self.assertEqual(data['publications'],{'sample':replacement})

    def test_lane_source_preserves_environment_and_routes_spawn(self):
        result = adapter().adapt(LEGACY, managed=False)
        ast.parse(result)
        self.assertIn('env=lanes.environment(s,env)', result)
        self.assertIn("p=shared_admission.Gate().spawn(", result)
        self.assertNotIn('or overloaded:break', result)
        self.assertIn("guards=admission_status_kwargs", result)
        self.assertIn('except shared_admission.Deferred as exc:', result)
        self.assertLess(result.index('    try:'), result.index("    atomic(str(prefix)"))

    def test_managed_source_preserves_lease_handshake_and_counts_only_success(self):
        result = adapter().adapt(MANAGED, managed=True)
        ast.parse(result)
        self.assertIn("if managed:s['lease'].update(pid=s['pid'],identity=s['identity'])", result)
        self.assertLess(result.index('p=shared_admission.Gate().spawn'), result.index('launches+=1;retry_launches+=retrying'))
        self.assertIn("self._queue_publication(data,s,'blocked'", result)
        self.assertIn("'admission',section='up_next'", result)
        self.assertLess(result.index('    try:'), result.index("    atomic(str(prefix)"))

    def test_completion_fallback_is_managed_only_and_refuses_changed_surfaces(self):
        result=adapter().adapt(MANAGED,managed=True)
        self.assertIn('def _completion_target_exists(',result)
        self.assertIn('completion_snapshot',result)
        self.assertIn("current!=item",result)
        self.assertNotIn('def _completion_target_exists(',adapter().adapt(LEGACY,managed=False))
        with self.assertRaises(ValueError):
            adapter().adapt(MANAGED.replace('    if not confirmed:continue','    if not confirmed:break'),managed=True)

    def test_combined_legacy_prefix_input_line_is_also_protected(self):
        source = LEGACY.replace("    prefix=Path(s['cwd'])/s['turn']\n", "").replace(
            "    atomic(str(prefix)", "    prefix=Path(s['cwd'])/s['turn'];atomic(str(prefix)")
        result = adapter().adapt(source, managed=False)
        self.assertLess(result.index('    try:'), result.index("     atomic(str(prefix)"))

    def test_company_adapter_gates_inner_group_and_preserves_outer_status(self):
        result = adapter().adapt_company(COMPANY)
        ast.parse(result)
        self.assertIn('launch = model_spawn if model_admission else subprocess.Popen', result)
        self.assertIn('model_admission=True', result)
        self.assertIn('return 75', result)
        self.assertIn("task['pid'] is not None", result)
        self.assertIn("('running',)", result)
        with self.assertRaises(ValueError):adapter().adapt_company(result)
        with self.assertRaises(ValueError):adapter().adapt_company(COMPANY.replace('stream=active)','stream=False)'))

    def test_unknown_or_already_adapted_source_is_refused(self):
        with self.assertRaises(ValueError):
            adapter().adapt('import uuid\n', managed=True)
        result = adapter().adapt(LEGACY, managed=False)
        with self.assertRaises(ValueError):
            adapter().adapt(result, managed=False)


if __name__ == '__main__':
    unittest.main()
