#!/usr/bin/env python3
"""One inference per frame, five parallel gates, and no installation or setting changes."""

import hashlib
import json
import os
import time
from collections import deque
from pathlib import Path

import numpy as np
import webrtcvad
from compare import read
from openwakeword.model import Model
from pipeline import HERE, TRAINING, save, sha

THRESHOLDS = (0.99, 0.995, 0.998, 0.999, 0.9995)


def main():
    os.umask(0o077)
    started = time.monotonic()
    baseline = json.loads((HERE / "comparison.json").read_text())
    old = HERE / "baseline-old.onnx"
    new = HERE / "models/hey_ted_candidate.onnx"
    model = Model(wakeword_models=[str(old), str(new)], inference_framework="onnx")
    names = list(model.models)
    aliases = {names[0]: "old", names[1]: "candidate"}
    result = {
        "thresholds": list(THRESHOLDS),
        "models": {
            "old": {"path": str(old), "sha256": sha(old)},
            "candidate": {"path": str(new), "sha256": sha(new)},
        },
        "gate": {
            "consecutive_hits": 2,
            "vad_mode": 2,
            "recent_frames": 4,
            "frame_seconds": 0.08,
            "cooldown_seconds": 2,
        },
        "method": "Each PCM frame is inferred once by each classifier sharing frontend features. All thresholds receive the same score and VAD result. Negative replay preserves continuous model and VAD state for all 1800 seconds.",
        "streaming": {},
        "physical": [],
    }

    def score(x):
        model.reset()
        vad = webrtcvad.Vad(2)
        recent = deque(maxlen=4)
        rows = {
            name: {
                str(t): {"count": 0, "last": -100, "triggers": []} for t in THRESHOLDS
            }
            for name in names
        }
        peaks = {name: 0.0 for name in names}
        for offset in range(0, len(x) - 1279, 1280):
            frame = x[offset : offset + 1280]
            scores = model.predict(frame)
            pcm = frame.tobytes()
            recent.append(
                any(vad.is_speech(pcm[j : j + 640], 16000) for j in range(0, 2560, 640))
            )
            voiced = any(recent)
            for name, value in scores.items():
                value = float(value)
                peaks[name] = max(peaks[name], value)
                for threshold in THRESHOLDS:
                    row = rows[name][str(threshold)]
                    row["count"] = (
                        row["count"] + 1 if value >= threshold and voiced else 0
                    )
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
            aliases[name]: {
                "peak": peaks[name],
                "thresholds": {
                    t: {"triggers": row["triggers"]} for t, row in gates.items()
                },
            }
            for name, gates in rows.items()
        }

    # Clip resets match the original comparison; duplicated macOS PCM is inferred once.
    cache = {}
    for group, original in baseline["streaming"].items():
        unique = {}
        for trial in original["trials"]:
            unique.setdefault(trial["pcm_sha256"], trial)
        trials = []
        for pcm_hash, trial in unique.items():
            if pcm_hash not in cache:
                x = read(trial["path"])
                cache[pcm_hash] = score(
                    np.concatenate(
                        [
                            np.zeros(16000, dtype="int16"),
                            x,
                            np.zeros(24000, dtype="int16"),
                        ]
                    )
                )
            trials.append(
                {
                    "path": trial["path"],
                    "pcm_sha256": pcm_hash,
                    "models": cache[pcm_hash],
                }
            )
        curves = {}
        for alias in aliases.values():
            curves[alias] = {
                str(t): {
                    "detected": sum(
                        bool(trial["models"][alias]["thresholds"][str(t)]["triggers"])
                        for trial in trials
                    ),
                    "clips": len(trials),
                }
                for t in THRESHOLDS
            }
        result["streaming"][group] = {
            "requested_conditions": original["clips"],
            "unique_audio_clips": len(trials),
            "curves": curves,
            "trials": trials,
        }
        print(group, curves, flush=True)
        save("threshold-curve-partial.json", result)

    # Raw microphone windows do not receive synthetic prefix or suffix silence.
    for original in baseline["physical"]:
        path = Path(original["path"])
        result["physical"].append(
            {
                "path": str(path),
                "sha256": sha(path),
                "label": original["label"],
                "models": score(read(path)),
            }
        )

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
    pcm_hash = hashlib.sha256(pcm.tobytes()).hexdigest()
    assert pcm_hash == baseline["negative_replay"]["pcm_sha256"], (
        "negative PCM differs from baseline"
    )
    print("continuous 1800-second negative replay starting", flush=True)
    result["negative_replay"] = {
        "seconds": 1800,
        "pcm_sha256": pcm_hash,
        "models": score(pcm),
    }
    result["negative_counts"] = {
        alias: {str(t): len(row["thresholds"][str(t)]["triggers"]) for t in THRESHOLDS}
        for alias, row in result["negative_replay"]["models"].items()
    }
    result["baseline_099_counts_match"] = (
        result["negative_counts"]["old"]["0.99"] == 32
        and result["negative_counts"]["candidate"]["0.99"] == 29
    )
    assert result["baseline_099_counts_match"], "unchanged .99 counts did not reproduce"
    result["elapsed_seconds"] = time.monotonic() - started
    result["limitations"] = [
        "Whole-clip validation selects the candidate epoch. MacOS heldouts comprise 18 requested conditions and 12 unique PCM clips.",
        "Neural gate candidates are not accepted Whisper requests or measured audible interruptions.",
        "One controlled synthetic corpus and small physical windows do not establish room false-positive rates or natural user recall.",
    ]
    save("threshold-curve.json", result)
    print(result["negative_counts"], flush=True)
    print("saved threshold-curve.json", result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main()
