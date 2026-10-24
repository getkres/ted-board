"""Prepare a hash-checked private steward candidate. Never install or call a network."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--dest', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / 'baseline.json').read_text())
    if args.dest.exists():
        raise SystemExit('Candidate destination must not already exist.')
    for name, expected in manifest['files'].items():
        if hashlib.sha256((args.source / name).read_bytes()).hexdigest() != expected:
            raise SystemExit('Private runtime differs from the reviewed baseline. Rebase the patch before continuing.')
    args.dest.mkdir(parents=True, mode=0o700)
    for name in manifest['files']:
        shutil.copy2(args.source / name, args.dest / name)
    command = ['patch', '--batch', '--fuzz=0', '-p1', '-i', str(bundle / 'runtime.patch')]
    for options in (['--dry-run'], []):
        result = subprocess.run(command + options, cwd=args.dest, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit('Runtime patch refused drift. Inspect candidate copies locally before continuing.')
    print('Private candidate prepared. Installed runtime was not changed.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError):
        raise SystemExit('Candidate could not be prepared. Check the private baseline and destination.') from None
