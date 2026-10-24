"""Candidate preparation never changes live sources, and refuses drift."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import prepare_failure_candidate as prepare


class Package(unittest.TestCase):
    def fixture(self, root):
        runtime=root/'runtime';package=root/'package';package.mkdir()
        paths={name:runtime/name for name in prepare.RUNTIME}
        paths['handler.ts']=runtime/'supabase/functions/ted-board/handler.ts'
        paths['inbox_steward.py']=runtime/'steward-runtime/current/inbox_steward.py'
        manifest={}
        for name,path in paths.items():
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text('original\n')
            manifest[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            (package/('failure-routing-'+name+'.patch')).write_text('--- '+name+'\n+++ '+name+'\n@@ -1 +1 @@\n-original\n+candidate\n')
        (package/'failure-routing-baseline.json').write_text(json.dumps(manifest))
        (package/'inbox_policy.py').write_text('# fixture policy\n')
        (package/'runner_failure_templates.json').write_text('{}\n')
        return runtime,package,paths

    def test_preparation_applies_only_to_private_candidate_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime,package,paths=self.fixture(root);destination=root/'candidate'
            with patch.object(prepare,'PACKAGE',package):prepare.prepare(runtime,destination)
            for name,source in paths.items():
                self.assertEqual(source.read_text(),'original\n')
                self.assertEqual((destination/name).read_text(),'candidate\n')
            self.assertEqual(destination.stat().st_mode & 0o777,0o700)

    def test_drift_and_existing_destinations_refuse_before_patching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime,package,paths=self.fixture(root);destination=root/'candidate'
            paths['sessions.py'].write_text('unreviewed change\n')
            with patch.object(prepare,'PACKAGE',package),self.assertRaises(ValueError):prepare.prepare(runtime,destination)
            self.assertFalse(destination.exists())
            with patch.object(prepare,'PACKAGE',package),self.assertRaises(ValueError):prepare.prepare(runtime,runtime)
            self.assertEqual(paths['sessions.py'].read_text(),'unreviewed change\n')

if __name__=='__main__':unittest.main()
