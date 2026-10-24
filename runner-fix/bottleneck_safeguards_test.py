#!/usr/bin/env python3
"""Verify proposed private tools in a disposable tree, without installing them."""
from pathlib import Path
import subprocess
import sys
import tempfile

PATCH = Path(__file__).with_name('safeguard-tools.patch').resolve()


def main():
    with tempfile.TemporaryDirectory(prefix='safeguard-check-') as temporary:
        root = Path(temporary).resolve()
        # A plain temporary directory is sufficient for git apply. No checkout,
        # production path, provider connection, or runtime installation is used.
        for command in ([ 'git', 'apply', '--check', str(PATCH)],
                        [ 'git', 'apply', str(PATCH)],
                        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']):
            result = subprocess.run(command, cwd=root)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
