"""Offline CLI reconstruction contract using harmless source fixtures."""
import hashlib
import json
import os
import plistlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class Packaging(unittest.TestCase):
    def test_launchd_path_resolves_private_operator_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);binary=home/'.local/bin/gh';binary.parent.mkdir(parents=True);binary.write_text('#!/bin/sh\necho fixture-gh\n');binary.chmod(0o700)
            text=(HERE/'reconciler-launchd.plist').read_text().replace('__TED_HOME__',str(home)).replace('__TED_BOARD_ROOT__',str(home/'ted-ops/ted-board'))
            plist=plistlib.loads(text.encode());env=plist.get('EnvironmentVariables',{})
            self.assertEqual(shutil.which('gh',path=env.get('PATH',os.defpath)),str(binary))

    def test_relative_paths_reconstruct_and_source_drift_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / 'bundle/runner-fix'
            backend = root / 'source/supabase/functions/ted-board'
            bundle.mkdir(parents=True)
            backend.mkdir(parents=True)
            (bundle.parent / 'backend-integration').mkdir()
            (bundle.parent / 'backend-integration/reconciliation.ts').write_text('// fixture\n')
            (backend / 'runner_failure_templates.json').write_text('{"version":1}\n')
            shutil.copyfile(HERE / 'reconstruct_reconciler.py', bundle / 'reconstruct_reconciler.py')
            (root / 'source/policy.py').write_text('policy before\n')
            (root / 'source/dispatch_pause.py').write_text('pause fixture\n')
            (bundle / 'reconciler-baseline-dependencies.json').write_text(json.dumps({'policy.py': hashlib.sha256(b'policy before\n').hexdigest(),'dispatch_pause.py':hashlib.sha256(b'pause fixture\n').hexdigest()}))
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
            self.assertEqual((root / 'candidate/dispatch_pause.py').read_text(),'pause fixture\n')
            self.assertTrue((root / 'candidate/backend/runner_failure_templates.json').is_file())
            self.assertEqual((root / 'candidate/backend/runner_failure_templates.json').read_text(), '{"version":1}\n')
            (root / 'source/sessions.py').write_text('changed\n')
            command[command.index('candidate')] = 'refused'
            run = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse((root / 'refused').exists())
            (root / 'source/sessions.py').write_text('before\n')
            (root / 'source/policy.py').write_text('policy changed\n')
            command[command.index('refused')] = 'dependency-refused'
            run = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse((root / 'dependency-refused').exists())


if __name__ == '__main__':
    unittest.main()
