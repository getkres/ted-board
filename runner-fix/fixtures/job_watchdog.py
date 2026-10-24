"""Public logging/probe contract fixture, without private recovery operations."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

LOG = Path('unused-watchdog.log')


def log(rows, dry_run):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        for row in rows:
            stream.write(json.dumps(dict(at=time.time(), dry_run=dry_run, **row), sort_keys=True) + '\n')
    LOG.chmod(0o600)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--root', type=Path)
    args = parser.parse_args(argv)
    if args.probe:
        print(json.dumps(dict(jobs=[])))
        return 0
    raise ValueError('Only the offline probe is available in this fixture')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        row = dict(action='watchdog_error', reason=type(exc).__name__)
        log([row], True)
        print(json.dumps(row))
        sys.exit(1)
