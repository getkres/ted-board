"""Offline pause tests. Private integration uses the exact current runtime candidate."""
import contextlib
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
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
TEMP=tempfile.TemporaryDirectory(prefix='legacy-pause-')
ROOT=Path(os.environ.get('TED_LEGACY_PAUSE_RUNTIME',TEMP.name))
if 'TED_LEGACY_PAUSE_RUNTIME' not in os.environ:
 subprocess.run(['patch','-s','-p0','-i',str(HERE/'legacy-dispatch-pause-helper.patch')],cwd=ROOT,check=True,capture_output=True)
sys.path.insert(0,str(ROOT))
import dispatch_pause

def load(path,name,deps):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
 with patch.dict(sys.modules,deps):spec.loader.exec_module(module)
 return module

class Marker(unittest.TestCase):
 def test_absence_and_explicit_false_preserve_admission(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'pause.json'
   self.assertFalse(dispatch_pause.paused(path))
   path.write_text('{"paused":false}');self.assertFalse(dispatch_pause.paused(path))
   path.write_text('{"paused":true}');self.assertTrue(dispatch_pause.paused(path))
 def test_invalid_or_symlink_marker_fails_closed(self):
  with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stderr(io.StringIO()):
   path=Path(temp)/'pause.json'
   for text in ('{','[]','{}','{"paused":"false"}','{"paused":false,"unknown":true}'):
    path.write_text(text);self.assertTrue(dispatch_pause.paused(path),text)
   path.unlink();path.symlink_to(Path(temp)/'missing');self.assertTrue(dispatch_pause.paused(path))

@unittest.skipUnless((ROOT/'sessions.py').is_file(),'exact private runtime required')
class Integration(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.jobs=Path(self.temp.name);self.marker=self.jobs/'dispatch-pause.json';self.marker.write_text('{"paused":true}')
  mode=patch.object(dispatch_pause,'PAUSE_PATH',self.marker);mode.start();self.addCleanup(mode.stop)
  client=types.SimpleNamespace(BoardConflict=RuntimeError,BoardGone=LookupError,call=Mock(return_value=dict(ok=True)))
  live=types.SimpleNamespace(instructions=lambda cid:'fixture',publish_live=Mock(return_value=True))
  self.sessions=load(ROOT/'sessions.py','pause_sessions',{'board_client':client,'live_status':live})
  self.store=self.sessions.Store(self.jobs)
  topology=patch.object(self.sessions.lanes,'topology',return_value=dict(enabled=False));topology.start();self.addCleanup(topology.stop)
 def enqueue(self,cid):
  self.store.enqueue(dict(id=cid,title='Fixture',project='Fixture'),'work',cid,engine='codex')
 def test_completed_result_settles_and_running_worker_survives_without_any_start(self):
  self.enqueue('finished');self.enqueue('queued');self.enqueue('running')
  with self.store.locked() as data:
   for cid,pid in (('finished',123),('running',124)):
    s=data['sessions'][cid];turn=s['queue'].pop(0);s.update(status='running',turn=turn['id'],pid=pid,identity='fixture')
   s=data['sessions']['finished'];Path(s['cwd'],s['turn']+'.result.json').write_text(json.dumps(dict(ok=True,text='saved output',session_id='thread')))
  with patch.object(self.sessions,'alive',side_effect=lambda pid,*args:pid==124),patch.object(self.sessions.subprocess,'Popen',side_effect=AssertionError('paused admission spawned')),patch.object(self.sessions,'safe_kill',side_effect=AssertionError('pause signalled worker')):
   self.store.tick()
  data=self.store.read();self.assertEqual(data['sessions']['finished']['status'],'done');self.assertIsNone(data['sessions']['finished']['pid'])
  self.assertEqual(data['sessions']['queued']['status'],'queued');self.assertEqual(len(data['sessions']['queued']['queue']),1)
  self.assertEqual(data['sessions']['running']['status'],'running');self.assertEqual(data['sessions']['running']['pid'],124)
  self.assertEqual(data['outbox'][0]['text'],'saved output')
 def test_lane_path_also_settles_results_without_new_starts(self):
  layout=dict(enabled=True,account2_ready=False,account3_ready=False)
  with patch.object(self.sessions.lanes,'topology',return_value=layout),patch.object(self.sessions.lanes,'capacity',return_value=dict(total_workers=64,load_per_cpu=3,engines=dict(claude=2,sonnet=8))):
   self.test_completed_result_settles_and_running_worker_survives_without_any_start()
 def test_absent_pause_resumes_the_existing_legacy_dispatch(self):
  self.enqueue('queued');self.marker.unlink()
  with patch.object(self.sessions.os,'getloadavg',return_value=(0,0,0)),patch.object(self.sessions,'identity',return_value='fixture'),patch.object(self.sessions.subprocess,'Popen',return_value=types.SimpleNamespace(pid=123)) as spawn:
   self.store.tick()
  self.assertEqual(spawn.call_count,1);self.assertEqual(self.store.read()['sessions']['queued']['status'],'running')
 def test_direct_card_create_uses_the_same_paused_tick(self):
  sync=types.SimpleNamespace(ENDPOINT='https://fixture.invalid',load_env=lambda:dict(TED_DECISIONS_WORKER_KEY='fixture'))
  client=types.SimpleNamespace(call=Mock(),cards=lambda:[],resolve_rule=Mock())
  front=load(ROOT/'card.py','pause_card',{'board_client':client,'sessions':self.sessions,'sync':sync})
  front.Store=lambda:self.store
  response=io.BytesIO(b'{"ok":true}')
  with patch.object(front.urllib.request,'urlopen',return_value=response),patch.object(self.sessions.subprocess,'Popen',side_effect=AssertionError('direct caller bypassed pause')):
   self.assertEqual(front.create('Fixture','Fixture','work',engine='codex',card_id='direct'),'direct')
  self.assertEqual(self.store.read()['sessions']['direct']['status'],'queued')

if __name__=='__main__':unittest.main()
