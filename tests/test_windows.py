import pytest

import raycast_linux.platform.detect as detect
from raycast_linux.backend.windows import (
    HyprlandProvider,
    NoneProvider,
    SwayProvider,
    WaylandGeneric,
    X11Generic,
    X11Provider,
    detect_provider,
)


def _mock_env(monkeypatch, dm, wm="unknown", tools=None):
    monkeypatch.setattr(detect, "display_server", lambda: dm)
    monkeypatch.setattr(detect, "window_manager", lambda: wm)
    monkeypatch.setattr(detect, "tools", lambda: tools or {})


def test_sway_selected(monkeypatch):
    _mock_env(monkeypatch, "wayland", "sway", {"swaymsg": True})
    assert isinstance(detect_provider(), SwayProvider)


def test_hyprland_selected(monkeypatch):
    _mock_env(monkeypatch, "wayland", "hyprland", {"hyprctl": True})
    assert isinstance(detect_provider(), HyprlandProvider)


def test_x11_selected(monkeypatch):
    _mock_env(monkeypatch, "x11", "gnome-shell", {"xdotool": True})
    assert isinstance(detect_provider(), X11Provider)


def test_x11_without_xdotool(monkeypatch):
    _mock_env(monkeypatch, "x11", "gnome-shell", {})
    assert isinstance(detect_provider(), X11Generic)


def test_wayland_without_bridge(monkeypatch):
    _mock_env(monkeypatch, "wayland", "gnome-shell", {"swaymsg": True})
    p = detect_provider()
    assert isinstance(p, WaylandGeneric)
    assert p.actions() == []
    res = p.run("left")
    assert res["ok"] is False


def test_headless(monkeypatch):
    _mock_env(monkeypatch, "unknown")
    assert isinstance(detect_provider(), NoneProvider)


def test_sway_provider_reports_actions(monkeypatch):
    _mock_env(monkeypatch, "wayland", "sway", {"swaymsg": True})
    p = detect_provider()
    assert "left" in p.actions()
    assert "maximize" in p.actions()


def test_x11_refocus_without_stash(monkeypatch):
    _mock_env(monkeypatch, "x11", "gnome-shell", {"xdotool": True})
    p = detect_provider()
    res = p.refocus()
    assert res["ok"] is False
