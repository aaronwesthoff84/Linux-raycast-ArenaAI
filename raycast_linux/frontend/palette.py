"""The floating command palette: search input, category chips, results.

Keyboard:
  type            fuzzy search (calculator runs live)
  ">" + word      jump to a category (apps, files, clipboard, snippets,
                  windows, settings)
  ↑ / ↓           move selection
  Enter           run selected item
  Tab / Shift-Tab cycle categories
  Esc             close
"""
from __future__ import annotations

import os
import re

from gi.repository import Gdk, GLib, Gtk, Pango

from ..logic.calculator import try_calculate
from ..logic.units import try_convert

CATEGORIES = [
    ("general", "General"),
    ("chat", "Chat"),
    ("apps", "Apps"),
    ("files", "Files"),
    ("clipboard", "Clipboard"),
    ("snippets", "Snippets"),
    ("windows", "Windows"),
    ("settings", "Settings"),
]

_PREFIX_RE = re.compile(r"^>(\w+)\s*(.*)$")
_PREFIX_MAP = {
    "app": "apps", "apps": "apps", "application": "apps", "applications": "apps",
    "file": "files", "files": "files", "open": "files",
    "clip": "clipboard", "clips": "clipboard", "clipboard": "clipboard",
    "snippet": "snippets", "snippets": "snippets",
    "win": "windows", "window": "windows", "windows": "windows",
    "settings": "settings", "config": "settings",
    "chat": "chat", "ai": "chat", "hermes": "chat", "agent": "chat",
}

_WINDOW_ACTION_LABELS = {
    "left": ("Move to left half", "window-restore-symbolic"),
    "right": ("Move to right half", "window-restore-symbolic"),
    "top": ("Move to top half", "window-restore-symbolic"),
    "bottom": ("Move to bottom half", "window-restore-symbolic"),
    "center": ("Center window", "window-restore-symbolic"),
    "maximize": ("Maximize window", "window-maximize-symbolic"),
    "fullscreen": ("Fullscreen window", "window-maximize-symbolic"),
    "close": ("Close window", "window-close-symbolic"),
    "next": ("Focus next window", "go-next-symbolic"),
    "prev": ("Focus previous window", "go-previous-symbolic"),
}


class PaletteWindow(Gtk.Window):
    WIDTH = 680

    def __init__(self, app) -> None:
        super().__init__(application=app, title="Raycast Linux")
        self.app = app
        self.category = "general"
        self.results: list[dict] = []
        self.calc_row: dict | None = None
        self.selected = 0
        self._debounce = None
        self._stage_box: dict | None = None
        self._env: dict = {}
        self._base_status = ""

        self.set_default_size(self.WIDTH, 460)
        self.set_size_request(self.WIDTH, 240)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_stickiness(Gtk.WindowStickiness.GLOBAL)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_position(Gtk.WindowPosition.CENTER)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_css_classes(["palette-root"])
        self.set_child(root)

        # -- search input --------------------------------------------------
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        input_row.set_css_classes(["palette-input-row"])
        magnifier = Gtk.Image.new_from_icon_name("system-search-symbolic")
        magnifier.add_css_class("search-icon")
        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("Type to search…  ( > prefix for categories )")
        self.entry.set_css_classes(["palette-entry"])
        self.entry.connect("changed", self._on_entry_changed)
        input_row.append(magnifier)
        input_row.append(self.entry)
        root.append(input_row)

        # -- category chips -------------------------------------------------
        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        chips.set_css_classes(["palette-chips"])
        self._chips: dict[str, Gtk.Button] = {}
        for key, label in CATEGORIES:
            b = Gtk.Button(label=label)
            b.add_css_class("chip")
            b.set_on_focus(False)
            b.connect("clicked", self._on_chip_clicked, key)
            chips.append(b)
            self._chips[key] = b
        root.append(chips)

        # -- results list ------------------------------------------------------
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_css_classes(["palette-list"])
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_child(self.listbox)
        root.append(self.scroller)

        # -- status bar -----------------------------------------------------------
        self.status = Gtk.Label(label="", xalign=0.0)
        self.status.set_css_classes(["palette-status"])
        root.append(self.status)

        self.connect("key-press-event", self._on_key)
        self.connect("show", self._on_show)
        self._set_chip("general")
        self._set_status("Loading…")
        self.api_get("/api/env", on_result=self._on_env)
        self._refresh_results()

    # ------------------------------------------------------------------ API
    def api_get(self, path: str, params: dict | None = None, on_result=None) -> None:
        self.app.api.get(path, params=params, on_result=on_result)

    def api_post(self, path: str, payload: dict | None = None, on_result=None) -> None:
        self.app.api.post(path, json=payload or {}, on_result=on_result)

    # ------------------------------------------------------------------ env
    def _on_env(self, result, error):
        if error or not result:
            self._set_status(f"API unreachable: {error}")
            return
        self._env = result
        dm = (result.get("display_server") or "?").upper()
        wm = result.get("window_manager") or "?"
        self._base_status = f"{dm} · {wm}"
        if self.status.get_text().startswith("Loading"):
            self._set_status("")

    def _set_status(self, text: str) -> None:
        base = self._base_status
        self.status.set_text(f"{text}    {base}".strip() if base else text)

    # --------------------------------------------------------------- events
    def _on_show(self, _w) -> None:
        # Remember the focused window before we steal focus (X11 refocus).
        self.api_post("/api/windows/stash-active")
        self.entry.grab_focus()
        self._refresh_results()

    def _on_entry_changed(self, _entry) -> None:
        if self._debounce is not None:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(80, self._debounced_refresh)

    def _debounced_refresh(self) -> bool:
        self._debounce = None
        self._refresh_results()
        return False

    def _parse_query(self) -> tuple[str, str]:
        """Return (category, query). A leading '>' forces a category."""
        text = self.entry.get_text().strip()
        m = _PREFIX_RE.match(text)
        if m:
            cat = _PREFIX_MAP.get(m.group(1).lower(), self.category)
            self._set_chip(cat)
            return cat, m.group(2).strip()
        return self.category, text

    # ------------------------------------------------------------- results
    def _refresh_results(self) -> None:
        category, query = self._parse_query()
        if category == "windows":
            self.api_get("/api/windows", on_result=lambda r, e: self._apply([], self._static_window_items(r or {})))
            return
        if category == "settings":
            self._apply([], self._static_settings_items())
            return
        if category == "chat":
            q_label = f": {query}" if query else ""
            self._apply([], [{
                "kind": "chat", "id": "open-chat", "title": f"Chat with Hermes{q_label}",
                "subtitle": "Ask Hermes Agent (Enter to open chat window)",
                "icon": "user-available-symbolic",
            }])
            return

        limit = 8 if category == "general" else 40

        def on_all(apps_r, clips_r, snip_r, files_r):
            items: list[dict] = []
            calc = self._calc_items(query)
            if category in ("general", "files") and calc:
                items.extend(calc)
            if category in ("general", "apps"):
                items.extend(self._app_items((apps_r or {}).get("items", [])))
            if category in ("general", "files"):
                items.extend(self._file_items((files_r or {}).get("items", [])))
            if category in ("general", "snippets"):
                items.extend(self._snippet_items((snip_r or {}).get("items", [])))
            if category in ("general", "clipboard"):
                items.extend(self._clip_items((clips_r or {}).get("items", [])))
            if not items:
                items.append(self._command_item("open-settings", "Open settings", "Preferences, snippets, shortcuts"))
            self._apply(calc, items)

        # One batch per search: a newer search supersedes this batch, so
        # stale responses are dropped by identity instead of mixed in.
        box: dict[str, tuple] = {"apps": None, "clips": None, "snips": None, "files": None}
        self._stage_box = box

        def stage(name: str):
            def cb(result, _error):
                if self._stage_box is not box:
                    return  # superseded by a newer search
                box[name] = (result, _error)
                if all(v is not None for v in box.values()):
                    self._stage_box = None
                    on_all(box["apps"][0], box["clips"][0], box["snips"][0], box["files"][0])
            return cb

        self.api_get("/api/apps", params={"query": query, "limit": limit}, on_result=stage("apps"))
        self.api_get("/api/clipboard", params={"query": query}, on_result=stage("clips"))
        self.api_get("/api/snippets", params={"query": query}, on_result=stage("snips"))
        self.api_get("/api/files", params={"query": query, "limit": limit}, on_result=stage("files"))

    def _apply(self, calc: list[dict], items: list[dict]) -> None:
        self.calc_row = calc[0] if calc else None
        self.results = items
        self.selected = 0
        self._rebuild_list()
        self._set_status(f"{len(items)} result{'s' if len(items) != 1 else ''}")

    def _rebuild_list(self) -> None:
        self.listbox.remove_all()
        if self.calc_row is not None:
            self.listbox.append(self._make_row(self.calc_row))
        for item in self.results:
            self.listbox.append(self._make_row(item))
        self._sync_row_styles()
        self._ensure_visible()

    # -------------------------------------------------------- item builders
    def _calc_items(self, query: str) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        converted = try_convert(query)
        if converted:
            return [{
                "kind": "calc", "id": "convert", "title": converted,
                "subtitle": f"{query}  →  copy", "icon": "accessories-calculator-symbolic",
            }]
        result = try_calculate(query)
        if result is None:
            return []
        return [{
            "kind": "calc", "id": "result", "title": result,
            "subtitle": f"{query}  →  copy", "icon": "accessories-calculator-symbolic",
        }]

    @staticmethod
    def _app_items(apps: list[dict]) -> list[dict]:
        return [{
            "kind": "app", "id": a["id"], "title": a["name"],
            "subtitle": a.get("comment") or a.get("generic") or "Application",
            "icon": a.get("icon") or "application-x-executable-symbolic",
        } for a in apps]

    @staticmethod
    def _file_items(files: list[dict]) -> list[dict]:
        return [{
            "kind": "file", "id": f["path"], "title": f["name"],
            "subtitle": f.get("rel", ""), "icon": "text-x-generic-symbolic",
        } for f in files]

    @staticmethod
    def _clip_items(items: list[dict]) -> list[dict]:
        out = []
        for i in items:
            preview = i["text"].replace("\n", " ⏎ ")
            if len(preview) > 80:
                preview = preview[:77] + "…"
            out.append({
                "kind": "clip", "id": i["id"], "title": preview,
                "subtitle": f"{i['chars']} chars · {i['lines']} line{'s' if i['lines'] != 1 else ''}",
                "icon": "edit-copy-symbolic", "text": i["text"],
            })
        return out

    @staticmethod
    def _snippet_items(items: list[dict]) -> list[dict]:
        return [{
            "kind": "snippet", "id": s["id"], "title": s["name"],
            "subtitle": s["content"].replace("\n", " ⏎ ")[:80],
            "icon": "font-x-generic-symbolic",
        } for s in items]

    def _command_item(self, id_: str, title: str, subtitle: str) -> dict:
        return {"kind": "command", "id": id_, "title": title, "subtitle": subtitle,
                "icon": "emblem-system-symbolic"}

    def _static_window_items(self, info: dict) -> list[dict]:
        items = []
        for action in info.get("actions", []):
            label, icon = _WINDOW_ACTION_LABELS.get(action, (action.title(), "window-restore-symbolic"))
            items.append({"kind": "window", "id": action, "title": label,
                          "subtitle": info.get("provider", ""), "icon": icon})
        if not items:
            items.append({"kind": "command", "id": "no-window-mgmt",
                          "title": "Window tiling unavailable here",
                          "subtitle": info.get("hint", "No provider for this session"),
                          "icon": "dialog-warning-symbolic"})
        return items

    def _static_settings_items(self) -> list[dict]:
        return [
            self._command_item("open-chat", "Open agent chat", "Chat with Hermes agent"),
            self._command_item("open-setup", "Setup and diagnostics", "System check, autostart, updates"),
            self._command_item("open-settings", "Open settings", "Preferences, snippets, shortcuts"),
            self._command_item("clear-clipboard", "Clear clipboard history", "Delete all stored clipboard items"),
            self._command_item("refresh-files", "Rebuild file index", "Scan $HOME again"),
            self._command_item("register-shortcut", "Register global shortcut (portal)", "Super+Space via xdg-desktop-portal"),
            self._command_item("about", "About raycast-linux", "Version and paths"),
        ]

    # ----------------------------------------------------------------- rows
    def _make_row(self, item: dict) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.add_css_class("result-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(7)
        box.set_margin_bottom(7)

        icon_name = item.get("icon") or "application-x-executable-symbolic"
        if icon_name.startswith("/") and os.path.exists(icon_name):
            img = Gtk.Image.new_from_file(icon_name)
        else:
            img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(20)
        img.add_css_class("row-icon")

        stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label=item["title"], xalign=0.0, ellipsize=Pango.EllipsizeMode.END)
        title.add_css_class("row-title")
        subtitle = Gtk.Label(label=item.get("subtitle", ""), xalign=0.0, ellipsize=Pango.EllipsizeMode.END)
        subtitle.add_css_class("row-subtitle")
        stack.append(title)
        stack.append(subtitle)

        kind = Gtk.Label(label=item["kind"].upper(), xalign=1.0)
        kind.add_css_class("row-kind")

        box.append(img)
        box.append(stack)
        box.append(kind)
        row.set_child(box)
        return row

    def _set_chip(self, category: str) -> None:
        for key, b in self._chips.items():
            if key == category:
                b.add_css_class("active")
            else:
                b.remove_css_class("active")
        self.category = category

    def _on_chip_clicked(self, _b, key: str) -> None:
        self.entry.set_text("")
        self._set_chip(key)
        self.entry.grab_focus()
        self._refresh_results()

    def _cycle_category(self, delta: int) -> None:
        keys = [k for k, _ in CATEGORIES]
        idx = keys.index(self.category)
        self._set_chip(keys[(idx + delta) % len(keys)])
        self._refresh_results()

    # ------------------------------------------------------------- keyboard
    def _on_key(self, _w, event) -> bool:
        keyval = event.keyval
        if keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        if keyval == Gdk.KEY_Down:
            self._move(1)
            return True
        if keyval == Gdk.KEY_Up:
            self._move(-1)
            return True
        if keyval == Gdk.KEY_Page_Down:
            self._move(5)
            return True
        if keyval == Gdk.KEY_Page_Up:
            self._move(-5)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._activate_selected()
            return True
        if keyval == Gdk.KEY_Tab:
            delta = 1 if not (event.state & Gdk.ModifierType.SHIFT_MASK) else -1
            self._cycle_category(delta)
            return True
        return False

    def _move(self, delta: int) -> None:
        n = self.listbox.get_children().get_n_children()
        if n == 0:
            return
        self.selected = (self.selected + delta) % n
        self._sync_row_styles()
        self._ensure_visible()

    def _sync_row_styles(self) -> None:
        child = self.listbox.get_children().get_first()
        i = 0
        while child is not None:
            if i == self.selected:
                child.add_css_class("selected")
            else:
                child.remove_css_class("selected")
            child = child.get_next_sibling()
            i += 1

    def _ensure_visible(self) -> None:
        row = self.listbox.get_row_at_index(self.selected)
        if row is None:
            return
        va = self.scroller.get_vadjustment()
        target = self.selected * 44 - va.get_page_size() // 2
        va.set_value(max(0.0, min(target, va.get_upper() - va.get_page_size())))

    def _selected_item(self) -> dict | None:
        idx = self.selected
        if self.calc_row is not None:
            if idx == 0:
                return self.calc_row
            idx -= 1
        if 0 <= idx < len(self.results):
            return self.results[idx]
        return None

    def _activate_selected(self) -> None:
        item = self._selected_item()
        if not item:
            return
        kind = item["kind"]
        if kind == "calc":
            self.api_post("/api/clipboard/copy", {"text": item["title"]},
                          on_result=lambda r, e: self._flash("Copied " + item["title"]))
        elif kind == "app":
            self.api_post("/api/apps/launch", {"id": item["id"]},
                          on_result=lambda r, e: self._flash((r or {}).get("message", "Launched")))
            self.hide()
        elif kind == "file":
            self.api_post("/api/files/open", {"path": item["id"]},
                          on_result=lambda r, e: self._flash((r or {}).get("message", "Opened")))
            self.hide()
        elif kind == "clip":
            self.api_post("/api/clipboard/copy", {"text": item["text"]},
                          on_result=lambda r, e: self._flash("Copied to clipboard"))
        elif kind == "snippet":
            self._expand_snippet(item)
        elif kind == "window":
            self._run_window_action(item["id"])
        elif kind == "command":
            self._run_command(item["id"])
        elif kind == "chat":
            self.app.open_chat()
            self.hide()

    # -------------------------------------------------------- special flows
    def _expand_snippet(self, item: dict) -> None:
        """Hide → return focus to the previous window → type the snippet."""
        self.hide()
        self.api_post("/api/windows/refocus")

        def do_expand() -> bool:
            self.api_post(f"/api/snippets/{item['id']}/expand",
                          on_result=lambda r, e: self._flash_after((r or {}).get("message", "Snippet expanded")))
            return False

        GLib.timeout_add(350, do_expand)

    def _run_window_action(self, action: str) -> None:
        self.hide()
        self.api_post("/api/windows/action", {"action": action})
        self.api_post("/api/windows/refocus",
                      on_result=lambda r, e: self._flash_after((r or {}).get("message", "")))

    def _run_command(self, id_: str) -> None:
        if id_ == "open-settings":
            self.app.open_settings()
            self.hide()
        elif id_ == "open-setup":
            self.app.open_setup()
            self.hide()
        elif id_ == "open-chat":
            self.app.open_chat()
            self.hide()
        elif id_ == "clear-clipboard":
            self.api_post("/api/clipboard/clear",
                          on_result=lambda r, e: self._flash("Clipboard history cleared"))
            self._refresh_results()
        elif id_ == "refresh-files":
            self._set_status("Rebuilding file index…")
            self.api_get("/api/files", params={"query": "", "refresh": True},
                         on_result=lambda r, e: self._flash(f"File index: {(r or {}).get('count', 0)} files"))
        elif id_ == "register-shortcut":
            self.api_post("/api/shortcuts", {"shortcut": "super+space"},
                          on_result=lambda r, e: self._flash((r or {}).get("message", "Shortcut updated")))
        elif id_ == "about":
            self.app.notify("raycast-linux",
                            f"v{self.app.version()} · GTK4 + FastAPI · data: ~/.local/share/raycast-linux")
        elif id_ == "no-window-mgmt":
            self.app.notify("Window tiling", self._env.get("window_hint", "Not available on this session"))

    # ----------------------------------------------------------- feedback
    def _flash(self, message: str) -> None:
        if not message:
            return
        self._set_status(message)
        self.app.notify("raycast-linux", message)

    def _flash_after(self, message: str) -> None:
        if message:
            self.app.notify("raycast-linux", message)
