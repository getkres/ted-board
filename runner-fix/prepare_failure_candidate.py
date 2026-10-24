#!/usr/bin/env python3
"""Prepare private candidate copies only. Never installs or deploys runtime code."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parent
RUNTIME = ('sessions.py', 'session_worker.py', 'board_live.py', 'live_status.py')


def prepare(runtime, destination):
    runtime, destination = Path(runtime).resolve(), Path(destination).resolve()
    if destination.exists() or destination == runtime:
        raise ValueError('Use a new candidate directory')
    sources = {name: runtime/name for name in RUNTIME}
    sources['handler.ts'] = runtime/'supabase/functions/ted-board/handler.ts'
    sources['inbox_steward.py'] = runtime/'steward-runtime/current/inbox_steward.py'
    manifest = json.loads((PACKAGE/'failure-routing-baseline.json').read_text())
    for name, source in sources.items():
        if hashlib.sha256(source.read_bytes()).hexdigest() != manifest[name]:
            raise ValueError('Private source drift: '+name+'. Rebase and retest before review.')
    destination.mkdir(parents=True, mode=0o700)
    destination.chmod(0o700)
    for source in sources.values():
        shutil.copy2(source, destination/source.name)
    for source in sources['handler.ts'].parent.glob('*.ts'):
        shutil.copy2(source, destination/source.name)
    shutil.copy2(PACKAGE/'inbox_policy.py', destination/'inbox_policy.py')
    for name in sources:
        with (PACKAGE/('failure-routing-'+name+'.patch')).open() as delta:
            result = subprocess.run(['patch', '--batch', '--fuzz=0', str(destination/name)],
                                    stdin=delta, capture_output=True, text=True)
        if result.returncode:
            raise ValueError('Candidate patch failed: '+name+'. Do not use this candidate.')
    for source in destination.iterdir():
        if source.is_file():
            source.chmod(0o600)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.runtime_root, args.destination)
    except (OSError, ValueError):
        print('Candidate preparation refused. Check source drift, manifest, and destination.', file=sys.stderr)
        return 1
    print('Candidate copies prepared. Nothing installed or deployed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
