"""Runtime environment detection: display server, window manager, tools.

Everything is best-effort and cached cheaply — the values are reported in
``/api/env`` and used to pick window-management providers.
"""
from __future__ import annotations

import os
import shutil
import subprocess

_TOOLS = [
    "wl-copy", "wl-paste", "wtype",          # Wayland
    "xclip", "xsel", "xdotool", "wmctrl",    # X11
    "swaymsg", "hyprctl",                    # tiling WMs
    "xdg-open",
]

# Window manager → marker process names (as seen in /proc/<pid>/comm)
_WM_MARKERS = {
    "sway": ("sway",),
    "hyprland": ("hyprland",),
    "kwin": ("kwin_wayland", "kwin_x11"),
    "gnome-shell": ("gnome-shell",),
    "mutter": ("mutter",),
    "labwc": ("labwc",),
    "weston": ("weston",),
    "cinnamon": ("cinnamon",),
    "xfce4": ("xfwm4",),
    "openbox": ("openbox",),
    "dwm": ("dwm",),
    "i3": ("i3",),
    "river": ("river",),
    "niri": ("niri",),
    "cosmic": ("cosmic-comp",),
    "awesome": ("awesome",),
}


def display_server() -> str:
    """Return 'wayland', 'x11' or 'unknown'."""
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    if os.environ.get("DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "x11":
        return "x11"
    return "unknown"


def _process_names() -> set[str]:
    names: set[str] = set()
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/comm", encoding="ascii", errors="replace") as f:
                    names.add(f.read().strip().lower())
            except OSError:
                pass
    except OSError:
        pass
    return names


def window_manager() -> str:
    """Best-effort WM name ('sway', 'hyprland', 'kwin', 'gnome-shell', …)."""
    procs = _process_names()
    for wm, markers in _WM_MARKERS.items():
        if any(m in procs for m in markers):
            return wm
    if display_server() == "x11" and shutil.which("xprop"):
        try:
            out = subprocess.run(
                ["xprop", "-root", "_NET_WM_NAME"],
                capture_output=True, text=True, timeout=2,
            ).stdout.lower()
            if "gnome" in out:
                return "gnome-shell"
            if "kde" in out or "kwin" in out:
                return "kwin"
            if "i3" in out:
                return "i3"
            if "dwm" in out:
                return "dwm"
            if "openbox" in out:
                return "openbox"
        except Exception:
            pass
    return "unknown"


def tools() -> dict[str, bool]:
    """Which helper binaries are on PATH (used by the doctor + providers)."""
    return {name: shutil.which(name) is not None for name in _TOOLS}


def env_info() -> dict:
    info = {
        "display_server": display_server(),
        "window_manager": window_manager(),
        "tools": tools(),
        "home": os.path.expanduser("~"),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        "x_display": os.environ.get("DISPLAY"),
    }
    return info
