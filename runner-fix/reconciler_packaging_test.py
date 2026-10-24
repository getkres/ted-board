"""Offline CLI reconstruction contract using harmless source fixtures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class Packaging(unittest.TestCase):
    def test_relative_paths_reconstruct_and_source_drift_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / 'bundle/runner-fix'
            backend = root / 'source/supabase/functions/ted-board'
            bundle.mkdir(parents=True)
            backend.mkdir(parents=True)
            (bundle.parent / 'backend-integration').mkdir()
            (bundle.parent / 'backend-integration/reconciliation.ts').write_text('// fixture\n')
            shutil.copyfile(HERE / 'reconstruct_reconciler.py', bundle / 'reconstruct_reconciler.py')
            manifest = {}
            for name in ('sessions.py', 'handler.ts', 'hourly-SKILL.md', 'inbox_steward.py'):
                source = backend / name if name == 'handler.ts' else root / 'source' / name
                source.write_text('before\n')
                patch = name + '.patch'
                (bundle / patch).write_text('--- a/' + name + '\n+++ b/' + name + '\n@@ -1 +1 @@\n-before\n+after\n')
                manifest[name] = dict(patch=patch, baseline_sha256=hashlib.sha256(b'before\n').hexdigest(),
                                      candidate_sha256=hashlib.sha256(b'after\n').hexdigest())
            (bundle / 'reconciler-manifest.json').write_text(json.dumps(manifest))
            command = [sys.executable, str(bundle / 'reconstruct_reconciler.py'), '--baseline', 'source',
                       '--output', 'candidate', '--hourly-skill', 'source/hourly-SKILL.md',
                       '--steward-source', 'source/inbox_steward.py']
            run = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual((root / 'candidate/sessions.py').read_text(), 'after\n')
            (root / 'source/sessions.py').write_text('changed\n')
            command[command.index('candidate')] = 'refused'
            run = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse((root / 'refused').exists())


if __name__ == '__main__':
    unittest.main()
