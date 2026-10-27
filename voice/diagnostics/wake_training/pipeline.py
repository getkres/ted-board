#!/usr/bin/env python3
"""Isolated, local bare-stop candidate. Never installs or promotes a model."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = (
    Path(
        os.environ.get("TED_WAKE_CANDIDATE_HOME", str(Path(__file__).resolve().parent))
    )
    .expanduser()
    .resolve()
)
JOB = (
    Path(
        os.environ.get(
            "TED_WAKE_JOB_HOME",
            "/Users/vahallo/ted-ops/ted-board/jobs/card-c-hey-ted-voice-1022",
        )
    )
    .expanduser()
    .resolve()
)
TRAINING = JOB / "training"
SOURCE = JOB / "worktree/voice"
PYTHON = JOB / "runtime/venv/bin/python"
SEED = 20261027
PHRASES = ["Ted stop", "Ted, stop.", "Ted. Stop.", "Ted, stop!"]
RATES = [0.75, 0.95, 1.15, 1.35]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + "\n")


def generate():
    positive = HERE / "bare-positive"
    positive.mkdir(exist_ok=True)
    if list(positive.glob("*.wav")):
        raise RuntimeError(
            "preserving existing generated clips; generation not repeated"
        )
    phrases = HERE / "phrases.txt"
    phrases.write_text("\n".join(PHRASES) + "\n")
    command = [
        str(PYTHON),
        str(TRAINING / "run_piper.py"),
        str(phrases),
        "--max-samples",
        "400",
        "--batch-size",
        "10",
        "--output-dir",
        str(positive),
        "--max-speakers",
        "500",
        "--length-scales",
        *map(str, RATES),
        "--noise-scales",
        "0.667",
        "0.85",
    ]
    started = time.monotonic()
    with (HERE / "generate.log").open("w") as log:
        subprocess.run(
            command,
            env=dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1"),
            cwd=JOB,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    files = sorted(positive.glob("*.wav"), key=lambda p: int(p.stem))
    if len(files) != 400:
        raise RuntimeError("generator did not produce exactly 400 clips")
    save(
        "generation.json",
        {
            "command": command,
            "seconds": time.monotonic() - started,
            "checkpoint_sha256": sha(TRAINING / "piper/models/en-us-libritts-high.pt"),
            "source_generator_sha256": sha(TRAINING / "piper/generate_samples.py"),
            "policy": "Piper only, no macOS heldout voice or physical microphone input used in training",
            "clips": [
                {
                    "path": str(p.relative_to(HERE)),
                    "sha256": sha(p),
                    "phrase": PHRASES[int(p.stem) % 4],
                    "length_scale": RATES[(int(p.stem) // 10 // 2) % 4],
                    "speaker_pair": [0, int(p.stem)],
                }
                for p in files
            ],
        },
    )


def embed():
    import numpy as np
    import scipy.signal
    import soundfile as sf
    from openwakeword.utils import AudioFeatures

    rng = np.random.default_rng(SEED)
    files = sorted((HERE / "bare-positive").glob("*.wav"), key=lambda p: int(p.stem))
    if len(files) != 400:
        raise RuntimeError("exactly 400 generated clips required")
    rng.shuffle(files)
    features = AudioFeatures(inference_framework="onnx")
    out = HERE / "models"
    out.mkdir(exist_ok=True)
    manifest = {
        "seed": SEED,
        "split": "340 training clips, 60 whole-clip heldouts; no clip used in both",
        "source_cache": {},
        "splits": {},
    }

    def prepare(path, augment=False):
        x, sr = sf.read(path, dtype="float32")
        if sr != 16000 or x.ndim != 1:
            raise RuntimeError("unexpected generated PCM format")
        if augment:
            x = scipy.signal.resample(x, max(1, int(len(x) / rng.uniform(0.88, 1.13))))
        tail = int(rng.uniform(0.05, 0.38) * 16000)
        x = x[: 32800 - tail]
        pcm = np.zeros(32800, dtype=np.float32)
        start = max(0, 32800 - tail - len(x))
        pcm[start : start + len(x)] = x
        if augment:
            if rng.random() < 0.5:
                delay = int(rng.uniform(0.03, 0.16) * 16000)
                pcm[delay:] += pcm[:-delay] * rng.uniform(0.1, 0.35)
            pcm *= rng.uniform(0.12, 1)
            pcm += rng.normal(0, rng.uniform(0, 0.003), len(pcm)).astype("float32")
        return (np.clip(pcm, -1, 1) * 32767).astype("int16")

    started = time.monotonic()
    for split, selected in [("train", files[:340]), ("val", files[340:])]:
        base = JOB / "runtime/models" / (split + ".npz")
        with np.load(base) as data:
            old_x, old_y = data["X"], data["Y"]
        rows = []
        for path in selected:
            rows.append(prepare(path))
            if split == "train":
                rows.append(prepare(path, True))
        embedded = []
        for start in range(0, len(rows), 64):
            embedded.append(
                features.embed_clips(
                    np.stack(rows[start : start + 64]), batch_size=64, ncpu=4
                )[:, -16:, :]
            )
            print("embedding", split, start, len(rows), flush=True)
        added = np.concatenate(embedded).astype("float32")
        x = np.concatenate([old_x, added])
        y = np.concatenate([old_y, np.ones((len(added), 1), dtype="float32")])
        np.savez(out / (split + ".npz"), X=x, Y=y)
        np.savez(
            HERE / (split + "-bare.npz"),
            X=added,
            Y=np.ones((len(added), 1), dtype="float32"),
        )
        manifest["source_cache"][split] = {
            "path": str(base),
            "sha256": sha(base),
            "shape": list(old_x.shape),
        }
        manifest["splits"][split] = {
            "clips": [str(p.relative_to(HERE)) for p in selected],
            "new_examples": len(added),
            "total_examples": len(x),
            "preserved_prefix_equal": bool(
                np.array_equal(x[: len(old_x)], old_x)
                and np.array_equal(y[: len(old_y)], old_y)
            ),
        }
    manifest["seconds"] = time.monotonic() - started
    save("embedding.json", manifest)


def train():
    command = [
        str(PYTHON),
        str(SOURCE / "train_wake.py"),
        "--data",
        str(TRAINING),
        "--out",
        str(HERE / "models"),
        "--reuse",
        "--music",
        str(TRAINING / "background-music.wav"),
        str(TRAINING / "background-train-extra.wav"),
    ]
    started = time.monotonic()
    with (HERE / "train.log").open("w") as log:
        subprocess.run(
            command, cwd=JOB, stdout=log, stderr=subprocess.STDOUT, check=True
        )
    shutil.copy2(HERE / "models/hey_ted.onnx", HERE / "models/hey_ted_candidate.onnx")
    save(
        "training-run.json",
        {
            "command": command,
            "seconds": time.monotonic() - started,
            "candidate_sha256": sha(HERE / "models/hey_ted_candidate.onnx"),
            "trainer_sha256": sha(SOURCE / "train_wake.py"),
            "note": "Original cached examples retained, 680 bare-stop training examples appended, and original 3000 music/mixed examples regenerated. Original trainer metadata positive_clips reports its source corpus only; see embedding.json for appended clips.",
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["generate", "embed", "train"])
    args = parser.parse_args()
    HERE.mkdir(parents=True, exist_ok=True, mode=0o700)
    globals()[args.stage]()
