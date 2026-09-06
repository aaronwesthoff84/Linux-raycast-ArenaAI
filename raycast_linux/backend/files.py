"""Home-directory file index with fuzzy search (Raycast-style "open file").

The index is built lazily in the foreground of the first search call
(or on demand via the UI), skipping hidden dirs and heavy build dirs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time

from ..logic.fuzzy import fuzzy_score

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".cache", ".npm", ".nvm", ".rustup", ".cargo", ".gradle", ".m2", ".cpan",
    "dist", "build", "target", "out", "coverage", ".next", ".nuxt", ".output",
    ".turbo", ".svelte-kit", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".local", ".config", ".var", ".icons", ".thumbnails",
    ".bundle", ".pub-cache", ".go", ".docker", "lost+found",
}

MAX_ENTRIES = 60_000


class FileIndex:
    def __init__(self, root: str | None = None) -> None:
        self.root = os.path.abspath(root or os.path.expanduser("~"))
        self.entries: list[dict] = []
        self.status = "idle"  # idle | building | ready | error
        self.last_built = 0.0
        self._lock = threading.Lock()

    def build(self) -> int:
        with self._lock:
            if self.status == "building":
                return len(self.entries)
            self.status = "building"
        entries: list[dict] = []
        try:
            stack = [self.root]
            while stack and len(entries) < MAX_ENTRIES:
                d = stack.pop()
                try:
                    with os.scandir(d) as it:
                        children = list(it)
                except OSError:
                    continue
                for child in children:
                    if len(entries) >= MAX_ENTRIES:
                        break
                    try:
                        if child.is_dir(follow_symlinks=False):
                            if child.name in SKIP_DIRS or child.name.startswith("."):
                                continue
                            stack.append(child.path)
                        else:
                            entries.append({
                                "path": child.path,
                                "name": child.name,
                                "rel": os.path.relpath(child.path, self.root),
                            })
                    except OSError:
                        continue
            self.entries = entries
            self.status = "ready"
            self.last_built = time.time()
        except Exception:  # noqa: BLE001
            self.status = "error"
        return len(self.entries)

    def ensure_built(self, force: bool = False) -> None:
        with self._lock:
            if self.status == "building":
                return
            if self.status == "ready" and not force:
                return
        self.build()

    def search(self, query: str, limit: int = 40) -> list[dict]:
        if not self.entries and self.status == "idle":
            self.ensure_built()
        query = (query or "").strip()
        if not query:
            return self.entries[:limit]
        scored: list[tuple[int, dict]] = []
        for e in self.entries:
            sc = fuzzy_score(query, e["name"])
            if sc is None:
                path_sc = fuzzy_score(query, e["rel"])
                sc = (path_sc - 25) if path_sc is not None else None
            if sc is not None:
                scored.append((sc, e))
        scored.sort(key=lambda pair: -pair[0])
        return [e for _, e in scored[:limit]]

    def open(self, path: str) -> dict:
        """Open a file with the default application."""
        if not os.path.isfile(path):
            return {"ok": False, "message": "Not a regular file"}
        uri = "file://" + path
        try:
            from gi.repository import Gio  # optional: only present on desktop Python
            Gio.AppInfo.launch_default_for_uri(uri, None)
            return {"ok": True, "message": f"Opened {os.path.basename(path)}"}
        except Exception:  # noqa: BLE001
            pass
        if shutil.which("xdg-open"):
            try:
                subprocess.Popen(
                    ["xdg-open", path],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"ok": True, "message": f"Opened {os.path.basename(path)}"}
            except OSError as e:
                return {"ok": False, "message": f"xdg-open failed: {e}"}
        return {"ok": False, "message": "No file opener available (install xdg-utils)"}
