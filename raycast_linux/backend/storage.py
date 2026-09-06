"""XDG-compliant data locations and a tiny atomic JSON store."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading


def data_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "raycast-linux")
    os.makedirs(d, exist_ok=True)
    return d


def state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    d = os.path.join(base, "raycast-linux")
    os.makedirs(d, exist_ok=True)
    return d


class JsonStore:
    """A single JSON document with atomic writes (tmp file + rename)."""

    def __init__(self, path: str, default: object):
        self.path = path
        self._default = default
        self._lock = threading.Lock()

    def load(self) -> object:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return copy.deepcopy(self._default)

    def save(self, data: object) -> None:
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix=".raycast-tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
