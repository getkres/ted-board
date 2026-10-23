import unittest
from pathlib import Path

from install import launchd_config


class InstallTests(unittest.TestCase):
    def test_launchd_uses_bundle_supervisor_and_durable_paths(self):
        p = launchd_config(
            Path("/Users/test/ted-ops/voice"), Path("/Users/test/ted-ops/voice/.venv/bin/python")
        )
        self.assertEqual(p["Label"], "co.ted.voice")
        self.assertTrue(p["KeepAlive"])
        self.assertIn("Ted Voice.app", p["ProgramArguments"][0])
        self.assertTrue(p["StandardErrorPath"].endswith("/voice/logs/launchd.err.log"))
        self.assertNotIn("jobs/", str(p))
        self.assertEqual(p["ThrottleInterval"], 30)


if __name__ == "__main__":
    unittest.main()
