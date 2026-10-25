#!/usr/bin/env python3
"""Build an uninstalled private candidate. Reads runtime sources, never executes them."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--hourly-skill',type=Path,required=True);p.add_argument('--steward-source',type=Path,required=True)
 a=p.parse_args()
 a.baseline=a.baseline.resolve();a.output=a.output.absolute();a.hourly_skill=a.hourly_skill.resolve();a.steward_source=a.steward_source.absolute()
 here=Path(__file__).resolve().parent
 manifest=json.loads((here/'reconciler-manifest.json').read_text())
 if a.output.exists():p.error('output must be a new private directory')
 dependencies=here/'reconciler-baseline-dependencies.json'
 if not dependencies.is_file():p.error('baseline dependency manifest is missing')
 for relative,expected in json.loads(dependencies.read_text()).items():
  source=a.baseline/relative
  if source.is_symlink() or not source.is_file() or sha(source)!=expected:p.error('baseline dependency changed for '+relative+', rebase and rerun review')
 sources={}
 baselines={}
 for name,row in manifest.items():
  source=row.get('source',name)
  if row.get('baseline_sha256'):
   path=a.baseline/source
   if source=='hourly-SKILL.md':path=a.hourly_skill
   elif source=='inbox_steward.py':path=a.steward_source
   elif source=='handler.ts':path=a.baseline/'supabase/functions/ted-board/handler.ts'
   sources[name]=path;baselines[source]=path
 for name,source in sources.items():
  if source.is_symlink() or not source.is_file() or sha(source)!=manifest[name]['baseline_sha256']:p.error('baseline changed for '+name+', rebase and rerun review')
 a.output.mkdir(parents=True,mode=0o700)
 archive=a.output/'legacy-baseline';archive.mkdir(mode=0o700)
 for name,path in baselines.items():shutil.copyfile(path,archive/name);(archive/name).chmod(0o600)
 for name,row in manifest.items():
  folder=a.output/'backend' if name.endswith('.ts') else a.output;folder.mkdir(exist_ok=True)
  target=folder/name
  if name in sources:shutil.copyfile(sources[name],target)
  command=['patch','--batch','--fuzz=0','-s']+([str(target)] if name in sources else ['-p0'])+['-i',str(here/row['patch'])]
  subprocess.run(command,cwd=folder,check=True,capture_output=True)
  target.chmod(0o600)
  if sha(target)!=row['candidate_sha256']:raise RuntimeError('candidate checksum mismatch for '+name)
 # Unchanged private adapters and backend siblings support offline integration tests.
 for name in ('board_client.py','sync.py','mockup_client.py','board_reply.py'):
  source=a.baseline/name
  if source.is_file():shutil.copyfile(source,a.output/name);(a.output/name).chmod(0o600)
 for source in (a.baseline/'supabase/functions/ted-board').iterdir():
  if source.is_file() and source.suffix in ('.ts','.json') and source.name!='handler.ts':
   shutil.copyfile(source,a.output/'backend'/source.name)
 shutil.copyfile(here.parent/'backend-integration/reconciliation.ts',a.output/'backend/reconciliation.ts')
 shutil.copyfile(a.output/'legacy-baseline/handler.ts',a.output/'backend/legacy-handler-baseline.ts')
 print('private candidate reconstructed and checksums verified; nothing installed')

if __name__=='__main__':main()
