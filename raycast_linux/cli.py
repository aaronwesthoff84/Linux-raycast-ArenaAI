"""Command-line interface.

  raycast-linux            start the app, or toggle the palette if running
  raycast-linux server     run only the API backend (foreground)
  raycast-linux toggle     toggle the palette of a running instance
  raycast-linux env        print detected environment
  raycast-linux doctor     check display server, WM, tools, dependencies
  raycast-linux version
"""
from __future__ import annotations

import argparse
import json
import sys


def _cmd_app(args: argparse.Namespace) -> int:
    from .backend.instance import api_post, running_instance

    inst = running_instance()
    if inst:
        try:
            res = api_post("/api/palette/toggle")
            print(res.get("message", "Toggled"))
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"Found instance (pid {inst['pid']}) but could not reach it: {e}", file=sys.stderr)
            return 1
    from .main import run_gui
    return run_gui(show_settings=args.settings)


def _cmd_server(args: argparse.Namespace) -> int:
    import os
    import signal
    import time

    from .backend.instance import remove_api, running_instance, write_api
    from .backend.server import ServiceHub, run_server

    inst = running_instance()
    if inst:
        print(f"An instance is already running (pid {inst['pid']}, port {inst['port']}).")
        return 1

    def _terminate(signum, frame):  # SIGTERM → clean shutdown (remove api.json)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _terminate)

    hub = ServiceHub()
    hub, port = run_server(port=args.port, hub=hub, block=True)
    write_api(port)
    try:
        print(f"raycast-linux API on http://127.0.0.1:{port}  (pid {os.getpid()})")
        print("Ctrl+C to stop.")
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        remove_api()
    return 0


def _cmd_toggle(args: argparse.Namespace) -> int:
    from .backend.instance import api_post, running_instance

    inst = running_instance()
    if not inst:
        print("No raycast-linux instance is running. Start it with `raycast-linux`.")
        return 1
    try:
        res = api_post("/api/palette/toggle")
        print(res.get("message", "Toggled"))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"Could not reach the running instance: {e}", file=sys.stderr)
        return 1


def _cmd_env(args: argparse.Namespace) -> int:
    from .backend.windows import detect_provider
    from .platform import detect

    info = detect.env_info()
    info["window_provider"] = detect_provider().name
    print(json.dumps(info, indent=2))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .backend.windows import detect_provider
    from .platform import detect

    ok = True
    line = lambda good, label, detail="": print(f"  {'✓' if good else '✗'} {label}" + (f" — {detail}" if detail else ""))

    dm = detect.display_server()
    wm = detect.window_manager()
    tools = detect.tools()
    provider = detect_provider()

    print("raycast-linux doctor")
    print("  display server :")
    line(dm in ("wayland", "x11"), dm or "unknown", "headless session — the GUI will not show a window")
    print("  window manager :")
    line(wm != "unknown", wm, "WM not recognised; window tiling may be limited")
    print("  window provider:")
    line(provider.name not in ("none",), provider.name, provider.hint if provider.actions() == [] else "actions available")
    print("  clipboard tools:")
    if dm == "wayland":
        line(tools.get("wl-copy", False), "wl-copy", "apt/pacman: wl-clipboard")
        line(tools.get("wl-paste", False), "wl-paste", "apt/pacman: wl-clipboard")
        line(tools.get("wtype", False), "wtype", "needed to auto-type snippets on Wayland")
    else:
        line(tools.get("xclip", False) or tools.get("xsel", False), "xclip or xsel")
        line(tools.get("xdotool", False), "xdotool")
        line(tools.get("wmctrl", False), "wmctrl", "for next/previous window")
    print("  wm bridges:")
    line(tools.get("swaymsg", False), "swaymsg", "only needed on Sway")
    line(tools.get("hyprctl", False), "hyprctl", "only needed on Hyprland")
    print("  python packages:")
    for mod in ("fastapi", "uvicorn", "httpx"):
        try:
            __import__(mod)
            line(True, mod)
        except ImportError:
            line(False, mod, "pip install -e .")
            ok = False
    try:
        import dbus  # noqa: F401
        line(True, "python3-dbus", "enables portal global shortcut")
    except ImportError:
        line(False, "python3-dbus", "optional — without it, bind the shortcut in the compositor")
    try:
        import gi  # noqa: F401
        gi.require_version("Gtk", "4.0")
        line(True, "GTK 4 (python3-gi + gir1.2-gtk-4.0)")
    except Exception:
        line(False, "GTK 4", "install python3-gi and gir1.2-gtk-4.0")
        ok = False
    try:
        import gi
        gi.require_version("Notify", "0.7")
        line(True, "libnotify (optional)", "toast notifications")
    except Exception:
        line(False, "libnotify (optional)", "no toasts — everything still works")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="raycast-linux",
        description="Raycast-style launcher and productivity hub for Linux.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    p_app = sub.add_parser("app", help="start the app or toggle the palette (default)")
    p_app.add_argument("--settings", action="store_true", help="open the settings window on start")
    p_app.set_defaults(func=_cmd_app)

    p_srv = sub.add_parser("server", help="run only the API backend (foreground)")
    p_srv.add_argument("--port", type=int, default=0, help="port (default: pick a free one)")
    p_srv.set_defaults(func=_cmd_server)

    sub.add_parser("toggle", help="toggle the palette of a running instance").set_defaults(func=_cmd_toggle)
    sub.add_parser("env", help="print the detected environment as JSON").set_defaults(func=_cmd_env)
    sub.add_parser("doctor", help="check display server, WM, tools and dependencies").set_defaults(func=_cmd_doctor)

    args = parser.parse_args(argv)
    if args.version:
        from .version import __version__
        print(f"raycast-linux {__version__}")
        return 0
    if not args.command:
        args = argparse.Namespace(func=_cmd_app, settings=False)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
