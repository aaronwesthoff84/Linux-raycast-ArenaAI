#!/usr/bin/env bash
# Build a .deb that bundles the app + its own venv under /opt/raycast-linux.
# Run on a Debian/Ubuntu machine (dpkg-deb is required).
set -euo pipefail
cd "$(dirname "$0")/.."

PKG=raycast-linux
VER=1.0.0
STAGE=dist/deb-$PKG
rm -rf dist "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/$PKG" "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/scalable/apps"

# 1. venv with the app installed
python3 -m venv "$STAGE/opt/$PKG/.venv"
"$STAGE/opt/$PKG/.venv/bin/pip" install -q -U pip
"$STAGE/opt/$PKG/.venv/bin/pip" install -q .

# 2. wrapper (final install path)
cat > "$STAGE/usr/bin/$PKG" <<'EOF'
#!/bin/sh
exec /opt/raycast-linux/.venv/bin/python -m raycast_linux "$@"
EOF
chmod 755 "$STAGE/usr/bin/$PKG"

# 3. desktop entry + icon
cp packaging/raycast-linux.desktop "$STAGE/usr/share/applications/"
cp packaging/raycast-linux.svg     "$STAGE/usr/share/icons/hicolor/scalable/apps/"

# 4. control
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VER
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), gir1.2-gtk-4.0, python3-gi, xdg-utils, wl-clipboard | xclip
Description: Raycast-style launcher and productivity hub for Linux
 Native GTK4 command palette with fuzzy app/file search, clipboard history,
 text snippets, window tiling (Sway/Hyprland/X11) and a built-in calculator.
EOF

chmod 755 "$STAGE/DEBIAN"
dpkg-deb --build --root-owner-group "$STAGE" "dist/${PKG}_${VER}_all.deb"
echo "→ dist/${PKG}_${VER}_all.deb"
