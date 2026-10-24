"""Prepare hash-checked private steward and optional GET feed candidates offline."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--feed-source', type=Path)
    parser.add_argument('--dest', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / 'baseline.json').read_text())
    if args.dest.exists():
        raise SystemExit('Candidate destination must not already exist.')
    jobs = [('runtime.patch', args.source, args.dest, manifest['files'])]
    if args.feed_source is not None:
        jobs.append(('feed.patch', args.feed_source, args.dest / 'feed', manifest['feed_files']))
    for patch_name, source, dest, files in jobs:
        if hashlib.sha256((bundle / patch_name).read_bytes()).hexdigest() != manifest['patches'][patch_name]:
            raise SystemExit('Review patch differs from its manifest. Regenerate hashes before continuing.')
        for name, expected in files.items():
            if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
                raise SystemExit('Private source differs from the reviewed baseline. Rebase the patch before continuing.')
    for patch_name, source, dest, files in jobs:
        dest.mkdir(parents=True, mode=0o700)
        for name in files:
            shutil.copy2(source / name, dest / name)
        command = ['patch', '--batch', '--fuzz=0', '-p1', '-i', str(bundle / patch_name)]
        for options in (['--dry-run'], []):
            result = subprocess.run(command + options, cwd=dest, capture_output=True, text=True)
            if result.returncode:
                raise SystemExit('Review patch refused drift. Inspect candidate copies locally before continuing.')
    print('Private candidate prepared. Installed runtime and backend were not changed.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError):
        raise SystemExit('Candidate could not be prepared. Check the private baseline and destination.') from None
