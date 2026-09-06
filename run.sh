#!/usr/bin/env bash
# Run from a source checkout (creates .venv on first use).
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q -U pip
  ./.venv/bin/pip install -q -e .
fi
exec ./.venv/bin/python -m raycast_linux "$@"
