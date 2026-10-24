#!/usr/bin/env python3
"""Exercise the retention proposal in a disposable tree, without installing it."""
from pathlib import Path
import subprocess
import sys
import tempfile

PATCH = Path(__file__).with_name('retention-tools.patch').resolve()


def main():
    with tempfile.TemporaryDirectory(prefix='retention-check-') as temporary:
        for command in (['git', 'apply', '--check', str(PATCH)],
                        ['git', 'apply', str(PATCH)],
                        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']):
            result = subprocess.run(command, cwd=temporary)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
