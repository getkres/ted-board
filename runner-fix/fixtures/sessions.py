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
 def _out(self,data,s,text,token):
  data.setdefault('outbox',[]).append(dict(card_id=s['card_id'],text=text,token=token))
 def tick(self):
  with self.locked() as data:
   running=sum(s['status']=='running' for s in data['sessions'].values())
   claude_running=0;sonnet_running=0
   overloaded=os.getloadavg()[0]>2*(os.cpu_count() or 8)
   for s in data['sessions'].values():
    if running>=64 or overloaded:break
    if s['status']=='running' or not s['queue']:continue
    turn=s['queue'][0]
    if turn['kind']=='review':
     a=data['approvals'][turn['approval_id']]
     s['reviewing']=a['id'];s['review_context']='synthetic';a.update(status='reviewing')
    s['queue'].pop(0);s['turn']=turn['id']
    if turn.get('veto_proposal_id'):s['active_veto_revision']=turn['veto_card_revision']
    prefix=Path(s['cwd'])/s['turn'];atomic(str(prefix)+'.input.json',dict(session=s,prompt=turn['message'],review=turn['kind']=='review',veto_proposal_id=turn.get('veto_proposal_id')))
    env=dict(os.environ)
    try:
     with open(str(prefix)+'.log','a') as log:
      os.chmod(log.name,0o600)
      p=subprocess.Popen([PYTHON,str(ROOT/'session_worker.py'),str(prefix)],cwd=s['cwd'],env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
     s.update(pid=p.pid,identity=identity(p.pid),status='running',started_at=time.time(),last_activity=time.time());running+=1;claude_running+=s.get('engine')=='claude';sonnet_running+=s.get('engine')=='sonnet'
     publish_live(s['card_id'],'running','synthetic',section='ted_doing')
    except OSError:
     s.update(status='failed',pid=None);self._out(data,s,'Worker could not start. Reply to retry.',s['turn'])
