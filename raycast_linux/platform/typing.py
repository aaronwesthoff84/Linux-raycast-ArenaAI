"""Clipboard + text-typing helpers with per-display-server fallbacks.

Wayland: wl-clipboard (wl-copy/wl-paste) and wtype (uinput virtual keyboard).
X11: xclip/xsel and xdotool. When no tool exists the functions degrade
gracefully (False / None) and callers surface a helpful message.
"""
from __future__ import annotations

import subprocess

from . import detect


def _run(cmd: list[str], input_text: str | None = None, timeout: float = 5) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=timeout)


def clipboard_get() -> str | None:
    """Return the current clipboard text, or None if unavailable/empty-ish."""
    if detect.display_server() == "wayland":
        if detect.tools().get("wl-paste"):
            try:
                r = _run(["wl-paste", "--no-newline", "--noninteractive"], timeout=2)
                if r.returncode == 0:
                    return r.stdout
            except Exception:
                pass
        return None
    for cmd in (
        ["xclip", "-o", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--output"],
    ):
        if detect.tools().get(cmd[0]):
            try:
                r = _run(cmd, timeout=2)
                if r.returncode == 0:
                    return r.stdout
            except Exception:
                continue
    return None


def clipboard_set(text: str) -> bool:
    """Put text on the clipboard. Returns True on success."""
    if detect.display_server() == "wayland":
        if detect.tools().get("wl-copy"):
            try:
                _run(["wl-copy"], input_text=text, timeout=2)
                return True
            except Exception:
                return False
        return False
    if detect.tools().get("xclip"):
        try:
            _run(["xclip", "-selection", "clipboard"], input_text=text, timeout=2)
            return True
        except Exception:
            pass
    if detect.tools().get("xsel"):
        try:
            _run(["xsel", "--clipboard", "--input"], input_text=text, timeout=2)
            return True
        except Exception:
            pass
    return False


def type_text(text: str) -> tuple[bool, str]:
    """Type text into the currently focused window.

    Returns ``(ok, method_or_reason)``. On Wayland this needs ``wtype``;
    on X11 it uses ``xdotool``.
    """
    if detect.display_server() == "wayland":
        if detect.tools().get("wtype"):
            try:
                r = _run(["wtype", "--", text], timeout=10)
                if r.returncode == 0:
                    return True, "wtype"
                return False, f"wtype failed: {r.stderr.strip() or 'unknown error'}"
            except Exception as e:  # noqa: BLE001
                return False, f"wtype error: {e}"
        return False, "wtype is not installed — install it to auto-type on Wayland"
    if detect.tools().get("xdotool"):
        try:
            r = _run(
                ["xdotool", "type", "--delay", "12", "--clearmodifiers", "--", text],
                timeout=10,
            )
            if r.returncode == 0:
                return True, "xdotool"
            return False, "xdotool type failed"
        except Exception as e:  # noqa: BLE001
            return False, f"xdotool error: {e}"
    return False, "no typing tool available (install wtype or xdotool)"
