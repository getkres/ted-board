import unittest
from pathlib import Path

from install import launchd_config


class InstallTests(unittest.TestCase):
    def test_runtime_copy_includes_main_router_and_guarded_fallback(self):
        from install import RUNTIME_FILES

        self.assertIn("routing.py", RUNTIME_FILES)
        self.assertIn("account2.py", RUNTIME_FILES)
        self.assertIn("session.py", RUNTIME_FILES)

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
        self.assertIn("CLAUDE_CONFIG_DIR", p["EnvironmentVariables"])
        self.assertEqual(p["EnvironmentVariables"]["CLAUDE_CONFIG_DIR"], str(Path.home() / ".claude-acct2"))


class RestartTests(unittest.TestCase):
    def test_bootstrap_retries_transient_unload_race(self):
        import subprocess
        from unittest.mock import patch

        from install import restart_service

        transient = subprocess.CompletedProcess([], 5, stderr="Input/output error")
        success = subprocess.CompletedProcess([], 0, stderr="")
        with patch("install.subprocess.run", side_effect=[success, transient, success]) as run, patch("install.time.sleep") as sleep:
            restart_service("gui/501", Path("/tmp/co.ted.voice.plist"))
        self.assertEqual(run.call_count, 3)
        sleep.assert_called_once()

    def test_bootstrap_does_not_hide_persistent_failure(self):
        import subprocess
        from unittest.mock import patch

        from install import restart_service

        failed = subprocess.CompletedProcess([], 5, stderr="persistent failure")
        with patch("install.subprocess.run", return_value=failed), patch("install.time.sleep"):
            with self.assertRaises(subprocess.CalledProcessError):
                restart_service("gui/501", Path("/tmp/co.ted.voice.plist"), attempts=2)


class NativeInstallTests(unittest.TestCase):
    def test_update_preserves_approved_launcher_and_builds_external_audio_helper(self):
        import tempfile
        from unittest.mock import patch

        from install import install_native

        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            source = home / "source"
            source.mkdir()
            (source / "Audio.swift").write_text("// native source")
            bundle = home / "Ted Voice.app/Contents"
            (bundle / "MacOS").mkdir(parents=True)
            launcher = bundle / "MacOS/TedVoice"
            launcher.write_bytes(b"approved launcher")
            info = bundle / "Info.plist"
            info.write_bytes(b"approved app identity")
            with patch("install.subprocess.run") as run:
                install_native(source, home)
            self.assertEqual(launcher.read_bytes(), b"approved launcher")
            self.assertEqual(info.read_bytes(), b"approved app identity")
            calls = [call.args[0] for call in run.call_args_list]
            self.assertTrue(
                any(
                    call[0] == "/usr/bin/swiftc" and str(home / "bin/TedVoiceAudio") in call
                    for call in calls
                )
            )
            self.assertFalse(
                any("--force" in call and str(home / "Ted Voice.app") in call for call in calls)
            )


if __name__ == "__main__":
    unittest.main()
