"""Build the SSM Go playback helper and fetch its pinned scrcpy server."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import requests


ROOT = Path(__file__).resolve().parent
SERVER_VERSION = "3.3.1"
SERVER_SHA256 = "a0f70b20aa4998fbf658c94118cd6c8dab6abbb0647a3bdab344d70bc1ebcbb8"


def build():
    local_go = ROOT / ".tools" / "go" / "bin" / ("go.exe" if os.name == "nt" else "go")
    go = str(local_go) if local_go.is_file() else shutil.which("go")
    if not go:
        raise RuntimeError("构建 SSM 播放核心需要 Go 1.25 或更高版本")
    assets = ROOT / "assets" / "ssm"
    assets.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, CGO_ENABLED="0")
    if local_go.is_file():
        environment["GOMODCACHE"] = str(ROOT / ".tools" / "gomod")
        environment["GOCACHE"] = str(ROOT / ".tools" / "gocache")
    name = "ssm-playback.exe" if sys.platform == "win32" else "ssm-playback"
    subprocess.run(
        [go, "build", "-trimpath", "-o", str(assets / name), "./cmd/autodori"],
        cwd=ROOT / "playback" / "ssm", env=environment, check=True,
    )
    server = assets / ("scrcpy-server-v" + SERVER_VERSION)
    if not server.is_file() or hashlib.sha256(server.read_bytes()).hexdigest() != SERVER_SHA256:
        response = requests.get(
            "https://github.com/Genymobile/scrcpy/releases/download/v%s/%s" %
            (SERVER_VERSION, server.name), timeout=45,
        )
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != SERVER_SHA256:
            raise RuntimeError("scrcpy server 校验失败")
        server.write_bytes(response.content)
    print("SSM playback ready:", assets / name)


if __name__ == "__main__":
    build()
