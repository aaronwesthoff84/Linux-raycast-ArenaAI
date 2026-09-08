"""Graphical setup and diagnostics window for Raycast Linux."""
from __future__ import annotations

import os
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango

from ..platform import detect


def _label(text: str, css: str | None = None) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0.0, wrap=True)
    lbl.set_lines(-1)
    if css:
        lbl.add_css_class(css)
    return lbl


def _card(title: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.add_css_class("settings-section")
    box.append(_label(title, "settings-title"))
    return box


class SetupWindow(Gtk.ApplicationWindow):
    """Graphical setup, diagnostic verification, and maintenance window."""

    def __init__(self, app) -> None:
        super().__init__(application=app, title="Raycast Linux: Setup and Diagnostics")
        self.app = app
        self.set_default_size(580, 680)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.add_css_class("settings-root")
        root.set_margin_start(18)
        root.set_margin_end(18)
        root.set_margin_top(18)
        root.set_margin_bottom(18)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(root)
        self.set_child(sw)

        # -- Header card ------------------------------------------------------
        hdr = _card("Welcome to Raycast Linux")
        hdr.append(_label(
            "Native GTK4 productivity launcher, clipboard manager, and AI agent hub.",
            "settings-hint",
        ))
        root.append(hdr)

        # -- Diagnostics card -------------------------------------------------
        diag = _card("System Diagnostics")
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(14)

        env_info = detect.env_info()
        dm = env_info.get("display_server", "unknown")
        wm = env_info.get("window_manager", "unknown")
        tools = detect.tools()

        checks = [
            ("Display server", dm, dm in ("wayland", "x11")),
            ("Window manager", wm, wm != "unknown"),
            ("Clipboard tool", "wl-clipboard" if dm == "wayland" else "xclip",
             tools.get("wl-copy", False) if dm == "wayland" else tools.get("xclip", False)),
            ("Typing tool", "wtype (Wayland)", tools.get("wtype", False) if dm == "wayland" else True),
            ("Shortcut portal", "python-dbus", self._check_dbus()),
        ]

        for row_idx, (name, val, ok) in enumerate(checks):
            grid.attach(_label(name, "settings-key"), 0, row_idx, 1, 1)
            status_text = f"{'✓' if ok else '✗'} {val}"
            status_css = "settings-value"
            grid.attach(_label(status_text, status_css), 1, row_idx, 1, 1)

        diag.append(grid)
        root.append(diag)

        # -- Quick Actions card -----------------------------------------------
        act = _card("Quick Actions")

        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_palette = Gtk.Button(label="Test Palette")
        btn_palette.connect("clicked", self._on_test_palette)

        btn_shortcut = Gtk.Button(label="Register Global Shortcut")
        btn_shortcut.connect("clicked", self._on_register_shortcut)

        btn_autostart = Gtk.Button(label=self._autostart_button_label())
        btn_autostart.connect("clicked", lambda b: self._on_toggle_autostart(b))

        act_box.append(btn_palette)
        act_box.append(btn_shortcut)
        act_box.append(btn_autostart)
        act.append(act_box)

        self._action_status = _label("", "settings-hint")
        act.append(self._action_status)
        root.append(act)

        # -- Update and Uninstall instructions card ---------------------------
        maint = _card("Updates and Maintenance")
        maint.append(_label("Data directory: ~/.local/share/raycast-linux", "settings-key"))
        maint.append(_label(
            "Your configurations, snippets, clipboard history, and chat threads "
            "are stored in ~/.local/share/raycast-linux and are preserved during updates.",
            "settings-hint",
        ))

        maint_grid = Gtk.Grid()
        maint_grid.set_row_spacing(8)
        maint_grid.set_column_spacing(12)

        maint_grid.attach(_label("Update (git):", "settings-key"), 0, 0, 1, 1)
        maint_grid.attach(_label("git pull && ./install.sh", "settings-value"), 1, 0, 1, 1)

        maint_grid.attach(_label("Update (CachyOS/Arch):", "settings-key"), 0, 1, 1, 1)
        maint_grid.attach(_label("yay -S raycast-linux", "settings-value"), 1, 1, 1, 1)

        maint_grid.attach(_label("Uninstall:", "settings-key"), 0, 2, 1, 1)
        maint_grid.attach(_label("./uninstall.sh  (preserves data) or ./uninstall.sh --purge", "settings-value"), 1, 2, 1, 1)

        maint.append(maint_grid)
        root.append(maint)

    # -- Internal helpers ----------------------------------------------------
    @staticmethod
    def _check_dbus() -> bool:
        try:
            import dbus  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _autostart_path() -> Path:
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return Path(config_home) / "autostart" / "raycast-linux.desktop"

    def _autostart_button_label(self) -> str:
        return "Disable Autostart" if self._autostart_path().exists() else "Enable Autostart"

    def _on_test_palette(self, _b) -> None:
        self.app._toggle_palette()
        self._action_status.set_text("Palette toggled.")

    def _on_register_shortcut(self, _b) -> None:
        self._action_status.set_text("Registering Super+Space portal shortcut...")
        self.app.api.post(
            "/api/shortcuts",
            json={"shortcut": "super+space"},
            on_result=lambda r, e: self._action_status.set_text((r or {}).get("message", str(e))),
        )

    def _on_toggle_autostart(self, button: Gtk.Button) -> None:
        p = self._autostart_path()
        if p.exists():
            p.unlink()
            self._action_status.set_text("Autostart entry removed.")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            desktop_src = Path(__file__).parent.parent.parent / "packaging" / "raycast-linux.desktop"
            if desktop_src.exists():
                p.write_text(desktop_src.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                p.write_text(
                    "[Desktop Entry]\nType=Application\nName=Raycast Linux\nExec=raycast-linux\nTerminal=false\n",
                    encoding="utf-8",
                )
            self._action_status.set_text("Autostart entry created at " + str(p))
        button.set_label(self._autostart_button_label())
