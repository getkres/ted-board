#!/usr/bin/env python3
"""Apply review patches in a disposable tree, and exercise their actual behavior."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions-source', type=Path, default=HERE / 'fixtures/sessions.py')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='admission-check-') as temporary:
        root = Path(temporary)
        shutil.copyfile(args.sessions_source, root / 'sessions.py')
        for filename in ('run.sh', 'codex-browser.sh', 'run-task.sh'):
            shutil.copyfile(HERE / 'fixtures' / filename, root / filename)
        commands = [
            ['git', 'apply', '--check', str(HERE / 'shared-admission-tools.patch')],
            ['git', 'apply', str(HERE / 'shared-admission-tools.patch')],
            *[['patch', '--batch', '--fuzz=0', '-p1', '-i', str(HERE / name)] for name in (
                'shared-admission-sessions.patch', 'codex-heartbeat-admission.patch',
                'direct-browser-admission.patch')],
            ['/bin/bash', '-n', 'run-task.sh'],
            ['/bin/bash', '-n', 'run.sh'],
            ['/bin/bash', '-n', 'codex-browser.sh'],
            [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']]
        for command in commands:
            result = subprocess.run(command, cwd=root)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
