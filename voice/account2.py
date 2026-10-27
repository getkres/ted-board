"""Subscription-only, account 2 voice conversation, with scoped read-only context."""

import hashlib
import json
import os
import re
import shlex
import subprocess
import threading
import unicodedata
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from session import Offline

SYSTEM = (
    "You are Ted answering through a read-only voice fallback while the main Ted conversation "
    "is unavailable or busy. Reply naturally in brief spoken prose, usually under 60 words. "
    "You may use only Read, Grep, and Glob in the four provided context directories. You cannot "
    "execute actions, send messages, spend money, or modify data. Requests for actions are "
    "queued separately for main Ted. Never claim to have completed an action. Do not invoke "
    "speech tools: the local loop speaks your final text. Never use an em dash, and always "
    "use the Oxford comma."
)
CONTEXT_POLICY = "read-only-four-roots-v1"


def voice_card(config_dir):
    """Read the configured UserPromptSubmit card without executing its mutating hook."""
    try:
        settings = json.loads((Path(config_dir) / "settings.json").read_text())
        for group in settings.get("hooks", {}).get("UserPromptSubmit", []):
            for hook in group.get("hooks", []):
                if hook.get("type") != "command":
                    continue
                command = shlex.split(hook.get("command", ""))
                if len(command) != 1:
                    continue
                script = Path(command[0].replace("$HOME", str(Path.home()))).expanduser()
                for line in script.read_text().splitlines():
                    if not line.strip().startswith("cat "):
                        continue
                    parts = shlex.split(line)
                    if len(parts) != 2 or not parts[1].endswith(".md"):
                        continue
                    path = Path(parts[1].replace("$HOME", str(Path.home()))).expanduser()
                    card = path.read_text()
                    if card.strip() and len(card) <= 32768:
                        return card.strip()
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    raise Offline("Ted voice card unavailable")


def account2_environment(source, directory):
    env = dict(source)
    for key in list(env):
        if key.startswith(("ANTHROPIC_", "CLAUDE_")) or key in (
            "CLAUDECODE",
            "CLAUDE_SECURESTORAGE_CONFIG_DIR",
            "CLAUDE_CODE_OAUTH_TOKEN",
            "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
            "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
            "CLAUDE_CODE_CUSTOM_HEADERS_HELPER",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            env.pop(key, None)
    env["CLAUDE_CONFIG_DIR"] = str(directory)
    return env


def subscription_usage(directory):
    """Read account-specific OAuth usage, keeping Keychain secrets only in memory."""
    try:
        normalized = unicodedata.normalize("NFC", str(directory))
        suffix = hashlib.sha256(normalized.encode()).hexdigest()[:8]
        username = os.environ.get("USER", "")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", username):
            raise ValueError()
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                username,
                "-w",
                "-s",
                "Claude Code-credentials-" + suffix,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode:
            raise ValueError()
        credentials = json.loads(result.stdout)
        token = credentials["claudeAiOauth"]["accessToken"]
        if not isinstance(token, str) or not token:
            raise ValueError()
        request = urllib.request.Request(
            "https://api.anthropic.com/api/oauth/usage",
            headers={
                "Authorization": "Bearer " + token,
                "anthropic-beta": "oauth-2025-04-20",
                "Content-Type": "application/json",
            },
        )
        # Do not allow inherited proxy credentials to redirect the OAuth request.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return json.loads(response.read(262144))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise Offline("account 2 extra usage status unavailable") from None


class Account2Bridge:
    def __init__(self, home, emit=None, binary=None, config_dir=None):
        self.home = Path(home)
        self.emit = emit or (lambda *args, **kwargs: None)
        self.binary = str(binary or Path.home() / ".local/bin/claude")
        self.config_dir = Path(config_dir or Path.home() / ".claude-acct2")
        self.state_path = self.home / "claude-voice-session.json"
        self.context_roots = [
            Path.home() / part for part in ("ted-ops/ted-state", "biz", "kres", "ventures")
        ]
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.Lock()
        self.process = None
        self.closed = False
        self.future = None
        try:
            self.state = (
                json.loads(self.state_path.read_text())
                if self.state_path.exists()
                else {
                    "session_id": str(uuid.uuid4()),
                    "launched": False,
                    "context_policy": CONTEXT_POLICY,
                }
            )
            if str(uuid.UUID(self.state["session_id"])) != self.state["session_id"]:
                raise ValueError()
            if type(self.state["launched"]) is not bool:
                raise ValueError()
            if self.state.get("context_policy") != CONTEXT_POLICY:
                self.state = {
                    "session_id": str(uuid.uuid4()),
                    "launched": False,
                    "context_policy": CONTEXT_POLICY,
                    "previous_session_id": self.state["session_id"],
                }
        except (OSError, ValueError, KeyError, TypeError):
            raise Offline("invalid local voice conversation state") from None

    def _save(self):
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.state_path.with_name("voice-session-" + uuid.uuid4().hex + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(self.state, stream)
        temporary.replace(self.state_path)

    def assert_current(self, sid):
        if self.closed or sid != self.state["session_id"]:
            raise Offline("voice conversation changed")

    def deliver(self, text):
        self.assert_current(self.state["session_id"])
        if self.future and not self.future.done():
            raise Offline("previous voice request still in progress; not resent")
        request = dict(
            session_id=self.state["session_id"],
            marker="voice:" + uuid.uuid4().hex,
            accepted=False,
            text=text,
        )
        env = account2_environment(os.environ, self.config_dir)
        self.future = self.executor.submit(self._turn, request, env)
        request["future"] = self.future
        return request

    def _verify_auth(self, env):
        if self.config_dir.is_symlink() or not self.config_dir.is_dir():
            raise Offline("account 2 Max login unavailable")
        try:
            result = subprocess.run(
                [self.binary, "auth", "status", "--json"],
                env=env,
                cwd=self.home,
                capture_output=True,
                text=True,
                timeout=10,
            )
            auth = json.loads(result.stdout)
            if (
                result.returncode
                or not isinstance(auth, dict)
                or auth.get("loggedIn") is not True
                or auth.get("authMethod") != "claude.ai"
                or auth.get("apiProvider") != "firstParty"
                or auth.get("subscriptionType") != "max"
                or Path(auth.get("configDirectory", "")).resolve() != self.config_dir.resolve()
            ):
                raise ValueError()
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            raise Offline("account 2 Max login unavailable") from None
        usage = subscription_usage(self.config_dir)
        extra = usage.get("extra_usage") if isinstance(usage, dict) else None
        if not isinstance(extra, dict) or extra.get("is_enabled") is not False:
            raise Offline("account 2 extra usage must be disabled")
        self.emit("claude_account2_ready", account=2, auth_method="claude.ai", subscription="max")
        self.emit("claude_account2_plan_only", extra_usage_enabled=False)

    def _turn(self, request, env):
        proc = None
        try:
            self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._verify_auth(env)
            sid = request["session_id"]
            prompt = voice_card(self.config_dir) + "\n\n" + SYSTEM
            if any(root.is_symlink() or not root.is_dir() for root in self.context_roots):
                raise Offline("read-only voice context directories unavailable")
            command = [
                self.binary,
                "-p",
                "--model",
                "sonnet",
                "--output-format",
                "stream-json",
                "--input-format",
                "stream-json",
                "--verbose",
                "--replay-user-messages",
                "--tools",
                "Read,Grep,Glob",
                "--restricted",
                "--add-dir",
                *(str(root) for root in self.context_roots[1:]),
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--safe-mode",
                "--permission-prompts",
                "none",
                "--permission-mode",
                "dontAsk",
                "--setting-sources",
                "",
                "--system-prompt-snapshot",
                "off",
                "--settings",
                '{"forceLoginMethod":"claudeai"}',
                "--system-prompt",
                prompt,
                "--resume" if self.state["launched"] else "--session-id",
                sid,
            ]
            content = "[voice] " + request["marker"] + "\n" + request["text"]
            frame = dict(type="user", session_id=sid, message=dict(role="user", content=content))
            with self.lock:
                self.assert_current(sid)
                # Record intent before starting, but undo it if no child was created.
                previously_launched = self.state["launched"]
                self.state["launched"] = True
                self._save()
                try:
                    proc = subprocess.Popen(
                        command,
                        cwd=self.context_roots[0],
                        env=env,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except OSError:
                    self.state["launched"] = previously_launched
                    self._save()
                    raise
                self.process = proc
            try:
                output, _ = proc.communicate(json.dumps(frame) + "\n", timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise Offline("Claude voice reply timed out; not retried") from None
            final = None
            for line in output.splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                if row.get("type") == "user" and row.get("session_id") == sid:
                    body = row.get("message", {}).get("content", "")
                    if isinstance(body, list):
                        body = "\n".join(p.get("text", "") for p in body if p.get("type") == "text")
                    if request["marker"] in body:
                        request["accepted"] = True
                if row.get("type") == "result":
                    final = row
            if final and final.get("session_id") != sid:
                raise Offline("Claude voice result session mismatch")
            if (
                proc.returncode
                or not final
                or final.get("is_error") is not False
                or final.get("subtype") != "success"
                or not isinstance(final.get("result"), str)
                or not final["result"].strip()
            ):
                self.emit(
                    "claude_voice_process_failed",
                    returncode=proc.returncode,
                    result_present=final is not None,
                )
                raise Offline("Claude voice reply failed; not retried")
            request["accepted"] = True
            self.emit("claude_voice_reply", account=2, characters=len(final["result"]))
            return final["result"].strip()
        except Offline as exc:
            self.emit("claude_voice_failed", reason=str(exc))
            raise
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            self.emit("claude_voice_failed", reason="Claude voice process failed; not retried")
            raise Offline("Claude voice process failed; not retried") from None
        finally:
            with self.lock:
                if self.process is proc:
                    self.process = None

    def poll(self, request):
        self.assert_current(request["session_id"])
        future = request["future"]
        return future.result() if future.done() else None

    def close(self):
        with self.lock:
            self.closed = True
            proc = self.process
            self.process = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.emit(
                    "claude_voice_shutdown_failed",
                    reason="child did not exit within shutdown limit",
                )
        self.executor.shutdown(wait=False, cancel_futures=True)
