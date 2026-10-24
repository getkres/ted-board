"""Pure voice policies, with no device, network, or model side effects."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Endpoint:
    silence: float = 0.0
    elapsed: float = 0.0
    heard: bool = False

    def feed(self, voiced: bool, seconds: float) -> bool:
        self.elapsed += seconds
        self.heard |= voiced
        self.silence = 0.0 if voiced else self.silence + seconds
        return (
            self.elapsed >= 30
            or (self.heard and self.silence >= 1.2 - 1e-8)
            or (not self.heard and self.elapsed >= 5)
        )


def speech_text(text: str) -> str:
    text = re.sub(r"```.*?(?:```|$)", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!\[[^]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}|>|[-*+] |\d+[.)] )\s*", "", text)
    text = re.sub(r"[*_~|]", "", text).replace(chr(0x2014), ", ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"\b(?:hey\s+)?ted[, .!]*\s*stop listening\b", "the pause command", text, flags=re.I
    )
    text = re.sub(r"\bhey[ ,.!]*ted\b", "Ted", text, flags=re.I)
    words = text.split()
    if len(words) > 60:
        # Prefer whole opening sentences. Never invent facts in a spoken summary.
        prefix = " ".join(words[:54])
        sentences = re.split(r"(?<=[.!?])\s+", prefix)
        prefix = " ".join(sentences[:-1]) if len(sentences) > 1 else prefix.rstrip(",:;") + "."
        text = prefix + " Details are on your phone."
    return text


def wake_command(text: str):
    text = text.strip()
    if re.fullmatch(r"(?:hey\s+)?ted[, .!]*\s*stop listening[.! ]*", text, re.I):
        return "__pause__"
    m = re.match(r"^hey[ ,.!]*ted\b[ ,.!:]*", text, re.I)
    return text[m.end() :].strip() if m else None


class ReplyCursor:
    def __init__(self, marker):
        self.marker = marker
        self.seen = False
        self.cancelled = False
        self.text = []

    def feed(self, row):
        if self.cancelled or row.get("isSidechain"):
            return None
        msg = row.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, str):
            text = content
            parts = []
        else:
            parts = content
            text = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
        if row.get("type") == "user":
            if self.marker in text:
                self.seen = True
                return None
            if self.seen and text.strip():
                self.cancelled = True
            return None
        if row.get("type") != "assistant" or not self.seen:
            return None
        if msg.get("stop_reason") == "tool_use" or any(p.get("type") == "tool_use" for p in parts):
            self.text = []
            return None
        if text.strip():
            self.text.append(text)
        if msg.get("stop_reason") == "end_turn" and self.text:
            return "\n".join(self.text)
        return None

    def finish_idle(self):
        return "\n".join(self.text) if self.seen and not self.cancelled and self.text else None


class PlaybackGate:
    def __init__(self, threshold=0.7, barge_threshold=0.95, hits=2):
        self.threshold = threshold
        self.barge_threshold = barge_threshold
        self.hits = hits
        self.count = 0

    def accept(self, score, playing=False, echo_clean=True):
        passed = score >= (self.barge_threshold if playing else self.threshold) and (
            not playing or echo_clean
        )
        self.count = self.count + 1 if passed else 0
        if self.count >= self.hits:
            self.count = 0
            return True
        return False


def choose_devices(devices, default_input, default_output):
    def pick(kind, fallback):
        return next(
            (d["id"] for d in devices if "jabra" in d["name"].lower() and d[kind]), fallback
        )

    return pick("input", default_input), pick("output", default_output)


class Pause:
    def __init__(self, home):
        self.path = Path(home) / "paused"

    @property
    def paused(self):
        return self.path.exists()

    def stop(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600)

    def resume(self):
        self.path.unlink(missing_ok=True)
