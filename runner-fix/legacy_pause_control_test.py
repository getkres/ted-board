"""Local state control tests; no production paths are used."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('control',Path(__file__).with_name('legacy_pause_control.py'))
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

class State(unittest.TestCase):
 def test_absent_marker_is_restored_as_absent(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'jobs').mkdir();backup=root/'backup.json'
   control.pause(root,backup)
   self.assertEqual((root/'jobs/dispatch-pause.json').read_bytes(),control.PAUSED)
   control.restore(root,backup);self.assertFalse((root/'jobs/dispatch-pause.json').exists())
 def test_existing_marker_bytes_and_mode_are_restored(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'jobs').mkdir();marker=root/'jobs/dispatch-pause.json';backup=root/'backup.json'
   original=b'{"paused": false}\n';marker.write_bytes(original);marker.chmod(0o640)
   control.pause(root,backup);control.restore(root,backup)
   self.assertEqual(marker.read_bytes(),original);self.assertEqual(marker.stat().st_mode&0o777,0o640)
 def test_existing_backup_and_changed_marker_are_never_overwritten(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'jobs').mkdir();backup=root/'backup.json';control.pause(root,backup)
   with self.assertRaises(ValueError):control.pause(root,backup)
   marker=root/'jobs/dispatch-pause.json';marker.write_bytes(b'{"paused":true,"operator":"other"}')
   with self.assertRaises(ValueError):control.restore(root,backup)
   self.assertIn(b'operator',marker.read_bytes())
 def test_symlink_marker_is_refused(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'jobs').mkdir();(root/'jobs/dispatch-pause.json').symlink_to(root/'missing')
   with self.assertRaises(ValueError):control.pause(root,root/'backup.json')

if __name__=='__main__':unittest.main()
