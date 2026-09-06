"""Window-management providers.

On Wayland there is no universal "move/resize any window" API, so we ship
compositor-specific bridges:

  * Sway      → ``swaymsg`` (move position + resize set, focus commands)
  * Hyprland  → ``hyprctl`` (split / centerwindow / focus)
  * X11       → ``xdotool`` + ``wmctrl`` (full geometry control)
  * Anything else → a provider that explains the limitation and still
                    offers what's possible.

Every provider exposes:
    actions()      → list of supported action names
    run(action)    → {"ok": bool, "message": str}
    stash_active() → remember the focused window (called before the palette grabs focus)
    refocus()      → return focus to that window (used after typing snippets)
    hint           → human-readable status for the UI
"""
from __future__ import annotations

import json
import subprocess

from ..platform import detect


class _Base:
    name = "none"
    hint = "No window management available on this session."
    _stashed: str | None = None

    def actions(self) -> list[str]:
        return []

    def run(self, action: str) -> dict:
        return {"ok": False, "message": f"Action “{action}” is not supported here"}

    def stash_active(self) -> None:
        pass

    def refocus(self) -> dict:
        return {"ok": False, "message": "No focus restore support"}


# ---------------------------------------------------------------- Sway
class SwayProvider(_Base):
    name = "sway"
    hint = "Sway detected — tiling via swaymsg."

    @staticmethod
    def _sway(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(["swaymsg"] + args, capture_output=True, text=True, timeout=3)

    def _focused_output(self) -> dict | None:
        r = self._sway(["-t", "get_outputs"])
        try:
            outputs = json.loads(r.stdout)
        except (ValueError, TypeError):
            return None
        for o in outputs:
            if o.get("focused"):
                return o
        return outputs[0] if outputs else None

    def _focused_rect(self) -> dict | None:
        r = self._sway(["-t", "get_tree"])
        try:
            tree = json.loads(r.stdout)
        except (ValueError, TypeError):
            return None

        def find(node: dict) -> dict | None:
            if node.get("focused"):
                return node
            for child in node.get("nodes", []):
                found = find(child)
                if found:
                    return found
            for child in node.get("floating_nodes", []):
                found = find(child)
                if found:
                    return found
            return None

        node = find(tree)
        return node.get("rect") if node else None

    def _snap(self, side: str) -> dict:
        out = self._focused_output()
        if not out:
            return {"ok": False, "message": "Could not read the focused output"}
        ox, oy, ow, oh = out["x"], out["y"], out["width"], out["height"]
        if side == "left":
            x, y, w, h = ox, oy, ow // 2, oh
        elif side == "right":
            x, y, w, h = ox + ow // 2, oy, ow // 2, oh
        elif side == "top":
            x, y, w, h = ox, oy, ow, oh // 2
        else:  # bottom
            x, y, w, h = ox, oy + oh // 2, ow, oh // 2
        self._sway(["move", "position", str(x), str(y)])
        self._sway(["resize", "set", str(w), str(h)])
        return {"ok": True, "message": f"Snapped window {side}"}

    def actions(self) -> list[str]:
        return ["left", "right", "top", "bottom", "center", "maximize", "close", "next", "prev"]

    def run(self, action: str) -> dict:
        if action in ("left", "right", "top", "bottom"):
            return self._snap(action)
        if action == "center":
            out, rect = self._focused_output(), self._focused_rect()
            if not out or not rect:
                return {"ok": False, "message": "Could not read window geometry"}
            x = out["x"] + (out["width"] - rect["width"]) // 2
            y = out["y"] + (out["height"] - rect["height"]) // 2
            self._sway(["move", "position", str(x), str(y)])
            return {"ok": True, "message": "Centered window"}
        if action == "maximize":
            out = self._focused_output()
            if not out:
                return {"ok": False, "message": "Could not read the focused output"}
            self._sway(["move", "position", str(out["x"]), str(out["y"])])
            self._sway(["resize", "set", str(out["width"]), str(out["height"])])
            return {"ok": True, "message": "Maximized window"}
        if action == "close":
            self._sway(["kill"])
            return {"ok": True, "message": "Closed window"}
        if action == "next":
            self._sway(["focus", "next"])
            return {"ok": True, "message": "Focused next window"}
        if action == "prev":
            self._sway(["focus", "prev"])
            return {"ok": True, "message": "Focused previous window"}
        return super().run(action)

    def refocus(self) -> dict:
        r = self._sway(["focus", "back-and-forth"])
        return {
            "ok": r.returncode == 0,
            "message": "Focus returned to the previous window" if r.returncode == 0 else "sway focus failed",
        }


# ------------------------------------------------------------- Hyprland
class HyprlandProvider(_Base):
    name = "hyprland"
    hint = "Hyprland detected — tiling via hyprctl."

    @staticmethod
    def _hctl(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(["hyprctl"] + args, capture_output=True, text=True, timeout=3)

    def actions(self) -> list[str]:
        return ["left", "right", "top", "bottom", "center", "fullscreen", "close", "next", "prev"]

    def run(self, action: str) -> dict:
        side = {"left": "l", "right": "r", "top": "u", "bottom": "d"}.get(action)
        if side:
            self._hctl(["dispatch", "split", side])
            return {"ok": True, "message": f"Split window {action}"}
        if action == "center":
            self._hctl(["dispatch", "centerwindow"])
            return {"ok": True, "message": "Centered window"}
        if action == "fullscreen":
            self._hctl(["dispatch", "fullscreen", "1"])
            return {"ok": True, "message": "Fullscreen window"}
        if action == "close":
            self._hctl(["dispatch", "closewindow"])
            return {"ok": True, "message": "Closed window"}
        if action == "next":
            self._hctl(["dispatch", "focusr"])
            return {"ok": True, "message": "Focused next window"}
        if action == "prev":
            self._hctl(["dispatch", "focusl"])
            return {"ok": True, "message": "Focused previous window"}
        return super().run(action)

    def refocus(self) -> dict:
        r = self._hctl(["dispatch", "focusbackandforth"])
        return {
            "ok": r.returncode == 0,
            "message": "Focus returned to the previous window" if r.returncode == 0 else "hyprctl focus failed",
        }


# ----------------------------------------------------------------- X11
class X11Provider(_Base):
    name = "x11"
    hint = "X11 detected — geometry via xdotool, cycling via wmctrl."

    @staticmethod
    def _xdotool(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(["xdotool"] + args, capture_output=True, text=True, timeout=3)

    def _active_id(self) -> str | None:
        r = self._xdotool(["getactivewindow"])
        wid = r.stdout.strip()
        return wid or None

    def _active_geom(self) -> dict | None:
        wid = self._active_id()
        if not wid:
            return None
        r = self._xdotool(["getwindowgeometry", "--shell", wid])
        d: dict[str, str] = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                d[k] = v.strip()
        try:
            return {
                "id": wid,
                "x": int(d.get("X", 0)),
                "y": int(d.get("Y", 0)),
                "w": int(d.get("WIDTH", 800)),
                "h": int(d.get("HEIGHT", 600)),
            }
        except ValueError:
            return None

    def _display_geom(self) -> tuple[int, int]:
        r = self._xdotool(["getdisplaygeometry"])
        try:
            w, h = r.stdout.split()
            return int(w), int(h)
        except ValueError:
            return 1920, 1080

    def actions(self) -> list[str]:
        return ["left", "right", "top", "bottom", "center", "maximize", "close", "next", "prev"]

    def run(self, action: str) -> dict:
        if action in ("left", "right", "top", "bottom", "center", "maximize"):
            g = self._active_geom()
            if not g:
                return {"ok": False, "message": "Could not read the active window"}
            dw, dh = self._display_geom()
            if action == "left":
                x, y, w, h = 0, 0, dw // 2, dh
            elif action == "right":
                x, y, w, h = dw // 2, 0, dw // 2, dh
            elif action == "top":
                x, y, w, h = 0, 0, dw, dh // 2
            elif action == "bottom":
                x, y, w, h = 0, dh // 2, dw, dh // 2
            elif action == "maximize":
                x, y, w, h = 0, 0, dw, dh
            else:
                x, y = (dw - g["w"]) // 2, (dh - g["h"]) // 2
                w, h = g["w"], g["h"]
            self._xdotool(["windowmove", g["id"], str(x), str(y)])
            self._xdotool(["windowsize", g["id"], str(w), str(h)])
            return {"ok": True, "message": f"Window {action}"}
        if action == "close":
            g = self._active_geom()
            if not g:
                return {"ok": False, "message": "Could not read the active window"}
            r = self._xdotool(["windowclose", g["id"]])
            return {"ok": r.returncode == 0, "message": "Closed window"}
        if action in ("next", "prev"):
            flag = "-N" if action == "next" else "-P"
            r = subprocess.run(["wmctrl", "-R", flag], capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                return {"ok": True, "message": f"Focused {action} window"}
            return {"ok": False, "message": "wmctrl failed — install wmctrl"}
        return super().run(action)

    def stash_active(self) -> None:
        self._stashed = self._active_id()

    def refocus(self) -> dict:
        if not self._stashed:
            return {"ok": False, "message": "No stashed window"}
        r = self._xdotool(["windowactivate", self._stashed])
        return {"ok": r.returncode == 0, "message": "Focus returned to the previous window"}


# ------------------------------------------------------------ fallbacks
class WaylandGeneric(_Base):
    name = "wayland-generic"

    def __init__(self, wm: str) -> None:
        self.hint = (
            f"Running under {wm or 'an unknown Wayland compositor'} — cross-window "
            "tiling is not possible on Wayland without a compositor bridge. "
            "Sway and Hyprland are built in; elsewhere use your compositor's own "
            "snap shortcuts (they coexist fine with raycast-linux)."
        )


class X11Generic(_Base):
    name = "x11-generic"
    hint = "X11 detected but xdotool is missing — install xdotool for window tiling."


class NoneProvider(_Base):
    name = "none"
    hint = "No display detected (headless?) — window actions are disabled."


def detect_provider() -> _Base:
    info = detect.env_info()
    dm, wm, tools = info["display_server"], info["window_manager"], info["tools"]
    if dm == "wayland":
        if wm == "sway" and tools.get("swaymsg"):
            return SwayProvider()
        if wm == "hyprland" and tools.get("hyprctl"):
            return HyprlandProvider()
        return WaylandGeneric(wm)
    if dm == "x11":
        if tools.get("xdotool"):
            return X11Provider()
        return X11Generic()
    return NoneProvider()
