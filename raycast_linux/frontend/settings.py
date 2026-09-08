"""Settings window: platform info, global shortcut, snippets, clipboard, files."""
from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango


def _label(text: str, css: str | None = None) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0.0, wrap=True)
    lbl.set_lines(-1)
    if css:
        lbl.add_css_class(css)
    return lbl


def _section(title: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.add_css_class("settings-section")
    box.append(_label(title, "settings-title"))
    return box


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app) -> None:
        super().__init__(application=app, title="Raycast Linux: Settings")
        self.app = app
        self.set_default_size(560, 640)
        self._selected_snippet: str | None = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.add_css_class("settings-root")
        root.set_margin_start(16)
        root.set_margin_end(16)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        self.set_child(root)

        # -- platform -------------------------------------------------------
        plat = _section("Platform")
        self._plat_grid = Gtk.Grid()
        self._plat_grid.set_row_spacing(3)
        self._plat_grid.set_column_spacing(14)
        for i, key in enumerate(["display_server", "window_manager", "window_provider",
                                 "data_dir", "version"]):
            self._plat_grid.append(_label(key.replace("_", " "), "settings-key"))
            lbl = _label("…", "settings-value")
            self._plat_grid.append(lbl)
            setattr(self, f"_plat_{key}", lbl)
        plat.append(self._plat_grid)
        root.append(plat)

        # -- global shortcut ----------------------------------------------------
        sc = _section("Global shortcut")
        self._sc_status = _label("not registered", "settings-value")
        sc.append(self._sc_status)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._sc_entry = Gtk.Entry()
        self._sc_entry.set_text("super+space")
        self._sc_entry.set_hexpand(True)
        btn = Gtk.Button(label="Register (portal)")
        btn.connect("clicked", self._on_register_shortcut)
        row.append(self._sc_entry)
        row.append(btn)
        sc.append(row)
        sc.append(_label(
            "Compositor fallback (works everywhere): bind the key to run "
            "“raycast-linux toggle”.  sway: bindsym $mod+space exec raycast-linux   ·   "
            "Hyprland: bind =SUPER,SPC, exec, raycast-linux", "settings-hint"))
        root.append(sc)

        # -- snippets ---------------------------------------------------------------
        sn = _section("Snippets")
        self._snip_list = Gtk.ListBox()
        self._snip_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._snip_list.set_css_classes(["snip-list"])
        self._snip_list.connect("row-selected", self._on_snip_selected)
        swrap = Gtk.ScrolledWindow()
        swrap.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        swrap.set_min_content_height(120)
        swrap.set_child(self._snip_list)
        sn.append(swrap)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._snip_name = Gtk.Entry()
        self._snip_name.set_placeholder_text("snippet name (e.g. email)")
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_left_margin(8)
        tv.set_right_margin(8)
        twrap = Gtk.ScrolledWindow()
        twrap.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        twrap.set_min_content_height(80)
        twrap.set_child(tv)
        self._snip_text = tv
        form.append(self._snip_name)
        form.append(twrap)
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save = Gtk.Button(label="Save")
        save.connect("clicked", self._on_snip_save)
        new = Gtk.Button(label="New")
        new.connect("clicked", self._on_snip_new)
        delete = Gtk.Button(label="Delete")
        delete.connect("clicked", self._on_snip_delete)
        btns.append(save)
        btns.append(new)
        btns.append(delete)
        form.append(btns)
        sn.append(form)
        root.append(sn)

        # -- clipboard ------------------------------------------------------------------
        cb = _section("Clipboard")
        crow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._clip_count = _label("", "settings-value")
        clear = Gtk.Button(label="Clear history")
        clear.connect("clicked", self._on_clip_clear)
        crow.append(self._clip_count)
        crow.append(clear)
        cb.append(crow)
        root.append(cb)

        # -- files --------------------------------------------------------------------------
        fi = _section("File index")
        frow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._files_status = _label("", "settings-value")
        refresh = Gtk.Button(label="Rebuild")
        refresh.connect("clicked", self._on_files_refresh)
        frow.append(self._files_status)
        frow.append(refresh)
        fi.append(frow)
        root.append(fi)

        # -- chat / ai --------------------------------------------------------------
        chat_sec = _section("Chat & AI (Hermes Agent)")
        self._chat_status = _label("", "settings-value")
        chat_sec.append(self._chat_status)

        cgrid = Gtk.Grid()
        cgrid.set_row_spacing(6)
        cgrid.set_column_spacing(10)

        cgrid.attach(_label("Endpoint", "settings-key"), 0, 0, 1, 1)
        self._chat_endpoint = Gtk.Entry()
        self._chat_endpoint.set_hexpand(True)
        self._chat_endpoint.set_placeholder_text("http://localhost:8000/v1")
        cgrid.attach(self._chat_endpoint, 1, 0, 1, 1)

        cgrid.attach(_label("Model", "settings-key"), 0, 1, 1, 1)
        self._chat_model = Gtk.Entry()
        self._chat_model.set_hexpand(True)
        self._chat_model.set_placeholder_text("hermes-3-llama-3.1-8b")
        cgrid.attach(self._chat_model, 1, 1, 1, 1)

        cgrid.attach(_label("API Key", "settings-key"), 0, 2, 1, 1)
        self._chat_api_key = Gtk.Entry()
        self._chat_api_key.set_hexpand(True)
        self._chat_api_key.set_visibility(False)
        self._chat_api_key.set_placeholder_text("Optional or masked")
        cgrid.attach(self._chat_api_key, 1, 2, 1, 1)

        chat_sec.append(cgrid)

        crow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_chat = Gtk.Button(label="Save Chat Config")
        save_chat.connect("clicked", self._on_chat_save)
        crow.append(save_chat)
        chat_sec.append(crow)
        root.append(chat_sec)

        self._load_all()

    # ------------------------------------------------------------------ api
    def api_get(self, path: str, params: dict | None = None, on_result=None) -> None:
        self.app.api.get(path, params=params, on_result=on_result)

    def api_post(self, path: str, payload: dict | None = None, on_result=None) -> None:
        self.app.api.post(path, json=payload or {}, on_result=on_result)

    def api_put(self, path: str, payload: dict | None = None, on_result=None) -> None:
        self.app.api.put(path, json=payload or {}, on_result=on_result)

    def api_delete(self, path: str, on_result=None) -> None:
        self.app.api.delete(path, on_result=on_result)

    def _notify(self, message: str) -> None:
        self.app.notify("raycast-linux", message)

    # ----------------------------------------------------------------- load
    def _load_all(self) -> None:
        self.api_get("/api/env", on_result=lambda r, e: self._on_env(r))
        self.api_get("/api/shortcuts", on_result=lambda r, e: self._on_shortcuts(r))
        self.api_get("/api/snippets", on_result=lambda r, e: self._on_snippets(r))
        self.api_get("/api/clipboard", on_result=lambda r, e: self._on_clipboard(r))
        self.api_get("/api/files", params={"query": "", "limit": 1},
                     on_result=lambda r, e: self._on_files(r))
        self.api_get("/api/chat/config", on_result=lambda r, e: self._on_chat_config(r))

    def _on_env(self, r: dict | None) -> None:
        if not r:
            return
        for key in ["display_server", "window_manager", "window_provider", "data_dir", "version"]:
            lbl = getattr(self, f"_plat_{key}", None)
            if lbl is not None:
                lbl.set_text(str(r.get(key, "—")))

    def _on_shortcuts(self, r: dict | None) -> None:
        if not r:
            return
        if r.get("registered"):
            self._sc_status.set_text(f"registered: {r.get('shortcut')}  (id {r.get('id')})")
        else:
            self._sc_status.set_text("not registered — use Register or a compositor binding")

    def _on_snippets(self, r: dict | None) -> None:
        self._snip_list.remove_all()
        items = (r or {}).get("items", [])
        self._snips = items
        for s in items:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            name = Gtk.Label(label=s["name"], xalign=0.0)
            name.add_css_class("row-title")
            preview = Gtk.Label(
                label=s["content"].replace("\n", " ⏎ ")[:60], xalign=0.0,
                ellipsize=Pango.EllipsizeMode.END)
            preview.add_css_class("row-subtitle")
            box.append(name)
            box.append(preview)
            row.set_child(box)
            row.set_data("id", s["id"])
            self._snip_list.append(row)

    def _on_clipboard(self, r: dict | None) -> None:
        count = len((r or {}).get("items", []))
        self._clip_count.set_text(f"{count} items stored (cap 200)")

    def _on_files(self, r: dict | None) -> None:
        if not r:
            return
        self._files_status.set_text(
            f"status: {r.get('status')} · {r.get('count', 0)} files indexed")

    # ---------------------------------------------------------------- actions
    def _on_register_shortcut(self, _b) -> None:
        shortcut = self._sc_entry.get_text().strip() or "super+space"
        self._sc_status.set_text(f"registering {shortcut}…")
        self.api_post("/api/shortcuts", {"shortcut": shortcut}, on_result=lambda r, e: (
            self._sc_status.set_text((r or {}).get("message", str(e))),
            self._notify((r or {}).get("message", "shortcut registration failed"))))

    def _on_snip_selected(self, _lb, row) -> None:
        if row is None:
            return
        sid = row.get_data("id")
        for s in getattr(self, "_snips", []):
            if s["id"] == sid:
                self._selected_snippet = sid
                self._snip_name.set_text(s["name"])
                self._snip_text.get_buffer().set_text(s["content"])
                break

    def _on_snip_new(self, _b) -> None:
        self._selected_snippet = None
        self._snip_name.set_text("")
        self._snip_text.get_buffer().set_text("")
        self._snip_name.grab_focus()

    def _on_snip_save(self, _b) -> None:
        name = self._snip_name.get_text().strip()
        content = self._snip_text.get_buffer().get_text(
            self._snip_text.get_buffer().get_start_iter(),
            self._snip_text.get_buffer().get_end_iter(), False)
        if not name:
            self._notify("Snippet name is empty")
            return
        if self._selected_snippet:
            self.api_put(f"/api/snippets/{self._selected_snippet}",
                         {"name": name, "content": content},
                         on_result=lambda r, e: self._after_snip_change("Snippet updated", e))
        else:
            self.api_post("/api/snippets", {"name": name, "content": content},
                          on_result=lambda r, e: self._after_snip_change("Snippet created", e))

    def _after_snip_change(self, message: str, error) -> None:
        if error:
            self._notify(str(error))
        else:
            self._notify(message)
        self.api_get("/api/snippets", on_result=lambda r, e: self._on_snippets(r))

    def _on_snip_delete(self, _b) -> None:
        if not self._selected_snippet:
            return
        sid = self._selected_snippet
        self._selected_snippet = None
        self.api_delete(f"/api/snippets/{sid}",
                        on_result=lambda r, e: self._after_snip_change("Snippet deleted", e))

    def _on_clip_clear(self, _b) -> None:
        self.api_post("/api/clipboard/clear", on_result=lambda r, e: (
            self.api_get("/api/clipboard", on_result=lambda r2, _e2: self._on_clipboard(r2)),
            self._notify("Clipboard history cleared")))

    def _on_files_refresh(self, _b) -> None:
        self._files_status.set_text("rebuilding…")
        self.api_get("/api/files", params={"query": "", "refresh": True},
                     on_result=lambda r, e: self._on_files(r))

    def _on_chat_config(self, r: dict | None) -> None:
        if not r:
            return
        endpoint = r.get("endpoint", "")
        model = r.get("model", "")
        masked_key = r.get("api_key", "")
        self._chat_endpoint.set_text(endpoint)
        self._chat_model.set_text(model)
        if masked_key:
            self._chat_api_key.set_text(masked_key)
        self._chat_status.set_text(f"Provider: {r.get('provider', 'hermes')} (Model: {model})")

    def _on_chat_save(self, _b) -> None:
        endpoint = self._chat_endpoint.get_text().strip()
        model = self._chat_model.get_text().strip()
        key = self._chat_api_key.get_text().strip()
        payload = {
            "provider": "hermes",
            "endpoint": endpoint or "http://localhost:8000/v1",
            "model": model or "hermes-3-llama-3.1-8b",
        }
        if key and not key.startswith("••••"):
            payload["api_key"] = key
        self.api_post("/api/chat/config", payload, on_result=lambda r, e: (
            self._notify("Chat configuration saved" if not e else str(e)),
            self.api_get("/api/chat/config", on_result=lambda r2, _e2: self._on_chat_config(r2))
        ))

