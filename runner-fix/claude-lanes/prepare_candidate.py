"""Prepare private runtime copies for offline review. Never install them."""
import argparse
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--dest', type=Path, required=True)
    args = parser.parse_args()
    if args.dest.exists():
        raise SystemExit('Candidate destination must not already exist.')
    args.dest.mkdir(parents=True, mode=0o700)
    for name in ('sessions.py', 'session_worker.py'):
        shutil.copy2(args.source / name, args.dest / name)
    for name in ('inbox_policy.py', 'runner_failure_templates.json'):
        if (args.source / name).exists():
            shutil.copy2(args.source / name, args.dest / name)
    patch = Path(__file__).resolve().with_name('runtime.patch')
    command = ['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)]
    for options in (['--dry-run'], []):
        result = subprocess.run(command + options, cwd=args.dest, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit('Runtime patch refused drift. Inspect candidate copies locally, and rebase before installation.')
    print('Candidate prepared. Production files were not changed.')


if __name__ == '__main__':
    main()
