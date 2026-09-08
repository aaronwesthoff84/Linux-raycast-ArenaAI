#!/usr/bin/env bash
# Build the source tarball expected by packaging/PKGBUILD
# (packaging/raycast-linux-<ver>.tar.gz), staged as raycast-linux-<ver>/.
# Also generates packaging/SHA256SUMS for release integrity verification.
set -euo pipefail
cd "$(dirname "$0")/.."

PKG=raycast-linux
VER=1.0.0
TARBALL="packaging/${PKG}-${VER}.tar.gz"
SUMS="packaging/SHA256SUMS"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/$PKG-$VER/files"
cp -r raycast_linux pyproject.toml requirements.txt README.md LICENSE \
  uninstall.sh setup_cachyos.sh "$STAGE/$PKG-$VER/"
cp packaging/raycast-linux.desktop packaging/raycast-linux.svg \
  "$STAGE/$PKG-$VER/files/"

tar -C "$STAGE" -czf "$TARBALL" "$PKG-$VER"

# Generate SHA256 integrity checksum
if command -v sha256sum >/dev/null 2>&1; then
  (cd packaging && sha256sum "${PKG}-${VER}.tar.gz" > "SHA256SUMS")
elif command -v shasum >/dev/null 2>&1; then
  (cd packaging && shasum -a 256 "${PKG}-${VER}.tar.gz" > "SHA256SUMS")
fi

echo "→ Generated tarball: $TARBALL"
if [ -f "$SUMS" ]; then
  echo "→ Integrity checksum:"
  cat "$SUMS"
fi
echo "Next: cd packaging && makepkg -si"
