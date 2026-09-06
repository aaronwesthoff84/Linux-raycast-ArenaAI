"""Minimal .desktop file parsing (freedesktop.org spec, the parts we need).

No external dependencies so the app list works even without PyGObject.
"""
from __future__ import annotations

import os
import re
import shlex

APPS_DIRS = [
    os.path.expanduser("~/.local/share/applications"),
    "/usr/local/share/applications",
    "/usr/share/applications",
]

_KEEP_KEYS = {
    "Name", "Comment", "Icon", "Exec", "Categories", "Keywords",
    "Terminal", "NoDisplay", "Type", "StartupWMClass", "GenericName",
}

_LOCALIZED_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9]*)(\[[^\]]+\])?$")
_PERCENT_TOKEN = re.compile(r"%[a-zA-Z%]")
_ENV_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def parse_desktop_file(path: str) -> dict | None:
    """Parse one .desktop file. Returns a normalized dict or None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None

    vals: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "[")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        m = _LOCALIZED_KEY.match(key)
        if not m:
            continue
        base = m.group(1)
        if base not in _KEEP_KEYS:
            continue
        # A localized key (Name[de]=…) never overrides the plain key.
        if base in vals and m.group(2):
            continue
        if base not in vals:
            vals[base] = value.strip()

    if vals.get("Type", "Application") != "Application":
        return None
    if vals.get("NoDisplay", "").lower() == "true":
        return None
    name = vals.get("Name")
    exec_ = vals.get("Exec")
    if not name or not exec_:
        return None

    return {
        "id": os.path.splitext(os.path.basename(path))[0],
        "name": re.sub(r"[*_]", "", name),
        "generic": vals.get("GenericName", ""),
        "comment": vals.get("Comment", ""),
        "icon": vals.get("Icon", ""),
        "exec": exec_,
        "categories": [c for c in vals.get("Categories", "").split(";") if c],
        "keywords": [k for k in vals.get("Keywords", "").split(";") if k],
        "terminal": vals.get("Terminal", "").lower() == "true",
        "path": path,
    }


def load_desktop_files(dirs: list[str]) -> list[dict]:
    """Load every usable .desktop file. User dir wins over system dirs."""
    seen: dict[str, dict] = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            if not n.endswith(".desktop"):
                continue
            app = parse_desktop_file(os.path.join(d, n))
            if app and app["id"] not in seen:
                seen[app["id"]] = app  # earlier (more specific) dirs win
    return list(seen.values())


def command_for(app: dict) -> tuple[list[str], list[str]]:
    """Split an Exec line into (env_assignments, argv).

    ``VAR=1 cmd %f`` → ``(["VAR=1"], ["cmd"])``.
    Freedesktop field tokens (``%u %f …``) are dropped; launchers that need
    them (file managers) are started without an initial file, which matches
    what a launcher typically wants.
    """
    try:
        parts = shlex.split(app.get("exec", ""))
    except ValueError:
        return [], []
    env: list[str] = []
    i = 0
    while i < len(parts) and _ENV_PREFIX.match(parts[i]):
        env.append(parts[i])
        i += 1
    cmd = [p for p in parts[i:] if not _PERCENT_TOKEN.search(p)]
    if not cmd:
        return [], []
    return env, cmd
