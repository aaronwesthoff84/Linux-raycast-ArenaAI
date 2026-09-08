"""Global shortcut registration through the official XDG GlobalShortcuts portal.

Implements org.freedesktop.portal.GlobalShortcuts according to the freedesktop spec:
  https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html

Workflow:
  1. CreateSession(options) -> Request object path
  2. Wait for Request.Response signal -> yields session_handle
  3. BindShortcuts(session_handle, shortcuts, parent_window, options) -> Request object path
  4. Wait for Request.Response signal -> binds shortcut
  5. Listen for Activated signal on org.freedesktop.portal.GlobalShortcuts
  6. On unregister / exit -> call Session.Close() on session_handle

Best-effort with clear fallback:
  * If python3-dbus is absent or the desktop portal is unavailable, registration
    fails gracefully and returns instructions for compositor bindings.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("raycast-linux.shortcuts")

PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"

SHORTCUT_ID = "toggle_palette"

_FALLBACK_MSG = (
    "Global shortcut not registered via the portal. Bind the key in your "
    "compositor and run: raycast-linux toggle  "
    "(sway: bindsym $mod+space exec raycast-linux; "
    "Hyprland: bind =SUPER,SPC, exec, raycast-linux)"
)


def _get_dbus():
    """Import dbus dependencies safely."""
    try:
        import dbus
        try:
            from dbus.mainloop.glib import DBusGMainLoop
            DBusGMainLoop(set_as_default=True)
        except Exception:
            pass
        return dbus, None
    except ImportError as err:
        return None, err


class GlobalShortcutPortal:
    """Registers one global shortcut with the portal; emits via callback."""

    def __init__(self) -> None:
        self._bus = None
        self._session_handle: str | None = None
        self._shortcut_id: str | None = None
        self._shortcut_string: str | None = None
        self._on_activate = None
        self._lock = threading.Lock()
        self._status_str = "unregistered"
        self._signal_receivers = []

    # -- API used by the server -------------------------------------------
    def set_on_activate(self, callback) -> None:
        self._on_activate = callback

    @property
    def registered(self) -> bool:
        return self._status_str == "registered"

    @property
    def shortcut_id(self) -> str | None:
        return self._shortcut_id

    @property
    def shortcut(self) -> str | None:
        return self._shortcut_string

    def register(self, shortcut: str = "super+space") -> dict:
        if self._on_activate is None:
            return {"ok": False, "message": "No activation handler attached"}

        dbus, err = _get_dbus()
        if dbus is None:
            return {
                "ok": False,
                "message": _FALLBACK_MSG + f"  (python3-dbus not available: {err})",
            }

        with self._lock:
            if self._shortcut_id and self.registered:
                return {"ok": True, "message": f"Already registered as {self._shortcut_id}"}

            try:
                bus = dbus.SessionBus()
                proxy = bus.get_object(PORTAL_SERVICE, PORTAL_PATH)
                iface = dbus.Interface(proxy, PORTAL_IFACE)

                # 1. CreateSession
                session_token = f"raycast_{time.time_ns()}"
                req_token = f"req_session_{time.time_ns()}"
                create_opts = dbus.Dictionary({
                    "session_handle_token": dbus.String(session_token, variant_level=1),
                    "handle_token": dbus.String(req_token, variant_level=1),
                }, signature="sv")

                create_req_path = iface.CreateSession(create_opts)
                sess_resp = self._wait_for_request(bus, dbus, create_req_path, timeout=4.0)
                if sess_resp["status"] != 0:
                    self._cleanup_bus(bus)
                    return {
                        "ok": False,
                        "message": f"CreateSession rejected (status {sess_resp['status']}) — {_FALLBACK_MSG}",
                    }

                session_handle = str(sess_resp["results"].get("session_handle", ""))
                if not session_handle:
                    self._cleanup_bus(bus)
                    return {
                        "ok": False,
                        "message": f"Portal returned no session handle — {_FALLBACK_MSG}",
                    }

                self._session_handle = session_handle

                # 2. BindShortcuts
                bind_token = f"req_bind_{time.time_ns()}"
                shortcuts_data = [
                    (
                        SHORTCUT_ID,
                        dbus.Dictionary({
                            "description": dbus.String("Toggle Raycast Linux Palette", variant_level=1),
                            "preferred_trigger": dbus.String(shortcut, variant_level=1),
                        }, signature="sv"),
                    )
                ]
                bind_opts = dbus.Dictionary({
                    "handle_token": dbus.String(bind_token, variant_level=1),
                }, signature="sv")

                bind_req_path = iface.BindShortcuts(
                    dbus.ObjectPath(session_handle),
                    shortcuts_data,
                    "",
                    bind_opts,
                )
                bind_resp = self._wait_for_request(bus, dbus, bind_req_path, timeout=4.0)
                if bind_resp["status"] != 0:
                    self._close_session(bus, dbus, session_handle)
                    self._cleanup_bus(bus)
                    return {
                        "ok": False,
                        "message": f"BindShortcuts rejected (status {bind_resp['status']}) — {_FALLBACK_MSG}",
                    }

                # 3. Listen for Activated signal on GlobalShortcuts interface
                rx = bus.add_signal_receiver(
                    self._on_activated_signal,
                    signal_name="Activated",
                    dbus_interface=PORTAL_IFACE,
                    bus_name=PORTAL_SERVICE,
                    path=PORTAL_PATH,
                )
                self._signal_receivers.append(rx)

                self._shortcut_id = SHORTCUT_ID
                self._shortcut_string = shortcut
                self._status_str = "registered"
                self._bus = bus
                log.info("XDG GlobalShortcuts portal registered: %s (session %s)", shortcut, session_handle)
                return {
                    "ok": True,
                    "message": f"Global shortcut registered: {shortcut}",
                    "id": self._shortcut_id,
                    "shortcut": self._shortcut_string,
                }
            except Exception as e:  # noqa: BLE001
                log.warning("Portal registration failed: %s", e)
                if self._session_handle and self._bus:
                    self._close_session(self._bus, dbus, self._session_handle)
                self._cleanup_bus(bus if 'bus' in locals() else None)
                self._status_str = "unregistered"
                return {
                    "ok": False,
                    "message": f"Global shortcut not registered via the portal ({e.__class__.__name__}: {e}) — {_FALLBACK_MSG}",
                }

    def unregister(self) -> dict:
        with self._lock:
            if not self._session_handle:
                self._cleanup_bus(self._bus)
                self._status_str = "unregistered"
                return {"ok": True, "message": "Nothing to unregister"}

            dbus, _ = _get_dbus()
            if self._bus and dbus:
                self._close_session(self._bus, dbus, self._session_handle)

            self._cleanup_bus(self._bus)
            self._session_handle = None
            self._shortcut_id = None
            self._shortcut_string = None
            self._status_str = "unregistered"
        return {"ok": True, "message": "Global shortcut unregistered"}

    def status(self) -> dict:
        return {
            "registered": self.registered,
            "id": self._shortcut_id,
            "shortcut": self._shortcut_string,
            "status": self._status_str,
        }

    # -- internals -----------------------------------------------------------
    def _wait_for_request(self, bus, dbus, req_path: str, timeout: float = 4.0) -> dict:
        """Wait synchronously for Request.Response signal on req_path."""
        resp_data = {"status": -1, "results": {}}
        evt = threading.Event()

        def on_response(response, results):
            resp_data["status"] = int(response)
            resp_data["results"] = dict(results)
            evt.set()

        rx = bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=req_path,
        )
        try:
            evt.wait(timeout=timeout)
        finally:
            try:
                if hasattr(rx, "remove"):
                    rx.remove()
                elif bus:
                    bus.remove_signal_receiver(on_response, signal_name="Response", dbus_interface=REQUEST_IFACE, path=req_path)
            except Exception:
                pass
        return resp_data

    def _on_activated_signal(self, session_handle, shortcut_id, timestamp, options) -> None:
        if self._session_handle and str(session_handle) == str(self._session_handle):
            if str(shortcut_id) == str(self._shortcut_id):
                cb = self._on_activate
                if cb:
                    threading.Thread(target=self._fire, args=(cb,), daemon=True).start()

    def _fire(self, cb) -> None:
        try:
            cb()
        except Exception:  # noqa: BLE001
            log.exception("on_activate callback failed")

    def _close_session(self, bus, dbus, session_handle: str) -> None:
        try:
            session_proxy = bus.get_object(PORTAL_SERVICE, session_handle)
            session_iface = dbus.Interface(session_proxy, SESSION_IFACE)
            session_iface.Close()
        except Exception as e:
            log.debug("Error closing session: %s", e)

    def _cleanup_bus(self, bus=None) -> None:
        bus = bus or self._bus
        if bus:
            for rx in self._signal_receivers:
                try:
                    if hasattr(rx, "remove"):
                        rx.remove()
                except Exception:
                    pass
        self._signal_receivers.clear()
        self._bus = None
