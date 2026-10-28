#!/usr/bin/env python3
"""Train an openWakeWord-compatible classifier on Piper synthetic audio.

Invoke after generating positives and confusables with dscripka/piper-sample-generator.
Training and validation clip splits, seeds, and metrics are recorded with the model.
"""

import argparse
import json
import random
from pathlib import Path

import numpy as np
import scipy.signal
import soundfile as sf
import torch
from openwakeword.utils import AudioFeatures

p = argparse.ArgumentParser()
p.add_argument("--data", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--reuse", action="store_true")
p.add_argument("--music", type=Path, nargs="*", default=[])
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
random.seed(20261022)
np.random.seed(20261022)
torch.manual_seed(20261022)
torch.set_num_threads(4)
rng = np.random.default_rng(20261022)
features = AudioFeatures(inference_framework="onnx")
length = 32800


def read(path):
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != 16000:
        x = scipy.signal.resample_poly(x, 16000, sr)
    return x


def prepare(x, positive=False, augment=False):
    if augment:
        rate = rng.uniform(0.88, 1.13)
        x = scipy.signal.resample(x, max(1, int(len(x) / rate)))
    tail = int(rng.uniform(0.05, 0.38) * 16000) if positive else 0
    out = np.zeros(length, dtype=np.float32)
    if len(x) > length - tail:
        start = 0 if positive else int(rng.integers(0, len(x) - (length - tail) + 1))
        x = x[start : start + length - tail]
    start = max(0, length - tail - len(x)) if positive else 0
    out[start : start + len(x)] = x
    if augment:
        if rng.random() < 0.5:
            delay = int(rng.uniform(0.03, 0.16) * 16000)
            out[delay:] += out[:-delay] * rng.uniform(0.1, 0.35)
        out *= rng.uniform(0.12, 1.0)
        out += rng.normal(0, rng.uniform(0, 0.003), len(out)).astype(np.float32)
    return (np.clip(out, -1, 1) * 32767).astype(np.int16)


pos = sorted((a.data / "positive").glob("*.wav"))
neg = sorted((a.data / "negative").glob("*.wav"))
# Separate entire synthetic clips, with macOS voices reserved for external validation.
rng.shuffle(pos)
rng.shuffle(neg)
background = sorted((a.data / "librispeech").rglob("*.flac"))
speakers = sorted({f.parent.parent.name for f in background})
training_speakers = set(speakers[: int(len(speakers) * 0.7)])
background = [f for f in background if f.parent.parent.name in training_speakers]
rng.shuffle(background)
sets = {}
if a.reuse:
    for name in ["train", "val"]:
        cached = np.load(a.out / (name + ".npz"))
        sets[name] = (torch.from_numpy(cached["X"]), torch.from_numpy(cached["Y"]))
else:
    for name in ["train", "val"]:
        rows = []
        labels = []
        for paths, label in [(pos, 1), (neg, 0)]:
            cut = int(len(paths) * 0.85)
            selected = paths[:cut] if name == "train" else paths[cut:]
            for path in selected:
                rows.append(prepare(read(path), label == 1, name == "train"))
                labels.append(label)
                if name == "train" and label:
                    rows.append(prepare(read(path), True, True))
                    labels.append(1)
        for path in background[:1800] if name == "train" else background[1800:2000]:
            x = read(path)
            for j in range(0, len(x), length):
                if len(x[j : j + length]) < 8000:
                    continue
                rows.append(prepare(x[j : j + length], False, name == "train"))
                labels.append(0)
        for _ in range(200 if name == "train" else 40):
            rows.append((rng.normal(0, rng.uniform(1, 2500), length)).astype(np.int16))
            labels.append(0)
        print("embedding", name, len(rows), flush=True)
        data = []
        for i in range(0, len(rows), 64):
            data.append(
                features.embed_clips(np.stack(rows[i : i + 64]), batch_size=64, ncpu=4)[:, -16:, :]
            )
        X = np.concatenate(data).astype(np.float32)
        Y = np.array(labels, dtype=np.float32)[:, None]
        sets[name] = (torch.from_numpy(X), torch.from_numpy(Y))
        np.savez(a.out / (name + ".npz"), X=X, Y=Y)
        print("embedded", name, X.shape, flush=True)

if a.music:
    music = [read(path) for path in a.music]
    rows = []
    labels = []
    for _ in range(2400):
        track = music[int(rng.integers(len(music)))]
        offset = int(rng.integers(0, len(track) - length))
        rows.append(prepare(track[offset : offset + length], False, True))
        labels.append(0)
    for _ in range(600):
        clip = prepare(read(pos[int(rng.integers(len(pos) * 0.85))]), True, True).astype(np.float32)
        track = music[int(rng.integers(len(music)))]
        offset = int(rng.integers(0, len(track) - length))
        clip += track[offset : offset + length] * rng.uniform(0.01, 0.15) * 32767
        rows.append(np.clip(clip, -32768, 32767).astype(np.int16))
        labels.append(1)
    extra = []
    for i in range(0, len(rows), 64):
        extra.append(
            features.embed_clips(np.stack(rows[i : i + 64]), batch_size=64, ncpu=4)[:, -16:, :]
        )
    x, y = sets["train"]
    sets["train"] = (
        torch.cat([x, torch.from_numpy(np.concatenate(extra))]),
        torch.cat([y, torch.tensor(labels, dtype=torch.float32)[:, None]]),
    )
    print("added music examples", len(rows), flush=True)

model = torch.nn.Sequential(
    torch.nn.Flatten(),
    torch.nn.Linear(1536, 64),
    torch.nn.LayerNorm(64),
    torch.nn.ReLU(),
    torch.nn.Linear(64, 32),
    torch.nn.ReLU(),
    torch.nn.Linear(32, 1),
    torch.nn.Sigmoid(),
)
opt = torch.optim.AdamW(model.parameters(), lr=0.0005)
X, Y = sets["train"]
vx, vy = sets["val"]
best = 1e9
best_state = None
for epoch in range(55):
    model.train()
    indices = torch.randperm(len(X))
    for batch in indices.split(256):
        pred = model(X[batch])
        loss = torch.nn.functional.binary_cross_entropy(
            pred, Y[batch], weight=torch.where(Y[batch] > 0, 1.0, 2.0)
        )
        opt.zero_grad()
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        pred = model(vx)
        vloss = torch.nn.functional.binary_cross_entropy(pred, vy).item()
    if vloss < best:
        best = vloss
        best_state = {k: v.clone() for k, v in model.state_dict().items()}
    if epoch % 10 == 0:
        print("epoch", epoch, "val_loss", round(vloss, 4), flush=True)
model.load_state_dict(best_state)
model.eval()
with torch.no_grad():
    scores = model(vx).numpy().ravel()
y = vy.numpy().ravel()
metrics = {}
for threshold in [0.5, 0.7, 0.8, 0.9, 0.95]:
    metrics[str(threshold)] = {
        "positive_recall": float(np.mean(scores[y == 1] >= threshold)),
        "negative_false_positive_fraction": float(np.mean(scores[y == 0] >= threshold)),
    }
torch.onnx.export(
    model,
    torch.zeros(1, 16, 96),
    str(a.out / "hey_ted.onnx"),
    input_names=["input"],
    output_names=["score"],
    opset_version=17,
    dynamo=False,
)
meta = dict(
    seed=20261022,
    positive_clips=len(pos),
    confusable_clips=len(neg),
    train_examples=len(X),
    validation_examples=len(vx),
    validation_loss=best,
    thresholds=metrics,
    training_speakers=sorted(training_speakers),
    music_sources=[str(path.name) for path in a.music],
    note="Synthetic holdout, not a room or user-voice acceptance test.",
)
(a.out / "training.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta), flush=True)
