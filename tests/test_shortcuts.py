"""Tests for XDG GlobalShortcuts portal contract and shortcuts service."""
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from raycast_linux.backend.shortcuts import (
    GlobalShortcutPortal,
    PORTAL_IFACE,
    PORTAL_SERVICE,
    PORTAL_PATH,
    REQUEST_IFACE,
    SESSION_IFACE,
)


def test_shortcuts_initial_status():
    """Verify status() returns a valid dictionary and is callable."""
    portal = GlobalShortcutPortal()
    st = portal.status()
    assert isinstance(st, dict)
    assert st["registered"] is False
    assert st["id"] is None
    assert st["shortcut"] is None
    assert st["status"] == "unregistered"


def test_shortcuts_register_without_callback():
    """Registering without callback must fail safely."""
    portal = GlobalShortcutPortal()
    res = portal.register("super+space")
    assert res["ok"] is False
    assert "No activation handler" in res["message"]


def test_shortcuts_portal_contract_mocked():
    """Verify the portal contract uses CreateSession, BindShortcuts, Activated, and Close."""
    portal = GlobalShortcutPortal()
    activated_event = threading.Event()
    portal.set_on_activate(lambda: activated_event.set())

    mock_bus = MagicMock()
    mock_portal_proxy = MagicMock()
    mock_portal_iface = MagicMock()
    mock_session_proxy = MagicMock()
    mock_session_iface = MagicMock()

    mock_bus.get_object.side_effect = lambda srv, path: (
        mock_portal_proxy if path == PORTAL_PATH else mock_session_proxy
    )

    session_token = "sess_123"
    session_handle = f"/org/freedesktop/portal/desktop/session/user/{session_token}"
    create_req_handle = "/org/freedesktop/portal/desktop/request/user/req_create"
    bind_req_handle = "/org/freedesktop/portal/desktop/request/user/req_bind"

    mock_portal_iface.CreateSession.return_value = create_req_handle
    mock_portal_iface.BindShortcuts.return_value = bind_req_handle

    registered_callbacks = {}

    def mock_add_signal_receiver(handler, signal_name, dbus_interface=None, path=None, **kwargs):
        registered_callbacks[(signal_name, path)] = handler
        return MagicMock()

    mock_bus.add_signal_receiver.side_effect = mock_add_signal_receiver

    with patch("raycast_linux.backend.shortcuts._get_dbus") as mock_get_dbus:
        mock_dbus_mod = MagicMock()
        mock_dbus_mod.SessionBus.return_value = mock_bus
        mock_dbus_mod.Interface.side_effect = lambda proxy, iface: (
            mock_session_iface if iface == SESSION_IFACE else mock_portal_iface
        )
        mock_dbus_mod.ObjectPath = lambda p: p
        mock_dbus_mod.String = lambda s, **kw: s
        mock_dbus_mod.Dictionary = lambda d, **kw: d
        mock_get_dbus.return_value = (mock_dbus_mod, None)

        # Trigger responses when Request signals are hooked
        def simulate_responses():
            time.sleep(0.05)
            # 1. Trigger CreateSession Response
            create_cb = registered_callbacks.get(("Response", create_req_handle))
            if create_cb:
                create_cb(0, {"session_handle": session_handle})
            time.sleep(0.05)
            # 2. Trigger BindShortcuts Response
            bind_cb = registered_callbacks.get(("Response", bind_req_handle))
            if bind_cb:
                bind_cb(0, {"shortcuts": [("toggle_palette", {"trigger_description": "Super+Space"})]})

        t = threading.Thread(target=simulate_responses, daemon=True)
        t.start()

        res = portal.register("super+space")
        assert res["ok"] is True
        assert portal.registered is True
        assert portal.shortcut_id == "toggle_palette"

        # Verify CreateSession and BindShortcuts were called with valid args
        mock_portal_iface.CreateSession.assert_called_once()
        mock_portal_iface.BindShortcuts.assert_called_once()

        # 3. Simulate Activated signal
        activated_cb = registered_callbacks.get(("Activated", PORTAL_PATH))
        assert activated_cb is not None
        activated_cb(session_handle, "toggle_palette", 12345678, {})
        assert activated_event.wait(timeout=1.0) is True

        # 4. Unregister: verify Session.Close() is called
        unreg_res = portal.unregister()
        assert unreg_res["ok"] is True
        assert portal.registered is False
        mock_session_iface.Close.assert_called_once()


def test_shortcuts_portal_error_fallback():
    """Verify portal failure falls back cleanly without reporting false success."""
    portal = GlobalShortcutPortal()
    portal.set_on_activate(lambda: None)

    with patch("raycast_linux.backend.shortcuts._get_dbus") as mock_get_dbus:
        mock_bus = MagicMock()
        mock_portal_iface = MagicMock()
        mock_portal_iface.CreateSession.side_effect = Exception("Portal service not running")

        mock_dbus_mod = MagicMock()
        mock_dbus_mod.SessionBus.return_value = mock_bus
        mock_dbus_mod.Interface.return_value = mock_portal_iface
        mock_dbus_mod.Dictionary = lambda d, **kw: d
        mock_dbus_mod.String = lambda s, **kw: s
        mock_get_dbus.return_value = (mock_dbus_mod, None)

        res = portal.register("super+space")
        assert res["ok"] is False
        assert portal.registered is False
        assert "Global shortcut not registered via the portal" in res["message"]
