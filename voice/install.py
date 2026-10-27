#!/usr/bin/env python3
"""Install the reviewed voice sources on a Mac mini. Never installs on a MacBook."""

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import time
from pathlib import Path

RUNTIME_FILES = (
    "core.py", "session.py", "account2.py", "routing.py", "runtime.py",
    "loop.py", "daemon.py", "README.md", "requirements.txt",
)


def launchd_config(home, python):
    return dict(
        Label="co.ted.voice",
        ProgramArguments=[
            str(home / "Ted Voice.app/Contents/MacOS/TedVoice"),
            "--supervise",
            str(python),
            str(home / "app/daemon.py"),
            "--home",
            str(home),
        ],
        RunAtLoad=True,
        KeepAlive=True,
        ThrottleInterval=30,
        ProcessType="Background",
        WorkingDirectory=str(home),
        EnvironmentVariables=dict(PATH="/opt/homebrew/bin:/usr/bin:/bin", PYTHONUNBUFFERED="1",
                                  CLAUDE_CONFIG_DIR=str(Path.home() / ".claude-acct2")),
        StandardOutPath=str(home / "logs/launchd.out.log"),
        StandardErrorPath=str(home / "logs/launchd.err.log"),
    )


def install_native(source, home):
    """Update audio without replacing the launcher's approved microphone identity."""
    helper = home / "bin/TedVoiceAudio"
    helper.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["/usr/bin/swiftc", "-O", str(source / "Audio.swift"), "-o", str(helper)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "/usr/bin/codesign",
            "--force",
            "--sign",
            "-",
            "--identifier",
            "co.ted.voice.audio",
            str(helper),
        ],
        check=True,
    )
    app = home / "Ted Voice.app"
    bundle = app / "Contents"
    launcher = bundle / "MacOS/TedVoice"
    if not launcher.exists() or not (bundle / "Info.plist").exists():
        launcher.parent.mkdir(parents=True, exist_ok=True)
        info = dict(
            CFBundleIdentifier="co.ted.voice",
            CFBundleName="Ted Voice",
            CFBundleDisplayName="Ted Voice",
            CFBundleExecutable="TedVoice",
            CFBundlePackageType="APPL",
            CFBundleVersion="1",
            LSUIElement=True,
            NSMicrophoneUsageDescription="Ted listens locally for hey Ted, then transcribes your request on this Mac.",
        )
        (bundle / "Info.plist").write_bytes(plistlib.dumps(info))
        shutil.copy2(helper, launcher)
        subprocess.run(
            [
                "/usr/bin/codesign",
                "--force",
                "--sign",
                "-",
                "--identifier",
                "co.ted.voice",
                str(app),
            ],
            check=True,
        )
    for target in [helper, app]:
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(target)], check=True)
    # LaunchServices registration supplies the approved app context to launchd.
    # Device enumeration does not open the microphone or request permission.
    subprocess.run(
        [
            "/usr/bin/open",
            "-n",
            "-g",
            "-W",
            str(app),
            "--stdout",
            "/dev/null",
            "--stderr",
            "/dev/null",
            "--args",
            "--devices",
        ],
        check=True,
        timeout=15,
    )


def restart_service(domain, plist, attempts=20):
    """launchd can briefly reject bootstrap while an unloaded job exits."""
    subprocess.run(["/bin/launchctl", "bootout", domain + "/co.ted.voice"], capture_output=True)
    for attempt in range(attempts):
        result = subprocess.run(["/bin/launchctl", "bootstrap", domain, str(plist)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return
        if result.returncode != 5 or attempt == attempts - 1:
            raise subprocess.CalledProcessError(result.returncode, result.args,
                                                result.stdout, result.stderr)
        time.sleep(0.5)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--home", type=Path, default=Path.home() / "ted-ops/voice")
    p.add_argument("--python", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--load", action="store_true")
    a = p.parse_args()
    machine = json.loads(
        subprocess.check_output(["/usr/sbin/system_profiler", "SPHardwareDataType", "-json"])
    )["SPHardwareDataType"][0]["machine_name"]
    if machine != "Mac mini":
        raise SystemExit("Install voice routines on the Mac mini only.")
    os.umask(0o077)
    home = a.home
    source = Path(__file__).resolve().parent
    for folder in ["app", "models", "logs", "tmp", "tones", "pending"]:
        (home / folder).mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in RUNTIME_FILES:
        if (source / name).exists():
            shutil.copy2(source / name, home / "app" / name)
    if (source / "README.md").exists():
        shutil.copy2(source / "README.md", home / "README.md")
    for name in ["hey_ted.onnx", "training.json"]:
        shutil.copy2(a.models / name, home / "models" / name)
    install_native(source, home)
    import math
    import struct
    import wave

    for name, hz in [("listen", 660), ("sent", 440)]:
        samples = [
            int(math.sin(2 * math.pi * hz * i / 16000) * 2200 * math.sin(math.pi * i / 1600))
            for i in range(1600)
        ]
        with wave.open(str(home / "tones" / (name + ".wav")), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    plist = Path.home() / "Library/LaunchAgents/co.ted.voice.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps(launchd_config(home, a.python.absolute())))
    subprocess.run(["/usr/bin/plutil", "-lint", str(plist)], check=True)
    if a.load:
        domain = "gui/" + str(os.getuid())
        restart_service(domain, plist)
    print("voice installation staged on the mini")


if __name__ == "__main__":
    main()
