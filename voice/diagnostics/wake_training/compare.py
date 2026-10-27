#!/usr/bin/env python3
"""Compare old and candidate models with identical PCM and unchanged playback gate."""

import hashlib
import json
import os
import subprocess
import time
from collections import deque
from pathlib import Path

import numpy as np
import onnxruntime as ort
import scipy.signal
import soundfile as sf
import webrtcvad
from openwakeword.model import Model
from pipeline import HERE, JOB, TRAINING, save, sha


def read(path):
    x, sr = sf.read(path, dtype="int16")
    if x.ndim == 1 and sr == 16000:
        return x
    x = x.astype("float32") / 32768
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != 16000:
        x = scipy.signal.resample_poly(x, 16000, sr)
    return (np.clip(x, -1, 1) * 32767).astype("int16")


def main():
    os.umask(0o077)
    old = (
        Path(os.environ.get("TED_WAKE_BASELINE_MODEL", str(HERE / "baseline-old.onnx")))
        .expanduser()
        .resolve()
    )
    new = HERE / "models/hey_ted_candidate.onnx"
    started = time.monotonic()
    model = Model(wakeword_models=[str(old), str(new)], inference_framework="onnx")
    names = list(model.models)
    assert len(names) == 2
    result = {
        "models": {
            names[0]: {"path": str(old), "sha256": sha(old)},
            names[1]: {"path": str(new), "sha256": sha(new)},
        },
        "gate": {
            "threshold": 0.99,
            "consecutive_hits": 2,
            "vad_mode": 2,
            "recent_frames": 4,
            "frame_seconds": 0.08,
            "cooldown_seconds": 2,
        },
        "scope": "Neural candidate detection only. No inference delivery, playback, Whisper confirmation, or external request occurs. All model comparisons use identical samples.",
        "static": {},
        "streaming": {},
        "physical": [],
    }

    def score(x):
        model.reset()
        vad = webrtcvad.Vad(2)
        recent = deque(maxlen=4)
        rows = {
            name: {"peak": 0.0, "triggers": [], "count": 0, "last": -100}
            for name in names
        }
        for offset in range(0, len(x) - 1279, 1280):
            frame = x[offset : offset + 1280]
            scores = model.predict(frame)
            pcm = frame.tobytes()
            recent.append(
                any(vad.is_speech(pcm[j : j + 640], 16000) for j in range(0, 2560, 640))
            )
            for name, value in scores.items():
                row = rows[name]
                value = float(value)
                row["peak"] = max(row["peak"], value)
                row["count"] = row["count"] + 1 if value >= 0.99 and any(recent) else 0
                if row["count"] >= 2:
                    row["count"] = 0
                    if offset / 16000 - row["last"] >= 2:
                        row["triggers"].append(
                            {
                                "seconds": round(offset / 16000, 3),
                                "score": round(value, 6),
                            }
                        )
                        row["last"] = offset / 16000
        return {
            name: {"peak": round(row["peak"], 6), "triggers": row["triggers"]}
            for name, row in rows.items()
        }

    # Reconstruct original whole-clip validation order. Cached Y verifies its layout.
    rng = np.random.default_rng(20261022)
    positives = sorted((TRAINING / "positive").glob("*.wav"))
    negatives = sorted((TRAINING / "negative").glob("*.wav"))
    rng.shuffle(positives)
    rng.shuffle(negatives)
    old_holdout = positives[int(len(positives) * 0.85) :]
    with np.load(JOB / "runtime/models/val.npz") as data:
        vx, vy = data["X"], data["Y"].ravel()
    assert np.all(vy[: len(old_holdout)] == 1) and np.all(vy[len(old_holdout) :] == 0)
    with np.load(HERE / "val-bare.npz") as data:
        bx = data["X"]
    static_groups = {
        "hey_ted": [
            i for i, p in enumerate(old_holdout) if not p.name.startswith("stop-")
        ],
        "ted_stop_listening": [
            i for i, p in enumerate(old_holdout) if p.name.startswith("stop-")
        ],
        "old_negatives": list(range(len(old_holdout), len(vx))),
    }
    for path, name in [(old, names[0]), (new, names[1])]:
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        outputs = np.array(
            [
                float(session.run(None, {"input": row[None, ...]})[0].ravel()[0])
                for row in vx
            ]
        )
        added = np.array(
            [
                float(session.run(None, {"input": row[None, ...]})[0].ravel()[0])
                for row in bx
            ]
        )
        result["static"][name] = {
            group: {
                "clips": len(indices),
                "at_099": int((outputs[indices] >= 0.99).sum()),
                "fraction_at_099": float((outputs[indices] >= 0.99).mean()),
            }
            for group, indices in static_groups.items()
        }
        result["static"][name]["bare_ted_stop"] = {
            "clips": len(added),
            "at_099": int((added >= 0.99).sum()),
            "fraction_at_099": float((added >= 0.99).mean()),
        }

    manifest = json.loads((HERE / "embedding.json").read_text())
    groups = {
        "hey_ted": [p for p in old_holdout if not p.name.startswith("stop-")],
        "ted_stop_listening": [p for p in old_holdout if p.name.startswith("stop-")],
        "bare_ted_stop": [HERE / p for p in manifest["splits"]["val"]["clips"]],
    }
    # Heldout macOS voices never appear in any training or embedding array.
    directory = HERE / "heldout-macos"
    directory.mkdir(exist_ok=True)
    metadata = []
    for voice in ("Daniel", "Samantha"):
        for rate in (120, 140, 180):
            for label, phrase in [
                ("hey_ted", "Hey Ted."),
                ("bare_ted_stop", "Ted, stop."),
                ("ted_stop_listening", "Ted, stop listening."),
            ]:
                path = directory / f"{voice}-{rate}-{label}.wav"
                if not path.exists():
                    subprocess.run(
                        [
                            "/usr/bin/say",
                            "-v",
                            voice,
                            "-r",
                            str(rate),
                            "-o",
                            str(path),
                            "--file-format=WAVE",
                            "--data-format=LEI16@16000",
                            phrase,
                        ],
                        check=True,
                        capture_output=True,
                    )
                groups.setdefault("macos_" + label, []).append(path)
                metadata.append(
                    {
                        "path": str(path),
                        "phrase": phrase,
                        "rate": rate,
                        "voice": voice,
                        "sha256": sha(path),
                        "pcm_sha256": hashlib.sha256(read(path).tobytes()).hexdigest(),
                    }
                )
    result["heldout_macos"] = metadata
    result["heldout_macos_audit"] = {
        "requested_conditions": len(metadata),
        "unique_audio_clips": len({row["pcm_sha256"] for row in metadata}),
        "note": "Requested rates are conditions, not independent samples. Count unique PCM hashes separately; these voices produced identical audio for 120 and 140 requests in this run.",
    }
    for group, paths in groups.items():
        trials = []
        for path in paths:
            x = read(path)
            padded = np.concatenate(
                [np.zeros(16000, dtype="int16"), x, np.zeros(24000, dtype="int16")]
            )
            trials.append(
                {
                    "path": str(path),
                    "sha256": sha(path),
                    "pcm_sha256": hashlib.sha256(x.tobytes()).hexdigest(),
                    "duration_seconds": len(x) / 16000,
                    "models": score(padded),
                }
            )
        result["streaming"][group] = {
            "clips": len(paths),
            "unique_audio_clips": len({t["pcm_sha256"] for t in trials}),
            "models": {
                name: {
                    "detected": sum(
                        bool(t["models"][name]["triggers"]) for t in trials
                    ),
                    "recall": sum(bool(t["models"][name]["triggers"]) for t in trials)
                    / len(trials),
                }
                for name in names
            },
            "trials": trials,
        }
        print(group, result["streaming"][group]["models"], flush=True)
        save("comparison-partial.json", result)

    physical = Path("/Users/vahallo/ted-ops/voice/FULL-1027/private-diagnostics")
    for path in sorted(physical.rglob("*.wav")):
        result["physical"].append(
            {
                "path": str(path),
                "sha256": sha(path),
                "label": "known bare-stop acoustic candidate"
                if path.name == "bare-stop-candidate.wav"
                else "unlabelled diagnostic microphone window",
                "duration_seconds": len(read(path)) / 16000,
                "models": score(read(path)),
            }
        )
    # Match original validation's heldout-speaker speech/music/mixed construction.
    files = sorted((TRAINING / "librispeech").rglob("*.flac"))
    speakers = sorted({p.parent.parent.name for p in files})
    heldout = set(speakers[int(len(speakers) * 0.7) :])
    chunks = []
    count = 0
    for path in [p for p in files if p.parent.parent.name in heldout]:
        x = read(path).astype("float32") / 32767
        chunks.append(x)
        count += len(x)
        if count >= 1800 * 16000:
            break
    speech = np.concatenate(chunks)
    if len(speech) < 1800 * 16000:
        speech = np.tile(speech, int(np.ceil(1800 * 16000 / len(speech))))
    speech = speech[: 1800 * 16000]
    music = read(TRAINING / "background-heldout.wav").astype("float32") / 32767
    music = np.tile(music, int(np.ceil(len(speech) / len(music))))[: len(speech)]
    third = len(speech) // 3
    speech[third : 2 * third] = music[third : 2 * third] * 0.7
    speech[2 * third :] = speech[2 * third :] * 0.65 + music[2 * third :] * 0.3
    pcm = (np.clip(speech, -1, 1) * 32767).astype("int16")
    print("negative replay 1800 seconds starting", flush=True)
    result["negative_replay"] = {
        "seconds": 1800,
        "conditions": "10 minutes heldout speech, 10 minutes heldout music, and 10 minutes mixed",
        "pcm_sha256": hashlib.sha256(pcm.tobytes()).hexdigest(),
        "heldout_speakers": sorted(heldout),
        "models": score(pcm),
    }
    result["elapsed_seconds"] = time.monotonic() - started
    result["limitations"] = [
        "Synthetic heldouts and offline microphone replay do not replace installed acoustic acceptance.",
        "Scores are not calibrated probabilities. Static one-window metrics are separate from unchanged .99 two-hit streaming/VAD results.",
        "Unknown diagnostic windows have no positive or negative label, so their triggers are descriptive only.",
    ]
    save("comparison.json", result)
    print("comparison saved", result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main()
