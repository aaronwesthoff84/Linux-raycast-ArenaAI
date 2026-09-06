#!/usr/bin/env bash
# Install raycast-linux into a local venv with a wrapper on PATH.
# System dependencies are NOT installed — see README (or run `raycast-linux doctor`).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
REAL="$(pwd)"

echo "→ creating venv ($REAL/.venv)"
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip
pip install -q -e .

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
