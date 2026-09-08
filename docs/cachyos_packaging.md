# CachyOS and Arch Linux Packaging Guide

Date: 2026-09-08
Repository: aaronwesthoff84/Linux-raycast-ArenaAI
Package: raycast-linux
Target distributions: CachyOS, Arch Linux, EndeavourOS, Manjaro

## Package Architecture

The `raycast-linux` package adheres to Arch Linux packaging standards and PEP 668 safety:
1. Application Code: Installed into an isolated virtual environment at `/opt/raycast-linux/.venv` using `--system-site-packages` and `--no-deps`.
2. Python Runtime Dependencies: Provided by native Arch Linux packages (`python-fastapi`, `uvicorn`, `python-httpx`, `python-pydantic`, `python-gobject`, `gtk4`).
3. User Environment Wrapper: Executable placed at `/usr/bin/raycast-linux` launching the application via `/opt/raycast-linux/.venv/bin/python -m raycast_linux "$@"`.
4. Desktop Integration: Desktop entry placed at `/usr/share/applications/raycast-linux.desktop` and vector icon at `/usr/share/icons/hicolor/scalable/apps/raycast-linux.svg`.

## Installation Methods

### Method 1: Automated Script (Recommended for Developers)

Run the one-shot setup script from the cloned repository:
```bash
./setup_cachyos.sh
```
This script verifies and installs missing prerequisites (`python-gobject`, `gtk4`, `wl-clipboard`, `wtype`), builds the local virtual environment with system site packages, creates desktop launchers, and executes `raycast-linux doctor`.

### Method 2: Arch / CachyOS PKGBUILD (makepkg)

Build and install the package with pacman:
```bash
# Generate the release source tarball and integrity checksum
./packaging/build-source.sh

# Build and install package via makepkg
cd packaging
makepkg -si
```

### Method 3: Graphical Setup

After installing, open the graphical setup and diagnostic window:
```bash
raycast-linux setup
```
The setup window allows you to:
- Verify system display server and Wayland tool availability
- Test palette appearance and toggling
- Register the global Super+Space shortcut via XDG desktop portal
- Enable or disable login autostart

## Release Integrity Verification

Official release archives are distributed with SHA256 checksums in `packaging/SHA256SUMS`.
To verify integrity before installation:
```bash
sha256sum -c packaging/SHA256SUMS
```

## Update Instructions

### Source Install Update
To update a source installation while preserving all user data:
```bash
git pull origin main
./install.sh
```

### Package Manager Update
When installed through pacman or an AUR helper:
```bash
yay -Syu raycast-linux
```

User data directories (`~/.local/share/raycast-linux` and `~/.config/raycast-linux`) store user configurations, snippets, clipboard history, and chat threads. They are located outside the package root and are preserved during updates.

## Uninstallation Instructions

### Clean Uninstall (Preserves User Data)
To remove the application binaries, desktop entry, and icons while keeping your snippets, clipboard history, and chat conversations:
```bash
./uninstall.sh
```
If installed through pacman:
```bash
sudo pacman -R raycast-linux
```

### Full Purge (Removes User Data)
To remove all application binaries and purge all saved user data:
```bash
./uninstall.sh --purge
```
