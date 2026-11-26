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
RUNTIME_DATA = ('runner_failure_templates.json', 'capacity.json')
NEW_TESTS = ('review_gate_test.py', 'review_adapter_test.py', 'review_deploy_test.py', 'review_transport_test.py', 'review_unit_fixtures.py')


def python_suite(private_root):
    import importlib.abc
    import importlib.machinery
    import unittest
    from unittest.mock import patch
    staged = Path.cwd().resolve()

    class OverlayFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            # Sibling legacy modules mutate sys.path. Keep local runtime imports
            # bound to this snapshot even after those mutations.
            if '.' not in fullname and (staged / (fullname + '.py')).is_file():
                return importlib.machinery.PathFinder.find_spec(fullname, [str(staged)])
            return None

    sys.meta_path.insert(0, OverlayFinder())
    with patch('urllib.request.urlopen', side_effect=RuntimeError('network disabled during tests')):
        import board_live, card
        assert all(Path(m.__file__).resolve().parent == staged for m in (board_live, card))
        suite = unittest.defaultTestLoader.discover('tests', pattern='*_test.py')
        suite.addTests(unittest.defaultTestLoader.discover('tests', pattern='test_*.py'))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    live = Path(private_root).resolve()
    leaked = sorted(n for n, m in list(sys.modules.items()) if getattr(m, '__file__', None)
                    and Path(m.__file__).resolve().parent == live)
    print('live modules imported during tests: ' + (', '.join(leaked) or 'none'))
    return int(bool(leaked) or not result.wasSuccessful())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-root', type=Path, default=Path.home() / 'ted-ops/ted-board')
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--python-only', action='store_true')
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='ted-review-test-') as tmp:
        staged = Path(tmp) / 'ted-board'; staged.mkdir()
        for p in args.private_root.glob('*.py'): shutil.copy2(p, staged / p.name)
        # Runtime data the worker modules read at import. Named, never globbed.
        for name in RUNTIME_DATA:
            if (args.private_root / name).is_file(): shutil.copy2(args.private_root / name, staged / name)
        for name in ('tests', 'supabase', 'scripts'):
            shutil.copytree(args.private_root / name, staged / name)
        for name in ('ted-decisions', 'telegram-ted'):
            (Path(tmp) / name).symlink_to(args.private_root.parent / name, target_is_directory=True)
        for target, content in deploy.worker_changes(args.private_root,args.bundle).items():
            (staged / target.relative_to(args.private_root)).write_bytes(content)
        for name in ('review_gate.py', 'review.py', 'deploy_review_gate.py', 'test_review_gate.py'):
            shutil.copy2(ROOT / name, staged / name)
        for name in NEW_TESTS: shutil.copy2(ROOT / 'tests' / name, staged / 'tests' / name)
        # Force any accidentally unmocked Python HTTP request to fail locally.
        command = [sys.executable, '-c',
                   'import test_review_gate as harness; raise SystemExit(harness.python_suite(%r))'
                   % str(args.private_root)]
        python = subprocess.run(command, cwd=staged)
        if args.python_only: return python.returncode
        deno = shutil.which('deno') or str(Path.home() / '.deno/bin/deno')
        environment = {k: v for k, v in os.environ.items() if not k.startswith('TED_VETO_')}
        typescript = subprocess.run([deno, 'test', '--allow-env', 'tests/'], cwd=staged, env=environment)
        return max(python.returncode, typescript.returncode)


if __name__ == '__main__': sys.exit(main())
