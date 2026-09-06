#!/usr/bin/env bash
# Best-effort AppImage build via PyInstaller + AppDir.
#
# GTK/PyGObject + PyInstaller is fiddly; if the one-file binary fails to
# start, prefer the .deb (build-deb.sh) or a plain venv install — both are
# first-class. This script is provided for the small-binary crowd.
set -euo pipefail
cd "$(dirname "$0")/.."

PYBIN=python3
rm -rf dist/raycast-linux onefile
"$PYBIN" -m venv .appimage-venv
./.appimage-venv/bin/pip install -q -U pip
./.appimage-venv/bin/pip install -q . pyinstaller

./.appimage-venv/bin/pyinstaller \
  --onefile \
  --name raycast-linux \
  --hidden-import gi \
  --collect-all gi \
  --collect-all cairo \
  --collect-all gdkpixbuf \
  --add-data "raycast_linux/frontend/styles.css:frontend" \
  raycast_linux/__main__.py

# Assemble an AppDir and (if linuxdeploy is available) produce the AppImage.
APPDIR=dist/raycast-linux
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"
mv dist/raycast-linux.bin "$APPDIR/usr/bin/raycast-linux"
cp packaging/raycast-linux.desktop "$APPDIR/usr/share/applications/"
cp packaging/raycast-linux.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
cat > "$APPDIR/raycast-linux.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Raycast Linux
Exec=raycast-linux
Icon=raycast-linux
Terminal=false
Categories=Utility;
EOF

if command -v linuxdeploy >/dev/null; then
  linuxdeploy --appdir "$APPDIR" --output appimage
  echo "→ dist/raycast-linux-*.AppImage"
else
  echo "linuxdeploy not found — AppDir left at $APPDIR (run linuxdeploy yourself)."
fi
