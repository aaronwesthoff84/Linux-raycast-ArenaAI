"""Clipboard history: poll the system clipboard, keep the last N items.

Text only (images are a roadmap item). Works with wl-clipboard on Wayland
and xclip/xsel on X11; if no tool is present the history simply stays
empty and the UI says why.
"""
from __future__ import annotations

import hashlib
import os
import time

from ..logic.fuzzy import fuzzy_score
from ..platform import typing
from .storage import JsonStore, data_dir


class ClipboardService:
    def __init__(self, cap: int = 200) -> None:
        self.cap = cap
        self.store = JsonStore(os.path.join(data_dir(), "clipboard.json"), {"items": []})
        self._last_hash: str | None = None

    # -- polling ----------------------------------------------------------
    def poll_once(self) -> bool:
        """Check the system clipboard; record a new item if it changed."""
        text = typing.clipboard_get()
        if text is None:
            return False
        if not text.strip():
            return False
        h = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
        if h == self._last_hash:
            return False
        self._last_hash = h
        items = self._load()
        items = [i for i in items if i.get("hash") != h]  # dedupe: move to top
        items.insert(0, {
            "id": h[:12],
            "hash": h,
            "text": text[:10_000],
            "ts": time.time(),
            "chars": len(text),
            "lines": text.count("\n") + 1,
        })
        self.store.save({"items": items[: self.cap]})
        return True

    # -- api --------------------------------------------------------------
    def _load(self) -> list[dict]:
        return self.store.load().get("items", [])

    def get_item(self, item_id: str) -> dict | None:
        return next((i for i in self._load() if i["id"] == item_id), None)

    def search(self, query: str, limit: int = 30) -> list[dict]:
        query = (query or "").strip()
        items = self._load()
        if not query:
            return items[:limit]
        q = query.lower()
        exact = [i for i in items if q in i["text"].lower()]
        if exact:
            return exact[:limit]
        scored = []
        for i in items:
            sc = fuzzy_score(query, i["text"][:200])
            if sc is not None:
                scored.append((sc, i))
        scored.sort(key=lambda pair: -pair[0])
        return [i for _, i in scored[:limit]]

    def copy(self, text: str) -> dict:
        if typing.clipboard_set(text):
            self.poll_once()
            return {"ok": True, "message": "Copied to clipboard"}
        return {"ok": False, "message": "No clipboard tool available (install wl-clipboard or xclip)"}

    def clear(self) -> dict:
        self.store.save({"items": []})
        self._last_hash = None
        return {"ok": True, "message": "Clipboard history cleared"}
