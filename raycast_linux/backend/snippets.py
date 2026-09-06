"""Text snippets: stored locally, expanded by typing into the focused window.

Expansion strategy on Wayland:
  1. ``wtype`` types into whatever is focused (frontend hides the palette
     and returns focus to the previous window first).
  2. If no typing tool is available, fall back to copying the snippet so
     the user can paste it — never a dead end.
"""
from __future__ import annotations

import os
import time
import uuid

from ..logic.fuzzy import fuzzy_score
from ..platform import typing
from .storage import JsonStore, data_dir

_DEFAULT_SNIPPETS = [
    {"name": "email", "content": "you@example.com"},
    {"name": "sig", "content": "Best regards,\nYour Name"},
    {"name": "json", "content": '{"key": "value"}'},
]


def _seed(items: list[dict]) -> list[dict]:
    if not items:
        for s in _DEFAULT_SNIPPETS:
            items.append({
                "id": uuid.uuid4().hex[:8],
                "name": s["name"],
                "content": s["content"],
                "created": time.time(),
                "updated": time.time(),
            })
    return items


class SnippetService:
    def __init__(self) -> None:
        self.store = JsonStore(os.path.join(data_dir(), "snippets.json"), {"snippets": []})

    def list(self) -> list[dict]:
        data = self.store.load()
        items = data.get("snippets")
        if not items:
            items = _seed([])
            data["snippets"] = items
            self.store.save(data)
        return items

    def get(self, snippet_id: str) -> dict | None:
        return next((s for s in self.list() if s["id"] == snippet_id), None)

    def create(self, name: str, content: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("Snippet needs a name")
        snip = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "content": content,
            "created": time.time(),
            "updated": time.time(),
        }
        data = self.store.load()
        data.setdefault("snippets", []).append(snip)
        self.store.save(data)
        return snip

    def update(self, snippet_id: str, name: str | None = None,
               content: str | None = None) -> dict | None:
        snip = self.get(snippet_id)
        if not snip:
            return None
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Snippet name cannot be empty")
            snip["name"] = name
        if content is not None:
            snip["content"] = content
        snip["updated"] = time.time()
        data = self.store.load()
        for s in data["snippets"]:
            if s["id"] == snippet_id:
                s.update(snip)
        self.store.save(data)
        return snip

    def delete(self, snippet_id: str) -> bool:
        data = self.store.load()
        before = len(data.get("snippets", []))
        data["snippets"] = [s for s in data.get("snippets", []) if s["id"] != snippet_id]
        if len(data["snippets"]) == before:
            return False
        self.store.save(data)
        return True

    def search(self, query: str, limit: int = 30) -> list[dict]:
        query = (query or "").strip()
        snippets = self.list()
        if not query:
            return snippets[:limit]
        scored = []
        for s in snippets:
            best = None
            for field in (s["name"], s["content"][:60]):
                sc = fuzzy_score(query, field)
                if sc is not None and (best is None or sc > best):
                    best = sc
            if best is not None:
                scored.append((best, s))
        scored.sort(key=lambda pair: -pair[0])
        return [s for _, s in scored[:limit]]

    def expand(self, snippet_id: str) -> dict:
        snip = self.get(snippet_id)
        if not snip:
            return {"ok": False, "message": "Snippet not found", "method": "none"}
        ok, detail = typing.type_text(snip["content"])
        if ok:
            return {"ok": True, "message": f"Typed “{snip['name']}” into the focused window", "method": detail}
        if typing.clipboard_set(snip["content"]):
            return {
                "ok": True,
                "message": f"Auto-type unavailable ({detail}) — “{snip['name']}” copied, paste with Ctrl+V",
                "method": "clipboard",
            }
        return {"ok": False, "message": f"Could not expand: {detail}", "method": "none"}
