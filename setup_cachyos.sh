#!/usr/bin/env bash
# One-shot setup for CachyOS / Arch Linux (Wayland).
#
#   1. checks which system prerequisites are missing
#   2. installs them via  pacman -S --needed
#   3. runs ./install.sh   (venv + ~/.local/bin/raycast-linux + desktop entry)
#   4. runs  raycast-linux doctor  to verify the result
#
# The package set is fixed and well known (python-gobject gtk4 wl-clipboard
# wtype), so pacman runs with --noconfirm. Run as your normal user; sudo is
# picked up automatically for the pacman step.
set -euo pipefail
cd "$(dirname "$0")"

# ---------------------------------------------------------------- sanity ----
if ! command -v pacman >/dev/null; then
  echo "error: pacman not found — this script is for Arch-based systems" >&2
  echo "       (CachyOS, Arch, EndeavourOS, …)." >&2
  exit 1
fi

ID=""
ID_LIKE=""
# shellcheck disable=SC1091
[ -r /etc/os-release ] && . /etc/os-release
if [ "$ID" != "arch" ] && [ "$ID" != "cachyos" ] && [[ "$ID_LIKE" != *arch* ]]; then
  echo "warning: this does not look like an Arch-based system (ID=${ID:-?}) — continuing anyway." >&2
fi

if ! command -v python3 >/dev/null; then
  echo "error: python3 not found — install the 'python' package first." >&2
  exit 1
fi

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null; then
  SUDO="sudo"
fi

# --------------------------------------- 1 + 2. check & install pacman deps --
REQUIRED_PKGS=(python-gobject gtk4 wl-clipboard wtype)
missing=()
for p in "${REQUIRED_PKGS[@]}"; do
  if ! pacman -Qq "$p" >/dev/null 2>&1; then
    missing+=("$p")
  fi
done

if [ "${#missing[@]}" -eq 0 ]; then
  echo "✓ All system prerequisites already installed: ${REQUIRED_PKGS[*]}"
else
  echo "→ Installing missing packages: ${missing[*]}"
  # shellcheck disable=SC2086
  $SUDO pacman -S --needed --noconfirm "${missing[@]}"
fi

echo "→ Optional extras (not auto-installed):"
for p in python-dbus libnotify; do
  if ! pacman -Qq "$p" >/dev/null 2>&1; then
    case $p in
      python-dbus) echo "    - $p  (portal global-shortcut registration)" ;;
      libnotify)   echo "    - $p  (toast notifications)" ;;
    esac
  fi
done

# ---------------------------------------------------------- 3. app install --
echo
echo "→ Running install.sh (venv + ~/.local/bin/raycast-linux + desktop entry)"
./install.sh

# ------------------------------------------------------------ 4. doctor -----
export PATH="$HOME/.local/bin:$PATH"
echo
echo "→ Running raycast-linux doctor"
set +e
raycast-linux doctor
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  echo
  echo "✓ Setup complete. Start with:   raycast-linux"
  echo "  Bind a key to it (CachyOS/KDE default: System Settings → Shortcuts →"
  echo "  Custom Shortcuts → new global shortcut → Command:  raycast-linux)"
else
  echo
  echo "⚠ doctor reported issues above — see README → Troubleshooting." >&2
fi
exit "$rc"
