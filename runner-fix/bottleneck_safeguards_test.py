#!/usr/bin/env python3
"""Verify proposed private tools in a disposable tree, without installing them."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PATCH = Path(__file__).with_name('safeguard-tools.patch').resolve()
WATCHDOG_PATCH = PATCH.with_name('bounded-watchdog-log.patch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watchdog-source', type=Path,
                        default=PATCH.parent / 'fixtures/job_watchdog.py')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='safeguard-check-') as temporary:
        root = Path(temporary).resolve()
        shutil.copyfile(args.watchdog_source, root / 'job_watchdog.py')
        if 'from reconciler_gate import reconciler_enabled' in args.watchdog_source.read_text():
            gate = args.watchdog_source.parent / 'reconciler_gate.py'
            if not gate.is_file() or gate.is_symlink():
                raise ValueError('reviewed reconciler gate dependency required')
            shutil.copyfile(gate, root / gate.name)
            # The isolated logging probe must never redirect into managed services.
            (root / 'jobs').mkdir()
            (root / 'jobs/reconciler-config.json').write_text(json.dumps(dict(enabled=False)))
        # A plain temporary directory is sufficient for git apply. No checkout,
        # production path, provider connection, or runtime installation is used.
        for command in ([ 'git', 'apply', '--check', str(PATCH)],
                        [ 'git', 'apply', str(PATCH)],
                        ['patch', '--batch', '--fuzz=0', '-p1', '-i', str(WATCHDOG_PATCH)],
                        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']):
            result = subprocess.run(command, cwd=root, env=dict(os.environ, TED_RECONCILER_ENABLED='false'))
            if result.returncode:
                return result.returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
