#!/usr/bin/env python3
"""Rebuild and test the private worker overlay without changing live files."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import deploy_review_gate as deploy

ROOT = Path(__file__).resolve().parent
NEW_TESTS = ('review_gate_test.py', 'review_adapter_test.py', 'review_deploy_test.py', 'review_transport_test.py', 'review_unit_fixtures.py')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-root', type=Path, default=Path.home() / 'ted-ops/ted-board')
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--python-only', action='store_true')
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='ted-review-test-') as tmp:
        staged = Path(tmp) / 'ted-board'; staged.mkdir()
        for p in args.private_root.glob('*.py'): shutil.copy2(p, staged / p.name)
        for name in ('tests', 'supabase'):
            shutil.copytree(args.private_root / name, staged / name)
        for name in ('ted-decisions', 'telegram-ted'):
            (Path(tmp) / name).symlink_to(args.private_root.parent / name, target_is_directory=True)
        for target, content in deploy.worker_changes(args.private_root,args.bundle).items():
            (staged / target.relative_to(args.private_root)).write_bytes(content)
        for name in ('review_gate.py', 'review.py', 'deploy_review_gate.py'):
            shutil.copy2(ROOT / name, staged / name)
        for name in NEW_TESTS: shutil.copy2(ROOT / 'tests' / name, staged / 'tests' / name)
        # Force any accidentally unmocked Python HTTP request to fail locally.
        command = [sys.executable, '-c',
                   'import unittest; from unittest.mock import patch; '
                   'suite=unittest.defaultTestLoader.discover("tests",pattern="*_test.py"); '
                   'block=patch("urllib.request.urlopen",side_effect=RuntimeError("network disabled during tests")); '
                   'block.start(); result=unittest.TextTestRunner(verbosity=1).run(suite); '
                   'raise SystemExit(not result.wasSuccessful())']
        python = subprocess.run(command, cwd=staged)
        if args.python_only: return python.returncode
        deno = shutil.which('deno') or str(Path.home() / '.deno/bin/deno')
        environment = {k: v for k, v in os.environ.items() if not k.startswith('TED_VETO_')}
        typescript = subprocess.run([deno, 'test', '--allow-env', 'tests/'], cwd=staged, env=environment)
        return max(python.returncode, typescript.returncode)


if __name__ == '__main__': sys.exit(main())
