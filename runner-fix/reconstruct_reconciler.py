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
 sources={name:a.baseline/name for name,row in manifest.items() if row.get('baseline_sha256')}
 sources.update({'hourly-SKILL.md':a.hourly_skill,'inbox_steward.py':a.steward_source,'handler.ts':a.baseline/'supabase/functions/ted-board/handler.ts'})
 for name,source in sources.items():
  if source.is_symlink() or not source.is_file() or sha(source)!=manifest[name]['baseline_sha256']:p.error('baseline changed for '+name+', rebase and rerun review')
 a.output.mkdir(parents=True,mode=0o700)
 for name,row in manifest.items():
  folder=a.output/'backend' if name=='handler.ts' else a.output;folder.mkdir(exist_ok=True)
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
 for source in (a.baseline/'supabase/functions/ted-board').glob('*.ts'):
  if source.name!='handler.ts':shutil.copyfile(source,a.output/'backend'/source.name)
 shutil.copyfile(here.parent/'backend-integration/reconciliation.ts',a.output/'backend/reconciliation.ts')
 print('private candidate reconstructed and checksums verified; nothing installed')

if __name__=='__main__':main()
