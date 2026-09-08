"""Chat window: interactive conversational interface with Hermes AI."""
from __future__ import annotations

import json

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango


class ChatWindow(Gtk.ApplicationWindow):
    def __init__(self, app) -> None:
        super().__init__(application=app, title="Raycast Linux: Hermes Chat")
        self.app = app
        self.set_default_size(620, 680)
        self._current_conv_id: str | None = None
        self._is_generating = False

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_css_classes(["chat-root"])
        root.set_margin_start(16)
        root.set_margin_end(16)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        self.set_child(root)

        # -- header bar --------------------------------------------------------
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._title_label = Gtk.Label(label="Hermes Chat", xalign=0.0)
        self._title_label.set_hexpand(True)
        self._title_label.add_css_class("chat-title")

        new_btn = Gtk.Button(label="New Chat")
        new_btn.connect("clicked", lambda _b: self._on_new_chat())

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", lambda _b: self._on_clear_chat())

        header.append(self._title_label)
        header.append(new_btn)
        header.append(clear_btn)
        root.append(header)

        # -- message list ------------------------------------------------------
        swrap = Gtk.ScrolledWindow()
        swrap.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        swrap.set_vexpand(True)
        self._msg_list = Gtk.ListBox()
        self._msg_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._msg_list.add_css_class("chat-msg-list")
        swrap.set_child(self._msg_list)
        root.append(swrap)
        self._scroll = swrap

        # -- status & model info -----------------------------------------------
        self._status_label = Gtk.Label(label="Model: nousresearch/hermes-3-llama-3.1-8b", xalign=0.0)
        self._status_label.add_css_class("chat-status")
        root.append(self._status_label)

        # -- input bar ---------------------------------------------------------
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Ask Hermes anything… (Enter to send)")
        self._entry.set_hexpand(True)
        self._entry.connect("activate", lambda _e: self._on_send())

        self._send_btn = Gtk.Button(label="Send")
        self._send_btn.connect("clicked", lambda _b: self._on_send())

        self._cancel_btn = Gtk.Button(label="Cancel")
        self._cancel_btn.set_sensitive(False)
        self._cancel_btn.connect("clicked", lambda _b: self._on_cancel())

        input_box.append(self._entry)
        input_box.append(self._send_btn)
        input_box.append(self._cancel_btn)
        root.append(input_box)

        # Initialize conversation
        self._init_conversation()

    # -- conversation lifecycle -----------------------------------------------
    def _init_conversation(self) -> None:
        self.app.api.get(
            "/api/chat/conversations",
            on_result=lambda r, e: GLib.idle_add(self._on_conversations_loaded, r),
        )

    def _on_conversations_loaded(self, r: list[dict] | None) -> None:
        if r and len(r) > 0:
            self._load_conversation(r[0]["id"])
        else:
            self._on_new_chat()

    def _load_conversation(self, conv_id: str) -> None:
        self._current_conv_id = conv_id
        self.app.api.get(
            f"/api/chat/conversations/{conv_id}",
            on_result=lambda r, e: GLib.idle_add(self._render_conversation, r),
        )

    def _render_conversation(self, conv: dict | None) -> None:
        self._msg_list.remove_all()
        if not conv:
            return
        self._title_label.set_text(conv.get("title", "Hermes Chat"))
        for msg in conv.get("messages", []):
            self._append_bubble(msg.get("role", "user"), msg.get("content", ""))

    def _append_bubble(self, role: str, content: str) -> Gtk.Label:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("chat-bubble")
        box.add_css_class(f"chat-bubble-{role}")

        role_lbl = Gtk.Label(label="You" if role == "user" else "Hermes", xalign=0.0)
        role_lbl.add_css_class("chat-bubble-role")

        content_lbl = Gtk.Label(label=content, xalign=0.0, wrap=True)
        content_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        content_lbl.add_css_class("chat-bubble-content")

        box.append(role_lbl)
        box.append(content_lbl)
        row.set_child(box)
        self._msg_list.append(row)

        # Scroll to bottom
        adj = self._scroll.get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper()))
        return content_lbl

    def _on_new_chat(self) -> None:
        self.app.api.post(
            "/api/chat/conversations",
            json={"title": "New Chat"},
            on_result=lambda r, e: GLib.idle_add(self._on_chat_created, r),
        )

    def _on_chat_created(self, r: dict | None) -> None:
        if r and "id" in r:
            self._current_conv_id = r["id"]
            self._msg_list.remove_all()
            self._title_label.set_text(r.get("title", "New Chat"))

    def _on_clear_chat(self) -> None:
        if not self._current_conv_id:
            return
        self.app.api.post(
            f"/api/chat/conversations/{self._current_conv_id}/clear",
            on_result=lambda _r, _e: GLib.idle_add(self._msg_list.remove_all),
        )

    def _on_send(self) -> None:
        text = self._entry.get_text().strip()
        if not text or not self._current_conv_id or self._is_generating:
            return

        self._entry.set_text("")
        self._append_bubble("user", text)
        assistant_lbl = self._append_bubble("assistant", "Thinking…")

        self._is_generating = True
        self._send_btn.set_sensitive(False)
        self._cancel_btn.set_sensitive(True)
        self._status_label.set_text("Generating response…")

        self.app.api.post(
            f"/api/chat/conversations/{self._current_conv_id}/messages",
            json={"prompt": text, "stream": False},
            on_result=lambda r, e: GLib.idle_add(self._on_message_response, assistant_lbl, r, e),
        )

    def _on_message_response(self, lbl: Gtk.Label, r: dict | None, err: Exception | None) -> None:
        self._is_generating = False
        self._send_btn.set_sensitive(True)
        self._cancel_btn.set_sensitive(False)
        self._status_label.set_text("Ready")

        if err:
            lbl.set_text(f"[Error: {err}]")
        elif r and r.get("ok"):
            msg = r.get("message", {})
            lbl.set_text(msg.get("content", ""))
        elif r and r.get("error"):
            lbl.set_text(f"[Error: {r['error']}]")
        elif r and r.get("cancelled"):
            lbl.set_text("[Cancelled]")
        else:
            lbl.set_text("[No response from Hermes]")

    def _on_cancel(self) -> None:
        if not self._current_conv_id or not self._is_generating:
            return
        self.app.api.post(
            f"/api/chat/conversations/{self._current_conv_id}/cancel",
            on_result=lambda _r, _e: None,
        )
