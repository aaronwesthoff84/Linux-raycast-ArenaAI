"""GUI entry point: starts the in-process API server + the GTK app.

GTK is imported lazily so ``raycast-linux server`` / ``doctor`` / tests
work on machines without a desktop.
"""
from __future__ import annotations

import os
import sys


def run_gui(show_settings: bool = False) -> int:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
    except (ImportError, ValueError) as e:
        print(
            "GTK 4 is required for the GUI.\n"
            "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0\n"
            "  Fedora:        sudo dnf install python3-gobject gtk4\n"
            "  Arch:          sudo pacman -S python-gobject gtk4\n"
            f"(import failed: {e})\n"
            "You can still run the API only:  raycast-linux server",
            file=sys.stderr,
        )
        return 1

    from .backend.instance import remove_api, write_api
    from .backend.server import ServiceHub, run_server
    from .frontend.app import RaycastLinuxApp

    hub = ServiceHub()
    hub, port = run_server(
        port=int(os.environ.get("RAYCAST_LINUX_PORT", "0")),
        hub=hub,
        block=False,
    )
    write_api(port)
    try:
        app = RaycastLinuxApp(hub=hub, port=port, show_settings=show_settings)
        return int(app.run([]))
    finally:
        remove_api()
