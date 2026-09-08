#!/usr/bin/env bash
# Clean uninstallation script for raycast-linux.
# Removes application binaries, desktop entry, autostart, and local virtual environment.
# User data (snippets, chat history, configuration) is preserved by default.
set -euo pipefail

PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge)
      PURGE=1
      ;;
    -h|--help)
      echo "Usage: $0 [--purge]"
      echo "  --purge: also delete all user data (snippets, clipboard, chat history)"
      exit 0
      ;;
  esac
done

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/raycast-linux"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/raycast-linux"

echo "→ Removing raycast-linux wrapper: $BIN_DIR/raycast-linux"
rm -f "$BIN_DIR/raycast-linux"

echo "→ Removing desktop launcher: $DESKTOP_DIR/raycast-linux.desktop"
rm -f "$DESKTOP_DIR/raycast-linux.desktop"

echo "→ Removing icon: $ICON_DIR/raycast-linux.svg"
rm -f "$ICON_DIR/raycast-linux.svg"

echo "→ Removing autostart entry if present: $AUTOSTART_DIR/raycast-linux.desktop"
rm -f "$AUTOSTART_DIR/raycast-linux.desktop"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/.venv" ]; then
  echo "→ Removing local virtual environment: $SCRIPT_DIR/.venv"
  rm -rf "$SCRIPT_DIR/.venv"
fi

if [ "$PURGE" -eq 1 ]; then
  echo "→ Purging user data and configurations:"
  echo "  Deleting $DATA_DIR"
  rm -rf "$DATA_DIR"
  echo "  Deleting $CONFIG_DIR"
  rm -rf "$CONFIG_DIR"
  echo "✓ User data purged."
else
  echo
  echo "✓ raycast-linux application removed."
  echo "  User data preserved at: $DATA_DIR"
  echo "  To completely remove user data, re-run with: ./uninstall.sh --purge"
fi

if command -v pacman >/dev/null 2>&1; then
  if pacman -Qq raycast-linux >/dev/null 2>&1; then
    echo
    echo "Note: raycast-linux is also installed as a pacman system package."
    echo "To remove system package: sudo pacman -R raycast-linux"
  fi
fi
