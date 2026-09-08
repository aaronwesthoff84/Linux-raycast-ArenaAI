#!/usr/bin/env bash
# Install raycast-linux into a local venv with a wrapper on PATH.
# System dependencies are NOT installed — see README (or run `raycast-linux doctor`).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
REAL="$(pwd)"

echo "→ creating venv ($REAL/.venv)"
"$PY" -m venv --system-site-packages .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip
pip install -q -e .

echo "→ verifying system GTK bindings in venv"
if ! "$REAL/.venv/bin/python" -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk" 2>/dev/null; then
  echo "⚠ warning: PyGObject / GTK4 is not importable from .venv." >&2
  echo "  On Arch/CachyOS: sudo pacman -S python-gobject gtk4" >&2
  echo "  On Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0" >&2
fi

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/raycast-linux" <<EOF
#!/bin/sh
exec "$REAL/.venv/bin/python" -m raycast_linux "\$@"
EOF
chmod +x "$BIN_DIR/raycast-linux"

# Desktop entry (optional, so the app shows up in menus)
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"
cp packaging/raycast-linux.desktop "$DESKTOP_DIR/"

echo
echo "Installed."
echo "  start / toggle : raycast-linux"
echo "  check setup    : raycast-linux doctor"
case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) echo "  note: add $BIN_DIR to your PATH" ;;
esac
