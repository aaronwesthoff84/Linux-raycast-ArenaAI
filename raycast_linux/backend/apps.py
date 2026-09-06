"""Installed application list (from .desktop files) + launching."""
from __future__ import annotations

import os
import subprocess
import time

from ..logic import desktop
from ..logic.fuzzy import fuzzy_score


class AppService:
    def __init__(self, dirs: list[str] | None = None) -> None:
        self.dirs = dirs or desktop.APPS_DIRS
        self._cache: list[dict] | None = None
        self._loaded_at = 0.0

    def list(self) -> list[dict]:
        now = time.time()
        if self._cache is None or now - self._loaded_at > 60:
            self._cache = desktop.load_desktop_files(self.dirs)
            self._loaded_at = now
        return self._cache

    def get(self, app_id: str) -> dict | None:
        return next((a for a in self.list() if a["id"] == app_id), None)

    def search(self, query: str, limit: int = 40) -> list[dict]:
        query = (query or "").strip()
        apps = self.list()
        if not query:
            return apps[:limit]
        scored: list[tuple[int, dict]] = []
        for a in apps:
            sc = fuzzy_score(query, a["name"])
            if sc is None and a["keywords"]:
                for kw in a["keywords"]:
                    ksc = fuzzy_score(query, kw)
                    if ksc is not None:
                        sc = sc if sc is not None else -100
                        sc = max(sc, ksc - 20)
            if sc is None and a["generic"]:
                gsc = fuzzy_score(query, a["generic"])
                if gsc is not None:
                    sc = (sc if sc is not None else -100)
                    sc = max(sc, gsc - 15)
            if sc is not None:
                scored.append((sc, a))
        scored.sort(key=lambda pair: -pair[0])
        return [a for _, a in scored[:limit]]

    def launch(self, app_id: str) -> dict:
        app = self.get(app_id)
        if not app:
            return {"ok": False, "message": f"App not found: {app_id}"}
        env, cmd = desktop.command_for(app)
        if not cmd:
            return {"ok": False, "message": f"Could not parse the Exec line of {app['name']}"}
        merged = dict(os.environ)
        for item in env:
            key, _, value = item.partition("=")
            merged[key] = value
        try:
            subprocess.Popen(
                cmd,
                env=merged,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            return {"ok": False, "message": f"Launch failed: {e}"}
        return {"ok": True, "message": f"Launched {app['name']}"}
