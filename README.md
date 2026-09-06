# raycast-linux

A **Raycast-style launcher and productivity hub for Linux** — native GTK4
frontend + Python API backend, one binary, no Electron.

```
┌────────────────────────────────────────────────────────┐
│  🔍  chrome                       WAYLAND · hyprland   │
│  [General][Apps][Files][Clipboard][Snippets][Win][Set] │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1024              2^10  →  copy        CALC      │  │
│  │ Google Chrome     A fast web browser  APPS       │  │
│  │ chrome.conf       project/config      FILES      │  │
│  │ https://example…  23 chars ⏎ 2 lines CLIP        │  │
│  │ email             you@example.com     SNIP       │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

## Quick Start

The whole setup is: install a few packages → run one script → bind a key.

**CachyOS / Arch (Wayland) — one command does it all:**

```bash
git clone <this-repo> raycast-linux && cd raycast-linux
./setup_cachyos.sh
```

`setup_cachyos.sh` checks for and installs any missing packages
(`python-gobject gtk4 wl-clipboard wtype`) via `pacman -S --needed`,
creates a venv, installs the app to `~/.local/bin/raycast-linux`, adds a
desktop entry, and finishes by running `raycast-linux doctor` to verify
everything.

**Then bind a key** so the palette opens on demand (see
[Global shortcut](#global-shortcut) — on stock CachyOS/KDE: System
Settings → Shortcuts → Custom Shortcuts → new shortcut running
`raycast-linux`).

**Manual install (any distro):**

```bash
# 1. system dependencies
# CachyOS / Arch (Wayland):
sudo pacman -S --needed python-gobject gtk4 wl-clipboard wtype
# Debian/Ubuntu:
sudo apt install python3-gi gir1.2-gtk-4.0 wl-clipboard wtype
# Fedora: dnf install python3-gobject gtk4 wl-clipboard wtype

# X11 instead of Wayland:
# Arch/CachyOS:  sudo pacman -S --needed xclip xdotool wmctrl
# Debian/Ubuntu: sudo apt install xclip xdotool wmctrl

# Sway / Hyprland need nothing extra (swaymsg / hyprctl ship with them).
# Optional: sudo pacman -S python-dbus   (portal global shortcut;
#          Debian: python3-dbus)

# 2. install
./install.sh            # venv + ~/.local/bin/raycast-linux + desktop entry
# or: make venv && make run

# 3. check everything the machine provides
raycast-linux doctor

# 4. go
raycast-linux
```

## Features

| Raycast feature        | raycast-linux                                                            |
| ---------------------- | ------------------------------------------------------------------------ |
| Command palette        | Global shortcut opens a floating, borderless, always-on-top palette      |
| App launching          | Fuzzy search over all `.desktop` apps, launch with Enter                 |
| File search & open     | Index of `$HOME` (skips hidden/build dirs), open with default app        |
| Clipboard history      | Polls the system clipboard (wl-clipboard / xclip), keeps last 200        |
| Snippets               | Local snippet store; expands by **typing into the focused window**       |
| Window management      | Left/right/top/bottom/center/maximize/close/next/prev per compositor     |
| Calculator             | Live as you type: `2^10`, `2pi`, `sqrt(16)`, unit conversion `100 c f`   |
| Categories             | `>` prefix or Tab to jump: apps, files, clipboard, snippets, windows, settings |
| Global shortcut        | XDG GlobalShortcuts portal (GNOME/KDE) **or** compositor binding (all WMs) |
| Settings window        | Snippet editor, shortcut registration, clipboard/index management        |

## Using the palette

| Key              | Action                                             |
| ---------------- | -------------------------------------------------- |
| type             | fuzzy search (calculator runs live as you type)    |
| `>` + word + ` ` | jump to a category (table below)                   |
| `↑` / `↓`        | move selection (wraps)                             |
| `PgUp` / `PgDn`  | move 5 rows                                        |
| `Enter`          | run the selected item                              |
| `Tab` / `Shift+Tab` | switch category chips                            |
| `Esc`            | close the palette                                  |

| Prefix        | Category    | Example                     |
| ------------- | ----------- | --------------------------- |
| `>apps`       | Apps        | `>apps fire` → Firefox      |
| `>files`      | Files       | `>files config`             |
| `>clip`       | Clipboard   | `>clip token`               |
| `>snippet`    | Snippets    | `>snippet email`            |
| `>win`        | Windows     | `>win left` → snap left     |
| `>settings`   | Settings    | `>settings`                 |

Notes:

* The **first** `>files` search takes a moment while `$HOME` is indexed
  (the status bar shows progress; rebuild anytime via
  *Rebuild file index* in the Settings category).
* **Enter** on a clipboard entry copies it; on a snippet it hides the
  palette, returns focus to your previous window, and types the snippet.
* On machines without a typing tool (`wtype`/`xdotool`), snippet expansion
  falls back to copying so you can paste with `Ctrl+V`.

## Architecture

One process, two layers:

```
raycast-linux (GTK4 GUI)                ──HTTP──▶   FastAPI backend (in-process, 127.0.0.1)
├─ PaletteWindow (floating palette)                     ├─ AppService     (.desktop parsing, launch)
├─ SettingsWindow                                       ├─ FileIndex      ($HOME scan, fuzzy)
├─ ApiClient (httpx, thread pool → GLib.idle_add)       ├─ ClipboardService (poll, history, copy)
└─ key handling, fuzzy UI state                         ├─ SnippetService (CRUD, expand via wtype)
                                                        ├─ WindowProviders (sway/hyprland/x11/none)
                                                        └─ GlobalShortcutPortal (xdg portal, dbus)
```

* The backend runs headless-safe (no GTK imports) and is also available
  standalone: `raycast-linux server` — the whole feature set is an HTTP API.
* A single instance is enforced via `~/.local/state/raycast-linux/api.json`;
  running `raycast-linux` again toggles the palette of the live instance —
  which is exactly what compositor key bindings call.

## Global shortcut

**Option A — compositor binding (works on every WM, recommended):**

| WM        | Config                                                                  |
| --------- | ----------------------------------------------------------------------- |
| Sway      | `bindsym $mod+space exec raycast-linux`                                  |
| Hyprland  | `bind =SUPER,SPC, exec, raycast-linux`                                   |
| KDE       | System Settings → Shortcuts → Custom Shortcuts → `raycast-linux`         |
| GNOME     | Settings → Keyboard → Custom Shortcuts → `raycast-linux` (Super+Space)   |
| labwc     | `labwc-rc` keybind → `exec raycast-linux`                                |

**Option B — XDG GlobalShortcuts portal (GNOME/KDE, no config file):**
open Settings → Global shortcut → Register, or run the command
`Register global shortcut (portal)` from the palette itself. The app
registers `Super+Space` through `xdg-desktop-portal` (needs `python-dbus`
on Arch/CachyOS, `python3-dbus` elsewhere). A stock CachyOS install
(KDE Plasma) supports both options — the portal works out of the box.

## Window management on Wayland

Wayland has no universal cross-window geometry API, so tiling is done through
compositor bridges:

* **Sway** — `swaymsg move position` + `resize set`, focus cycling, close.
* **Hyprland** — `hyprctl dispatch split/centerwindow/…`.
* **X11 (any WM)** — full geometry via `xdotool` + `wmctrl` (next/prev).
* **Other Wayland compositors** — the palette still works fully; window
  actions show a notice. Use your compositor's own snap shortcuts
  (they coexist with raycast-linux).

## Calculator

Type in the palette (General or Files category):

* `2^10` → `1024` · `2+2*3` → `8` · `5--3` → `8`
* `sqrt(16)` · `2pi` · `3(4+1)` · `sin(0)` · `1.5e-2`
* units: `100 c f` → `212 f` · `5 km mi` → `3.10685596 mi` · `1 lb kg`
* Enter copies the result to the clipboard

## CLI

```
raycast-linux             start the app, or toggle the palette if already running
raycast-linux app         same as above (explicit subcommand)
raycast-linux app --settings   also open the settings window on start
raycast-linux server      API backend only (foreground) — scriptable!
raycast-linux toggle      toggle the palette of a running instance
raycast-linux env         detected environment as JSON
raycast-linux doctor      display server / WM / tools / dependency check
raycast-linux --version
```

Example one-liner (launch Firefox through the API of a running instance):

```bash
curl -s -X POST http://127.0.0.1:$(python3 -c "import json;print(json.load(open('$XDG_STATE_HOME/raycast-linux/api.json'))['port'])")/api/apps/launch -H 'content-type: application/json' -d '{"id":"firefox"}'
```

## HTTP API (abridged)

| Method & path                    | Purpose                                  |
| -------------------------------- | ---------------------------------------- |
| `GET /api/health`                | liveness + display/WM info               |
| `GET /api/env`                   | tools, provider, data dirs, index status |
| `GET /api/apps?query=`           | fuzzy app search                         |
| `POST /api/apps/launch` `{id}`   | launch an app                            |
| `GET /api/files?query=&refresh=` | fuzzy file search (auto-builds index)    |
| `POST /api/files/open` `{path}`  | open with default app                    |
| `GET /api/clipboard?query=`      | clipboard history                        |
| `GET /api/clipboard/{id}`        | one full clipboard item                  |
| `POST /api/clipboard/copy` `{text}` / `POST …/clear` | clipboard ops        |
| `GET/POST/PUT/DELETE /api/snippets…` | snippet CRUD                         |
| `POST /api/snippets/{id}/expand` | type a snippet into the focused window   |
| `GET /api/windows`               | provider + supported actions             |
| `POST /api/windows/action` `{action}` | move/resize/close/next/prev         |
| `POST /api/windows/stash-active` / `POST /api/windows/refocus` | focus bookkeeping |
| `GET/POST/DELETE /api/shortcuts` | global shortcut portal registration      |
| `POST /api/palette/toggle`       | show/hide the palette (used by bindings) |

## Data & state

* `~/.local/share/raycast-linux/` — `snippets.json`, `clipboard.json`
* `~/.local/state/raycast-linux/api.json` — live instance pid + port

### Uninstall

```bash
# pacman (PKGBUILD install):
sudo pacman -Rns raycast-linux

# venv install:
rm -rf <repo>/.venv ~/.local/bin/raycast-linux \
   ~/.local/share/applications/raycast-linux.desktop

# your data (optional):
rm -rf ~/.local/share/raycast-linux ~/.local/state/raycast-linux
```

## Packaging

**CachyOS / Arch — pacman-tracked (recommended here):**

```bash
./packaging/build-source.sh     # creates packaging/raycast-linux-1.0.0.tar.gz
cd packaging && makepkg -si     # builds + installs; runtime deps come from
                                # pacman (python-fastapi, gtk4, …)
# afterwards: pacman -Qi raycast-linux · pacman -Rns raycast-linux
```

The PKGBUILD is AUR-ready — set a real `url=` and replace
`sha256sums=(SKIP)` with a checksum before submitting.

**Other formats:**

```bash
make deb        # dist/raycast-linux_1.0.0_all.deb (bundles its own venv)
make appimage   # best-effort PyInstaller AppImage
./install.sh    # venv + PATH wrapper (no package-manager tracking)
```

## Development

```bash
make venv       # .venv with the app + pytest
make test       # pure-logic + API tests (run headless)
make server     # API only, in the terminal
make source     # build the source tarball for the PKGBUILD
make pkgbuild   # source + makepkg -si
```

Project layout:

```
raycast_linux/
├── cli.py            entry points (app/server/toggle/env/doctor)
├── main.py           GUI bootstrap (imports GTK lazily)
├── logic/            pure python: fuzzy, calculator, units, .desktop
├── platform/         display/WM detection, clipboard + typing helpers
├── backend/          FastAPI server, services, portal, single-instance
└── frontend/         GTK4 app, palette, settings, CSS
packaging/            PKGBUILD, deb/AppImage scripts, .desktop, icon
tests/                headless unit + API tests (pytest)
```

## Troubleshooting

Run `raycast-linux doctor` — it reports the display server, WM, available
tools and missing packages, e.g. on a healthy CachyOS (Wayland) session:

```
raycast-linux doctor
  display server :
  ✓ wayland
  window manager :
  ✓ kwin
  …
  python packages:
  ✓ fastapi
  ✓ uvicorn
  ✓ httpx
  ✓ GTK 4 (python3-gi + gir1.2-gtk-4.0)
```

Common issues (Arch/CachyOS package names first):

* **“GTK 4 is required”** — `sudo pacman -S python-gobject gtk4`
  (Debian/Ubuntu: `python3-gi` + `gir1.2-gtk-4.0`).
* **Clipboard history stays empty on Wayland** — `sudo pacman -S wl-clipboard`.
* **Snippets only copy instead of typing** — `sudo pacman -S wtype`
  (Wayland) / `xdotool` (X11).
* **“Portal unavailable”** — your compositor has no GlobalShortcuts
  implementation; use the compositor binding (Option A above). On
  CachyOS/KDE just `sudo pacman -S python-dbus` and retry.
* **Window actions say “not supported”** — your WM is not bridged yet;
  Sway and Hyprland are built in.

## Roadmap

* Image clipboard history (wl-paste --deref + thumbnails)
* Snippet variables (`{date}`, `{user}`, `{clipboard}`)
* KWin/GNOME tiling bridge via KWin scripting
* Plugin system (the HTTP API is the seam)
* Raycast-style themes

## License

[MIT](LICENSE)
