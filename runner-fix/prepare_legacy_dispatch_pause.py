"""Reconstruct a private candidate. This command never installs or changes state."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--root',type=Path,required=True)
 parser.add_argument('--out',type=Path,required=True)
 args=parser.parse_args();root=args.root.resolve();out=args.out.resolve()
 manifest=json.loads((HERE/'legacy-dispatch-pause-manifest.json').read_text())
 if out.exists():raise SystemExit('Output must not exist.')
 for name,entry in manifest['files'].items():
  if sha(root/name)!=entry['baseline_sha256']:raise SystemExit('Baseline changed: '+name)
 for name,digest in manifest['dependencies'].items():
  if sha(root/name)!=digest:raise SystemExit('Dependency changed: '+name)
 for name in manifest['new_files']:
  if (root/name).exists() or (root/name).is_symlink():raise SystemExit('New file already exists: '+name)
 out.mkdir(parents=True);(out/'legacy-baseline').mkdir()
 for name in manifest['files']:
  shutil.copy2(root/name,out/name);shutil.copy2(root/name,out/'legacy-baseline'/name)
 for name in manifest['dependencies']:shutil.copy2(root/name,out/name)
 for patch in ('legacy-dispatch-pause-helper.patch','legacy-dispatch-pause.patch'):
  subprocess.run(['patch','--fuzz=0','-p0','-i',str(HERE/patch)],cwd=out,check=True)
 for name,entry in manifest['files'].items():
  if sha(out/name)!=entry['candidate_sha256']:raise SystemExit('Candidate mismatch: '+name)
 for name,digest in manifest['new_files'].items():
  if sha(out/name)!=digest:raise SystemExit('New file mismatch: '+name)
 print(json.dumps(dict(candidate=str(out),manifest=manifest),indent=2))
if __name__=='__main__':main()
