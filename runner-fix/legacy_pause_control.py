"""Explicit local pause and exact-state restore, synchronized with Store.tick."""
import argparse
import base64
import contextlib
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

PAUSED=b'{"paused":true}\n'

@contextlib.contextmanager
def locked(root):
 jobs=Path(root).resolve()/'jobs'
 if not jobs.is_dir():raise ValueError('jobs directory missing')
 with (jobs/'.sessions.lock').open('a') as lock:
  os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
  yield jobs/'dispatch-pause.json'

def regular(path):
 try:mode=path.lstat().st_mode
 except FileNotFoundError:return False
 if not stat.S_ISREG(mode):raise ValueError('Marker must be a regular file or absent')
 return True

def replace(path,content,mode):
 fd,name=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as stream:
   os.fchmod(stream.fileno(),mode);stream.write(content);stream.flush();os.fsync(stream.fileno())
  os.replace(name,path)
 finally:
  Path(name).unlink(missing_ok=True)

def pause(root,backup):
 root=Path(root).resolve();backup=Path(backup)
 with locked(root) as marker:
  exists=regular(marker)
  saved=dict(version=1,root=str(root),exists=exists,mode=(marker.stat().st_mode&0o777) if exists else None,content=base64.b64encode(marker.read_bytes()).decode() if exists else None)
  try:
   fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  except FileExistsError:raise ValueError('Backup already exists')
  with os.fdopen(fd,'w') as stream:
   json.dump(saved,stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())
  replace(marker,PAUSED,0o600)

def restore(root,backup):
 root=Path(root).resolve();saved=json.loads(Path(backup).read_text())
 if saved.get('version')!=1 or saved.get('root')!=str(root) or type(saved.get('exists')) is not bool:raise ValueError('Backup identity mismatch')
 if saved['exists']:
  if type(saved.get('mode')) is not int or not 0<=saved['mode']<=0o777:raise ValueError('Invalid backup mode')
  content=base64.b64decode(saved['content'],validate=True)
 with locked(root) as marker:
  if not regular(marker) or marker.read_bytes()!=PAUSED:raise ValueError('Current marker changed; restore refused')
  if saved['exists']:replace(marker,content,saved['mode'])
  else:marker.unlink()

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('action',choices=['pause','restore'])
 parser.add_argument('--root',type=Path,required=True)
 parser.add_argument('--backup',type=Path,required=True)
 args=parser.parse_args()
 try:globals()[args.action](args.root,args.backup)
 except (OSError,ValueError,KeyError,TypeError) as exc:raise SystemExit(str(exc))
 print('Admission paused; running workers and result consumption remain active.' if args.action=='pause' else 'Original admission marker state restored.')
if __name__=='__main__':main()
