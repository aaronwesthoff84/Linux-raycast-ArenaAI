#!/usr/bin/env bash
# Build the source tarball expected by packaging/PKGBUILD
# (packaging/raycast-linux-<ver>.tar.gz), staged as raycast-linux-<ver>/.
set -euo pipefail
cd "$(dirname "$0")/.."

PKG=raycast-linux
VER=1.0.0
TARBALL="packaging/${PKG}-${VER}.tar.gz"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/$PKG-$VER/files"
cp -r raycast_linux pyproject.toml requirements.txt README.md LICENSE \
  "$STAGE/$PKG-$VER/"
cp packaging/raycast-linux.desktop packaging/raycast-linux.svg \
  "$STAGE/$PKG-$VER/files/"

tar -C "$STAGE" -czf "$TARBALL" "$PKG-$VER"
echo "→ $TARBALL"
echo "Next:  cd packaging && makepkg -si"
