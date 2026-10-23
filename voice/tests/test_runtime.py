import tempfile
import unittest
from pathlib import Path

from runtime import PendingQueue, Whisper


class RuntimeTests(unittest.TestCase):
    def test_offline_queue_is_private_bounded_and_unique(self):
        with tempfile.TemporaryDirectory() as d:
            q = PendingQueue(Path(d))
            for i in range(105):
                q.add("request " + str(i))
            rows = list((Path(d) / "pending").glob("*.json"))
            self.assertEqual(len(rows), 100)
            self.assertEqual(rows[0].stat().st_mode & 0o777, 0o600)

    def test_whisper_failure_does_not_deliver_noise(self):
        w = Whisper(Path("/missing"), Path("/missing"))
        with self.assertRaises(RuntimeError):
            w.transcribe(Path("/unused"))


if __name__ == "__main__":
    unittest.main()


class CreditTests(unittest.TestCase):
    def test_overage_or_unknown_billing_never_allows_paid_voice(self):
        from runtime import subscription_safe

        self.assertFalse(
            subscription_safe(
                dict(
                    status="active",
                    character_limit=10000,
                    character_count=0,
                    max_credit_limit_extension="unlimited",
                ),
                100,
            )
        )
        self.assertFalse(
            subscription_safe(dict(status="active", character_limit=10000, character_count=0), 100)
        )
        self.assertFalse(
            subscription_safe(
                dict(
                    status="active",
                    character_limit=10000,
                    character_count=9990,
                    max_credit_limit_extension=0,
                ),
                100,
            )
        )
        self.assertTrue(
            subscription_safe(
                dict(
                    status="active",
                    character_limit=10000,
                    character_count=0,
                    max_credit_limit_extension=0,
                ),
                100,
            )
        )


class ApprovalTests(unittest.TestCase):
    def test_approval_expiry_accepts_iso_and_unix(self):
        from runtime import VOICE_ID, approval_active

        auth = dict(approved=True, voice_id=VOICE_ID, max_characters=400)
        for expiry in [1001, "1970-01-01T00:16:41+00:00", "1970-01-01T00:16:41Z"]:
            self.assertTrue(approval_active(dict(auth, expires_at=expiry), 100, now=1000))

    def test_invalid_or_expired_approval_is_inactive(self):
        from runtime import VOICE_ID, approval_active

        auth = dict(approved=True, voice_id=VOICE_ID, max_characters=400)
        for expiry in [
            1000,
            "1970-01-01T00:16:40+00:00",
            "1970-01-01T00:16:41",
            "invalid",
            None,
            True,
        ]:
            self.assertFalse(approval_active(dict(auth, expires_at=expiry), 100, now=1000))
        self.assertFalse(approval_active([], 100, now=1000))

    def test_iso_marker_reaches_credit_guard_without_synthesis(self):
        import json
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        from runtime import VOICE_ID, render

        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
            (home / "elevenlabs-approved.json").write_text(
                json.dumps(
                    dict(approved=True, voice_id=VOICE_ID, max_characters=400, expires_at=expiry)
                )
            )
            with (
                patch("runtime.credits_available", return_value=False) as credits,
                patch("runtime.render_local", return_value=home / "local.aiff"),
                patch("runtime.subprocess.run") as synthesis,
            ):
                render("hello", home)
                credits.assert_called_once_with(5)
                synthesis.assert_not_called()

    def test_daily_cap_reserves_all_three_helper_attempts(self):
        import json
        import time
        from unittest.mock import Mock, patch

        from runtime import VOICE_ID, render

        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "tmp").mkdir()
            (home / "elevenlabs-approved.json").write_text(
                json.dumps(
                    dict(
                        approved=True,
                        voice_id=VOICE_ID,
                        expires_at=time.time() + 60,
                        max_characters=400,
                        daily_character_cap=6,
                    )
                )
            )
            with (
                patch("runtime.credits_available", return_value=True),
                patch("runtime.subprocess.run", return_value=Mock(returncode=0)) as paid,
                patch("runtime.render_local", return_value=home / "local.aiff"),
            ):
                render("hi", home)
                render("hi", home)
                self.assertEqual(paid.call_count, 1)
                self.assertEqual(
                    json.loads((home / "elevenlabs-usage.json").read_text())["characters"], 6
                )
