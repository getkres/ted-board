"""Synthetic dispatch surface for the public patch harness."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from board_client import BoardConflict, BoardGone, call
from live_status import instructions, publish_live

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def atomic(path, data):
 Path(path).write_text(json.dumps(data))


def identity(pid):
 return str(pid)


class Store:
 def __init__(self, root):
  self.root=Path(root);self.root.mkdir(parents=True);self.path=self.root/'sessions.json'
 @contextlib.contextmanager
 def locked(self):
  data=json.loads(self.path.read_text()) if self.path.exists() else dict(sessions={},approvals={})
  yield data
  atomic(self.path,data)
 def read(self):
  return json.loads(self.path.read_text())
 def _out(self,*args):
  pass
 def tick(self):
  with self.locked() as data:
   for s in data['sessions'].values():
    turn=s['queue'][0]
    if turn['kind']=='review':
     a=data['approvals'][turn['approval_id']]
     s['reviewing']=a['id'];s['review_context']='synthetic';a.update(status='reviewing')
    s['queue'].pop(0);s['turn']=turn['id']
    if turn.get('veto_proposal_id'):s['active_veto_revision']=turn['veto_card_revision']
    prefix=Path(s['cwd'])/s['turn'];env=dict(os.environ)
    try:
     with open(str(prefix)+'.log','a') as log:
      os.chmod(log.name,0o600)
      p=subprocess.Popen([PYTHON,str(ROOT/'session_worker.py'),str(prefix)],cwd=s['cwd'],env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
     s.update(pid=p.pid,identity=identity(p.pid),status='running')
     publish_live(s['card_id'],'running','synthetic',section='ted_doing')
    except OSError:
     s.update(status='failed',pid=None);self._out(data,s,'Worker could not start. Reply to retry.',s['turn'])
