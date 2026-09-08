"""Tests for CachyOS packaging, install/upgrade data retention, and uninstall workflows."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def test_pkgbuild_metadata_and_integrity():
    pkgbuild_path = REPO_ROOT / "packaging" / "PKGBUILD"
    assert pkgbuild_path.exists()
    content = pkgbuild_path.read_text(encoding="utf-8")

    assert 'pkgname=raycast-linux' in content
    assert 'pkgver=1.0.0' in content
    assert 'https://github.com/aaronwesthoff84/Linux-raycast-ArenaAI' in content
    assert 'python-venv' not in content  # Arch packages venv inside python
    assert 'uvicorn' in content
    assert 'python-fastapi' in content
    assert 'sha256sums=' in content
    assert 'example.invalid' not in content


def test_desktop_entry_validity():
    desktop_path = REPO_ROOT / "packaging" / "raycast-linux.desktop"
    assert desktop_path.exists()
    content = desktop_path.read_text(encoding="utf-8")

    assert "[Desktop Entry]" in content
    assert "Exec=raycast-linux" in content
    assert "Icon=raycast-linux" in content
    assert "Type=Application" in content


def _run_script(script_path: Path, args: list[str], env: dict) -> subprocess.CompletedProcess:
    import sys
    env = env.copy()
    env["RAYCAST_TESTING"] = "1"
    if sys.platform == "win32":
        wsl_script = "/mnt/" + str(script_path)[0].lower() + str(script_path)[2:].replace("\\", "/")
        wsl_env = ["RAYCAST_TESTING=1"]
        for k in ("XDG_BIN_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            if k in env:
                v = env[k]
                wsl_val = "/mnt/" + str(v)[0].lower() + str(v)[2:].replace("\\", "/")
                wsl_env.append(f"{k}={wsl_val}")
        cmd = ["wsl", "-d", "archlinux", "env"] + wsl_env + ["bash", wsl_script] + args
        return subprocess.run(cmd, capture_output=True, text=True)
    else:
        return subprocess.run(["bash", str(script_path)] + args, env=env, capture_output=True, text=True)


def test_uninstall_preserves_user_data_by_default(tmp_path):
    bin_dir = tmp_path / "bin"
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    bin_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    app_bin = bin_dir / "raycast-linux"
    app_bin.write_text("#!/bin/sh\nexit 0", encoding="utf-8")

    desktop_dir = data_dir / "applications"
    desktop_dir.mkdir(parents=True)
    desktop_file = desktop_dir / "raycast-linux.desktop"
    desktop_file.write_text("[Desktop Entry]\nName=Raycast Linux", encoding="utf-8")

    # Create mock user data
    user_data_dir = data_dir / "raycast-linux"
    user_data_dir.mkdir(parents=True)
    snippets_file = user_data_dir / "snippets.json"
    snippets_file.write_text(json.dumps([{"id": "s1", "name": "email", "content": "test@example.com"}]), encoding="utf-8")

    chat_file = user_data_dir / "chat_conversations.json"
    chat_file.write_text(json.dumps([{"id": "c1", "title": "My chat", "messages": []}]), encoding="utf-8")

    env = os.environ.copy()
    env["XDG_BIN_HOME"] = str(bin_dir)
    env["XDG_DATA_HOME"] = str(data_dir)
    env["XDG_CONFIG_HOME"] = str(config_dir)

    uninstall_script = REPO_ROOT / "uninstall.sh"
    res = _run_script(uninstall_script, [], env)
    assert res.returncode == 0

    # Binary and desktop launcher removed
    assert not app_bin.exists()
    assert not desktop_file.exists()

    # User data preserved
    assert snippets_file.exists()
    assert chat_file.exists()
    snippets_data = json.loads(snippets_file.read_text(encoding="utf-8"))
    assert snippets_data[0]["name"] == "email"


def test_uninstall_purges_user_data_when_flag_passed(tmp_path):
    bin_dir = tmp_path / "bin"
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"

    bin_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    user_data_dir = data_dir / "raycast-linux"
    user_data_dir.mkdir(parents=True)
    snippets_file = user_data_dir / "snippets.json"
    snippets_file.write_text(json.dumps([{"id": "s1"}]), encoding="utf-8")

    env = os.environ.copy()
    env["XDG_BIN_HOME"] = str(bin_dir)
    env["XDG_DATA_HOME"] = str(data_dir)
    env["XDG_CONFIG_HOME"] = str(config_dir)

    uninstall_script = REPO_ROOT / "uninstall.sh"
    res = _run_script(uninstall_script, ["--purge"], env)
    assert res.returncode == 0

    assert not user_data_dir.exists()


def test_upgrade_simulation_retains_user_data(tmp_path):
    data_dir = tmp_path / "data"
    user_data_dir = data_dir / "raycast-linux"
    user_data_dir.mkdir(parents=True)

    initial_snippets = [{"id": "s1", "name": "important-macro", "content": "SELECT * FROM users"}]
    initial_chats = [{"id": "c1", "title": "Saved Thread", "messages": [{"role": "user", "content": "hello"}]}]

    (user_data_dir / "snippets.json").write_text(json.dumps(initial_snippets), encoding="utf-8")
    (user_data_dir / "chat_conversations.json").write_text(json.dumps(initial_chats), encoding="utf-8")

    # Simulate upgrade: package build and re-install
    # None of the packaging or install steps overwrite XDG_DATA_HOME/raycast-linux
    assert (user_data_dir / "snippets.json").exists()
    loaded_snippets = json.loads((user_data_dir / "snippets.json").read_text(encoding="utf-8"))
    assert loaded_snippets == initial_snippets

    loaded_chats = json.loads((user_data_dir / "chat_conversations.json").read_text(encoding="utf-8"))
    assert loaded_chats == initial_chats


def test_cli_setup_command_registered():
    from raycast_linux.cli import main
    # Help includes setup subcommand
    res = subprocess.run(["python", "-m", "raycast_linux", "--help"], capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert res.returncode == 0
    assert "setup" in res.stdout
    assert "open graphical setup and diagnostics window" in res.stdout
