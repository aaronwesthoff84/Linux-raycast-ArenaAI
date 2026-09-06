"""Single-instance helpers: state file, liveness check, IPC over HTTP.

The running app writes ``~/.local/state/raycast-linux/api.json`` with its
pid + port. A second ``raycast-linux`` invocation talks to it (toggle)
instead of starting a second GUI.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .storage import state_dir

_API_FILE = "api.json"


def api_path() -> str:
    return os.path.join(state_dir(), _API_FILE)


def write_api(port: int) -> None:
    with open(api_path(), "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "port": port}, f)


def read_api() -> dict | None:
    try:
        with open(api_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("port"):
            return data
    except (OSError, ValueError):
        pass
    return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running_instance() -> dict | None:
    """Return {pid, port} if a healthy instance is up, else None."""
    info = read_api()
    if not info or not _pid_alive(int(info.get("pid", -1))):
        return None
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{info['port']}/api/health", timeout=1
        ) as r:
            data = json.load(r)
        if data.get("pid") == info.get("pid"):
            return info
    except Exception:  # noqa: BLE001
        pass
    return None


def api_post(path: str, payload: dict | None = None, timeout: float = 3.0) -> dict:
    info = read_api()
    if not info:
        raise RuntimeError("No raycast-linux instance is running")
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def remove_api() -> None:
    try:
        os.unlink(api_path())
    except OSError:
        pass
