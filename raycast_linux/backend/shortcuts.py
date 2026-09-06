"""Global shortcut registration through the XDG GlobalShortcuts portal.

GNOME and KDE implement ``org.freedesktop.portal.GlobalShortcuts``. This
module registers a handler object on the session bus; when the user presses
the chosen combination (default ``super+space``) the portal:

  1. calls ``GetStatus()`` on our handler object (liveness check),
  2. emits an ``Activate`` signal *on our object path* — which we catch with
     a bus-wide signal receiver filtered to our path.

Best-effort by design:
  * needs ``python3-dbus`` (system package) — without it we return a message
    with the compositor-level fallback (bind ``raycast-linux toggle``).
  * on compositors without a portal implementation the registration fails
    gracefully with the same fallback message.

Compositor fallbacks (always work, no portal needed):
  sway:      bindsym $mod+space exec raycast-linux
  Hyprland:  bind =SUPER,SPC, exec, raycast-linux
  KDE:       System Settings → Shortcuts → Custom Shortcuts → new global
             shortcut → Command to Run: raycast-linux
  GNOME:     Settings → Keyboard → Custom Shortcuts → New shortcut
             (Super+Space) → raycast-linux
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("raycast-linux.shortcuts")

PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"
SHORTCUT_IFACE = "org.freedesktop.portal.GlobalShortcuts.Shortcut"
PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
HANDLER_BUS_NAME = "dev.arena.raycast_linux.shortcut"
HANDLER_PATH = "/dev/arena/raycast_linux/shortcut"
SESSION_PATH = "/dev/arena/raycast_linux/session"

_FALLBACK_MSG = (
    "Global shortcut not registered via the portal. Bind the key in your "
    "compositor and run: raycast-linux toggle  "
    "(sway: bindsym $mod+space exec raycast-linux; "
    "Hyprland: bind =SUPER,SPC, exec, raycast-linux)"
)


class GlobalShortcutPortal:
    """Registers one global shortcut with the portal; emits via callback."""

    def __init__(self) -> None:
        self._bus = None
        self._handler = None
        self._session_obj = None
        self._shortcut_id: str | None = None
        self._shortcut_string: str | None = None
        self._on_activate = None
        self._lock = threading.Lock()
        self.status = "unregistered"

    # -- API used by the server -------------------------------------------
    def set_on_activate(self, callback) -> None:
        self._on_activate = callback

    @property
    def registered(self) -> bool:
        return self.status == "registered"

    @property
    def shortcut_id(self) -> str | None:
        return self._shortcut_id

    @property
    def shortcut(self) -> str | None:
        return self._shortcut_string

    def register(self, shortcut: str = "super+space") -> dict:
        if self._on_activate is None:
            return {"ok": False, "message": "No activation handler attached"}
        try:
            import dbus  # python3-dbus (system package)
            import dbus.service
        except ImportError:
            return {
                "ok": False,
                "message": _FALLBACK_MSG + "  (install python3-dbus to try the portal again)",
            }
        with self._lock:
            if self._shortcut_id:
                return {"ok": True, "message": f"Already registered as {self._shortcut_id}"}
            try:
                bus = dbus.SessionBus()
                bus.request_name(HANDLER_BUS_NAME)

                portal = self

                class _Handler(dbus.service.Object):
                    """org.freedesktop.portal.GlobalShortcuts.Shortcut."""

                    @dbus.service.method(SHORTCUT_IFACE, out_signature="u")
                    def GetStatus(self):
                        # 0=unregistered, 1=registering, 2=registered
                        return dbus.UInt32(2 if portal._shortcut_id else 1)

                    @dbus.service.method(SHORTCUT_IFACE, in_signature="a{sv}")
                    def UpdateProperties(self, properties):
                        return None

                    @dbus.service.method(SHORTCUT_IFACE)
                    def Destroy(self):
                        threading.Thread(target=portal.unregister, daemon=True).start()
                        return None

                self._session_obj = dbus.service.Object(bus, SESSION_PATH)
                self._handler = _Handler(bus, HANDLER_PATH)
                bus.add_signal_receiver(
                    self._signal_activated,
                    sender_name=None,  # the portal emits the signal
                    signal_name="Activate",
                    interface_name=SHORTCUT_IFACE,
                    path_keyword="path",
                )

                proxy = bus.get_object(PORTAL_SERVICE, PORTAL_PATH)
                iface = dbus.Interface(proxy, PORTAL_IFACE)
                token = f"raycast-linux-{time.time_ns()}"
                iface.Create(token, dbus.ObjectPath(SESSION_PATH),
                             dbus.Dictionary({}, signature="sv"))
                status, results = iface.CreateShortcut(
                    token,
                    dbus.ObjectPath(HANDLER_PATH),
                    shortcut,
                    dbus.Dictionary({}, signature="sv"),
                )
                results = dict(results)
                if status != 0:  # 0 = success
                    reason = str(results.get("message", "portal returned an error"))
                    self._cleanup_bus()
                    return {"ok": False, "message": f"{reason} — {_FALLBACK_MSG}"}
                self._shortcut_id = str(results.get("id", ""))
                self._shortcut_string = str(results.get("shortcut", shortcut))
                self.status = "registered"
                self._bus = bus
                log.info("Global shortcut registered: %s", self._shortcut_string)
                return {
                    "ok": True,
                    "message": f"Global shortcut registered: {self._shortcut_string}",
                    "id": self._shortcut_id,
                    "shortcut": self._shortcut_string,
                }
            except Exception as e:  # noqa: BLE001
                log.warning("Portal registration failed: %s", e)
                self._cleanup_bus()
                return {
                    "ok": False,
                    "message": f"Portal unavailable ({e.__class__.__name__}) — {_FALLBACK_MSG}",
                }

    def unregister(self) -> dict:
        with self._lock:
            if not self._shortcut_id:
                self._cleanup_bus()
                self.status = "unregistered"
                return {"ok": True, "message": "Nothing to unregister"}
            self._shortcut_id = None
            self._shortcut_string = None
            self.status = "unregistered"
        self._cleanup_bus()
        return {"ok": True, "message": "Global shortcut unregistered"}

    def status(self) -> dict:
        return {
            "registered": self.registered,
            "id": self._shortcut_id,
            "shortcut": self._shortcut_string,
            "status": self.status,
        }

    # -- internals -----------------------------------------------------------
    def _signal_activated(self, path: str = "") -> None:
        if path != HANDLER_PATH:
            return  # another app's global shortcut firing
        cb = self._on_activate
        if cb:
            # We're on the dbus-python bus thread — don't block it.
            threading.Thread(target=self._fire, args=(cb,), daemon=True).start()

    def _fire(self, cb) -> None:
        try:
            cb()
        except Exception:  # noqa: BLE001
            log.exception("on_activate callback failed")

    def _cleanup_bus(self) -> None:
        bus, self._bus = self._bus, None
        try:
            if bus is not None:
                if self._handler is not None:
                    self._handler.remove_from_connection()
                if self._session_obj is not None:
                    self._session_obj.remove_from_connection()
                bus.remove_signal_receiver(self._signal_activated)
        except Exception:  # noqa: BLE001
            log.debug("bus cleanup issue", exc_info=True)
        self._handler = None
        self._session_obj = None
