"""Application shell: Gtk.Application, CSS, window registry."""
from __future__ import annotations

import os

from gi.repository import Gdk, GLib, Gtk

from ..version import __version__
from .api_client import ApiClient
from .chat_window import ChatWindow
from .palette import PaletteWindow
from .settings import SettingsWindow

_CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.css")


class RaycastLinuxApp(Gtk.Application):
    def __init__(self, hub, port: int, show_settings: bool = False) -> None:
        super().__init__(application_id="dev.arena.RaycastLinux")
        self.hub = hub
        self.port = port
        self.show_settings = show_settings
        self.api = ApiClient(f"http://127.0.0.1:{port}")

        # API thread → GTK main thread
        self.hub.on_palette_toggle = lambda: GLib.idle_add(self._toggle_palette)
        # Portal global shortcut → GTK main thread
        self.hub.portal.set_on_activate(lambda: GLib.idle_add(self._toggle_palette))

        self.palette: PaletteWindow | None = None
        self.settings_win: SettingsWindow | None = None
        self.chat_win: ChatWindow | None = None

    # -- Gtk.Application vfunc overrides ---------------------------------
    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_path(_CSS_PATH)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        self.palette = PaletteWindow(self)
        if self.show_settings:
            self.open_settings()

    def do_activate(self) -> None:
        assert self.palette is not None
        self.palette.present()

    def do_shutdown(self) -> None:
        self.api.shutdown()
        Gtk.Application.do_shutdown(self)

    # -- helpers -----------------------------------------------------------
    def _toggle_palette(self) -> bool:
        if self.palette is not None:
            if self.palette.is_visible():
                self.palette.hide()
            else:
                self.palette.present()
        return False

    def open_settings(self) -> None:
        if self.settings_win is None:
            self.settings_win = SettingsWindow(self)
        self.settings_win.present()

    def open_chat(self) -> None:
        if self.chat_win is None:
            self.chat_win = ChatWindow(self)
        self.chat_win.present()

    def notify(self, summary: str, body: str = "") -> None:
        try:
            import gi
            gi.require_version("Notify", "0.7")
            from gi.repository import Notify
            if not Notify.init("raycast-linux"):
                return
            n = Notify.Notification(summary, body or None)
            n.show()
        except Exception:  # noqa: BLE001
            pass  # notifications are optional

    def version(self) -> str:
        return __version__
