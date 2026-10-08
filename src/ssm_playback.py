"""Bridge to the vendored SSM Go touch generator and playback scheduler."""

import json
import logging
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


class SSMPlayback:
    def __init__(self, serial, resolution, *, offline=False):
        base = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent
        )
        assets = base / "assets" / "ssm"
        executable = assets / ("ssm-playback.exe" if sys.platform == "win32" else "ssm-playback")
        if not executable.is_file():
            raise FileNotFoundError("SSM 播放核心缺失，请先运行 python build_ssm.py")
        server = assets / "scrcpy-server-v3.3.1"
        if not offline and not server.is_file():
            raise FileNotFoundError("scrcpy server 缺失，请先运行 python build_ssm.py")
        workspace = base / "data" / "ssm"
        workspace.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(executable), "-serial", str(serial), "-server", str(server),
            "-width", str(resolution[0]), "-height", str(resolution[1]),
        ]
        if offline:
            cmd.append("-offline")
        self._messages = queue.Queue()
        self._write_lock = threading.Lock()
        self._closed = False
        self.stats = {}
        self._process = subprocess.Popen(
            cmd, cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()
        try:
            self._wait_for("connected", 30)
        except Exception:
            self.close()
            raise

    def _read_output(self):
        for line in self._process.stdout:
            try:
                message = json.loads(line)
            except (ValueError, TypeError):
                level = logging.WARNING if "[WARN]" in line or "[FATAL]" in line else logging.DEBUG
                logging.log(level, "SSM: %s", line.rstrip())
                continue
            if isinstance(message, dict) and "event" in message:
                self._messages.put(message)
        self._messages.put({"event": "error", "message": "SSM 播放进程已退出"})

    def _send(self, command, **fields):
        with self._write_lock:
            if self._closed or self._process.poll() is not None:
                raise RuntimeError("SSM 播放进程已关闭")
            self._process.stdin.write(json.dumps({"command": command, **fields}) + "\n")
            self._process.stdin.flush()

    def poll(self, timeout=0.05):
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty:
            return None
        if message["event"] == "error":
            raise RuntimeError(message.get("message", "SSM 播放失败"))
        return message

    def _wait_for(self, event, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("等待 SSM %s 超时" % event)
            message = self.poll(min(remaining, 0.1))
            if message and message["event"] == event:
                return message

    def prepare(self, timed_notes):
        self._send("prepare", notes=timed_notes)
        self.stats = self._wait_for("ready", 30)
        return self.stats

    def start(self, first_due):
        # Pass the deadline, rather than waiting in Python and adding IPC latency.
        # Go turns this one epoch timestamp into a monotonic timeline at receipt.
        first_due_unix_ns = time.time_ns() + round((first_due - time.perf_counter()) * 1e9)
        self._send("play", first_due_unix_ns=first_due_unix_ns)

    def stop(self):
        self._send("stop")
        self._wait_for("stopped", 5)

    def close(self):
        with self._write_lock:
            if self._closed:
                return
            self._closed = True
            self._process.stdin.close()  # EOF cancels playback and releases touches.
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        self._reader.join(timeout=1)
        self._process.stdout.close()
