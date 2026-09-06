"""FastAPI backend — the HTTP API consumed by the GTK frontend and CLI.

The server runs in-process (a daemon thread with its own asyncio loop), so
the whole app is one binary: ``raycast-linux``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..platform import detect, typing
from ..version import __version__
from . import storage
from .apps import AppService
from .clipboard import ClipboardService
from .files import FileIndex
from .shortcuts import GlobalShortcutPortal
from .snippets import SnippetService
from .windows import detect_provider

log = logging.getLogger("raycast-linux.api")


# -- request models (module level so FastAPI can resolve the types) ------
class TextBody(BaseModel):
    text: str


class LaunchBody(BaseModel):
    id: str


class OpenBody(BaseModel):
    path: str


class ActionBody(BaseModel):
    action: str


class SnippetBody(BaseModel):
    name: str | None = None
    content: str | None = None


class ShortcutBody(BaseModel):
    shortcut: str = "super+space"


class ServiceHub:
    """Owns every service instance. One hub per running app."""

    def __init__(self) -> None:
        self.apps = AppService()
        self.snippets = SnippetService()
        self.clipboard = ClipboardService()
        self.files = FileIndex()
        self.windows = detect_provider()
        self.portal = GlobalShortcutPortal()
        self.started = time.time()
        self.on_palette_toggle = None  # set by the frontend (thread-safe call)


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def build_app(hub: ServiceHub) -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async def clipboard_poller():
            while True:
                try:
                    hub.clipboard.poll_once()
                except Exception:  # noqa: BLE001
                    log.debug("clipboard poll failed", exc_info=True)
                await asyncio.sleep(1.0)

        task = asyncio.create_task(clipboard_poller())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="raycast-linux API", version=__version__, lifespan=lifespan)

    # -- meta ----------------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "pid": os.getpid(),
            "version": __version__,
            "uptime": round(time.time() - hub.started, 1),
            "display_server": detect.display_server(),
            "window_manager": detect.window_manager(),
        }

    @app.get("/api/env")
    def env() -> dict:
        info = detect.env_info()
        info.update({
            "version": __version__,
            "data_dir": storage.data_dir(),
            "state_dir": storage.state_dir(),
            "window_provider": hub.windows.name,
            "window_hint": hub.windows.hint,
            "file_index": {"status": hub.files.status, "count": len(hub.files.entries)},
        })
        return info

    # -- apps ----------------------------------------------------------------
    @app.get("/api/apps")
    def apps_list(query: str = "") -> dict:
        return {"items": hub.apps.search(query, 40)}

    @app.post("/api/apps/launch")
    def apps_launch(body: LaunchBody) -> dict:
        return hub.apps.launch(body.id)

    # -- files -----------------------------------------------------------------
    @app.get("/api/files")
    def files_search(query: str = "", limit: int = 40, refresh: bool = False) -> dict:
        hub.files.ensure_built(force=refresh)
        return {
            "items": hub.files.search(query, min(max(limit, 1), 200)),
            "status": hub.files.status,
            "count": len(hub.files.entries),
        }

    @app.post("/api/files/open")
    def files_open(body: OpenBody) -> dict:
        if not os.path.isfile(body.path):
            raise HTTPException(status_code=404, detail="Not a regular file")
        return hub.files.open(body.path)

    # -- clipboard ----------------------------------------------------------------
    @app.get("/api/clipboard")
    def clipboard_list(query: str = "") -> dict:
        return {"items": hub.clipboard.search(query, 30)}

    @app.get("/api/clipboard/{item_id}")
    def clipboard_get(item_id: str) -> dict:
        item = hub.clipboard.get_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Clipboard item not found")
        return item

    @app.post("/api/clipboard/copy")
    def clipboard_copy(body: TextBody) -> dict:
        return hub.clipboard.copy(body.text)

    @app.post("/api/clipboard/clear")
    def clipboard_clear() -> dict:
        return hub.clipboard.clear()

    # -- snippets --------------------------------------------------------------
    @app.get("/api/snippets")
    def snippets_list(query: str = "") -> dict:
        return {"items": hub.snippets.search(query, 30)}

    @app.post("/api/snippets")
    def snippets_create(body: SnippetBody) -> dict:
        try:
            return hub.snippets.create(body.name or "", body.content or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.put("/api/snippets/{snippet_id}")
    def snippets_update(snippet_id: str, body: SnippetBody) -> dict:
        try:
            updated = hub.snippets.update(snippet_id, body.name, body.content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not updated:
            raise HTTPException(status_code=404, detail="Snippet not found")
        return updated

    @app.delete("/api/snippets/{snippet_id}")
    def snippets_delete(snippet_id: str) -> dict:
        if not hub.snippets.delete(snippet_id):
            raise HTTPException(status_code=404, detail="Snippet not found")
        return {"ok": True, "message": "Snippet deleted"}

    @app.post("/api/snippets/{snippet_id}/expand")
    def snippets_expand(snippet_id: str) -> dict:
        return hub.snippets.expand(snippet_id)

    # -- windows ------------------------------------------------------------------
    @app.get("/api/windows")
    def windows_info() -> dict:
        return {
            "provider": hub.windows.name,
            "actions": hub.windows.actions(),
            "hint": hub.windows.hint,
        }

    @app.post("/api/windows/action")
    def windows_action(body: ActionBody) -> dict:
        return hub.windows.run(body.action)

    @app.post("/api/windows/stash-active")
    def windows_stash() -> dict:
        hub.windows.stash_active()
        return {"ok": True}

    @app.post("/api/windows/refocus")
    def windows_refocus() -> dict:
        return hub.windows.refocus()

    # -- global shortcut -----------------------------------------------------------
    @app.get("/api/shortcuts")
    def shortcuts_status() -> dict:
        return hub.portal.status()

    @app.post("/api/shortcuts")
    def shortcuts_register(body: ShortcutBody) -> dict:
        return hub.portal.register(body.shortcut)

    @app.delete("/api/shortcuts")
    def shortcuts_unregister() -> dict:
        return hub.portal.unregister()

    # -- palette control -------------------------------------------------------------
    @app.post("/api/palette/toggle")
    def palette_toggle() -> dict:
        cb = hub.on_palette_toggle
        if cb is None:
            return {"ok": False, "message": "Frontend not running (server-only mode)"}
        cb()
        return {"ok": True, "message": "Palette toggled"}

    return app


def run_server(host: str = "127.0.0.1", port: int | None = None,
               hub: ServiceHub | None = None, block: bool = True) -> tuple[ServiceHub, int]:
    """Start the API server. Returns (hub, actual_port)."""
    hub = hub or ServiceHub()
    if port in (None, 0):
        port = _pick_free_port()
    app = build_app(hub)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    if block:
        server.run()
    else:
        threading.Thread(
            target=server.run, daemon=True, name="raycast-linux-api",
        ).start()
    return hub, port
