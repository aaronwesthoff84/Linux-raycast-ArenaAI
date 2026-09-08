"""Smoke tests for installation, venv system-site-packages, and GTK availability."""
import os
import subprocess
import sys
import venv
from pathlib import Path
import pytest


def test_venv_system_site_packages_strategy(tmp_path):
    """Test that creating a venv with system_site_packages allows accessing system libraries."""
    venv_dir = tmp_path / "test_venv"
    builder = venv.EnvBuilder(system_site_packages=True, with_pip=False)
    builder.create(venv_dir)

    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    assert pyvenv_cfg.exists()
    cfg_content = pyvenv_cfg.read_text(encoding="utf-8")
    assert "include-system-site-packages = true" in cfg_content.lower()

    if sys.platform != "win32":
        try:
            import gi
            has_gi = True
        except (ImportError, ModuleNotFoundError):
            has_gi = False

        if has_gi:
            python_bin = venv_dir / "bin" / "python"
            # Test that gi is importable from this venv
            res = subprocess.run(
                [str(python_bin), "-c", "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print('OK')"],
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0
            assert "OK" in res.stdout


def test_install_script_contains_system_site_packages():
    """Verify install.sh uses --system-site-packages to bind system GTK."""
    script_path = Path(__file__).resolve().parent.parent / "install.sh"
    content = script_path.read_text(encoding="utf-8")
    assert "--system-site-packages" in content
    assert "import gi" in content
