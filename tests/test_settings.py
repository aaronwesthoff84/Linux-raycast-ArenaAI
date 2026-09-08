"""Tests for SettingsWindow callbacks and environment loading."""
import pytest
from unittest.mock import MagicMock


class MockLabel:
    def __init__(self, text: str = "…"):
        self.text = text

    def set_text(self, text: str) -> None:
        self.text = text

    def get_text(self) -> str:
        return self.text


class MockSettingsWindow:
    """Mock SettingsWindow providing the labels populated in __init__."""
    def __init__(self):
        self.keys = ["display_server", "window_manager", "window_provider", "data_dir", "version"]
        for key in self.keys:
            setattr(self, f"_plat_{key}", MockLabel("…"))


def test_on_env_reproduction_and_update():
    """Verify _on_env updates label texts and handles empty/populated payloads."""
    # We import the method or class
    # If gi is not available on Windows, we extract or import safely
    try:
        from raycast_linux.frontend.settings import SettingsWindow
        on_env_func = SettingsWindow._on_env
    except (ImportError, ModuleNotFoundError):
        # On environments without GTK, test the method definition directly
        import ast
        from pathlib import Path
        src = Path("raycast_linux/frontend/settings.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_on_env":
                mod = ast.Module(body=[node], type_ignores=[])
                code = compile(mod, filename="<ast>", mode="exec")
                ns = {}
                exec(code, ns)
                on_env_func = ns["_on_env"]
                break
        else:
            pytest.fail("Could not find _on_env in settings.py")

    win = MockSettingsWindow()

    # 1. Test None response (absent)
    on_env_func(win, None)
    assert win._plat_version.text == "…"

    # 2. Test empty response
    on_env_func(win, {})
    assert win._plat_version.text == "…"

    # 3. Test populated response
    payload = {
        "display_server": "wayland",
        "window_manager": "sway",
        "window_provider": "sway",
        "data_dir": "/home/user/.local/share/raycast-linux",
        "version": "1.0.0",
    }
    on_env_func(win, payload)
    assert win._plat_display_server.text == "wayland"
    assert win._plat_window_manager.text == "sway"
    assert win._plat_window_provider.text == "sway"
    assert win._plat_data_dir.text == "/home/user/.local/share/raycast-linux"
    assert win._plat_version.text == "1.0.0"

    # 4. Test partial response with fallback
    partial_payload = {
        "display_server": "x11",
    }
    on_env_func(win, partial_payload)
    assert win._plat_display_server.text == "x11"
    assert win._plat_version.text == "—"
