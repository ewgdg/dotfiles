from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("dbus")
pytest.importorskip("Xlib")

from Xlib import X

PACKAGE_DIR = Path(__file__).parents[1] / "packages/linux/xembedsniproxy"
sys.path.insert(0, str(PACKAGE_DIR))

import wine_sni_bridge


class FakeIconWindow:
    def __init__(self, xid=42):
        self.id = xid
        self.operations = []

    def change_save_set(self, mode):
        self.operations.append(("save_set", mode))

    def reparent(self, parent, x, y):
        self.operations.append(("reparent", parent, x, y))

    def configure(self, **kwargs):
        self.operations.append(("configure", kwargs))

    def map(self):
        self.operations.append(("map",))

    def unmap(self):
        self.operations.append(("unmap",))

    def change_attributes(self, **kwargs):
        self.operations.append(("attributes", kwargs))

    def send_event(self, _event):
        self.operations.append(("send_event",))

    def get_wm_class(self):
        return ("late-host-probe", "late-host-probe")


class FakeTrayWindow:
    def __init__(self):
        self.id = 0x1234
        self.configure_calls = []
        self.normal_hints = []
        self.protocols = []
        self.clear_count = 0

    def set_wm_name(self, _name):
        pass

    def set_wm_class(self, _instance, _class):
        pass

    def change_property(self, *_args):
        pass

    def configure(self, **kwargs):
        self.configure_calls.append(kwargs)

    def map(self):
        pass

    def set_selection_owner(self, *_args):
        pass

    def set_wm_normal_hints(self, **kwargs):
        self.normal_hints.append(kwargs)

    def set_wm_protocols(self, protocols):
        self.protocols.append(protocols)

    def clear_area(self, *_args):
        self.clear_count += 1


class FakeRoot:
    def __init__(self, tray):
        self.tray = tray
        self.create_window_kwargs = None

    def create_window(self, *_args, **kwargs):
        self.create_window_kwargs = kwargs
        return self.tray

    def send_event(self, *_args, **_kwargs):
        pass


class FakeDisplay:
    def __init__(self, tray=None, events=None, resource=None):
        self.tray = tray
        self.events = list(events or [])
        self.resource = resource

    def create_resource_object(self, _resource_type, _xid):
        return self.resource

    def intern_atom(self, name):
        return name

    def get_selection_owner(self, _atom):
        return self.tray

    def sync(self):
        pass

    def flush(self):
        pass

    def pending_events(self):
        return bool(self.events)

    def next_event(self):
        return self.events.pop(0)


class FakeSNI:
    def bind(self, _xid):
        pass

    def update_icon(self, _icon):
        pass

    def remove_from_connection(self):
        pass


class FakeBus:
    def close(self):
        pass


def make_claim_bridge():
    tray = FakeTrayWindow()
    root = FakeRoot(tray)
    bridge = object.__new__(wine_sni_bridge.WineSNIBridge)
    bridge._screen = SimpleNamespace(root_depth=24, black_pixel=0)
    bridge._root = root
    bridge._display = FakeDisplay(tray=tray)
    bridge._atoms = {
        name: name
        for name in (
            "_NET_SYSTEM_TRAY_S0",
            "_NET_SYSTEM_TRAY_ORIENTATION",
            "_NET_WM_WINDOW_TYPE",
            "_NET_WM_WINDOW_TYPE_UTILITY",
            "_NET_WM_STATE",
            "_NET_WM_STATE_SKIP_TASKBAR",
            "_NET_WM_STATE_SKIP_PAGER",
            "MANAGER",
            "WM_DELETE_WINDOW",
        )
    }
    return bridge, root, tray


def claim_tray(bridge):
    with (
        patch.object(wine_sni_bridge.GLib, "timeout_add"),
        patch.object(
            wine_sni_bridge.protocol.event,
            "ClientMessage",
            side_effect=lambda **kwargs: kwargs,
        ),
    ):
        assert bridge._claim_tray()


def test_tray_has_explicit_black_background_for_automatic_repaint():
    bridge, root, _tray = make_claim_bridge()

    claim_tray(bridge)

    assert root.create_window_kwargs["background_pixel"] == bridge._screen.black_pixel


def test_tray_does_not_publish_size_hints():
    bridge, _root, tray = make_claim_bridge()

    claim_tray(bridge)

    assert tray.normal_hints == []


def test_tray_advertises_graceful_window_close():
    bridge, _root, tray = make_claim_bridge()

    claim_tray(bridge)

    assert tray.protocols == [[bridge._atoms["WM_DELETE_WINDOW"]]]


def test_docked_icon_is_protected_by_the_x11_save_set():
    icon = FakeIconWindow()
    tray = FakeTrayWindow()
    watcher = SimpleNamespace(RegisterStatusNotifierItem=lambda _name: None)
    bridge = object.__new__(wine_sni_bridge.WineSNIBridge)
    bridge._dead = False
    bridge._active_icons = {}
    bridge._display = FakeDisplay(resource=icon)
    bridge._tray_window = tray
    bridge._slots = [{
        "sni": FakeSNI(),
        "bus_name": "org.example.Test",
        "dbus_name": object(),
        "slot_bus": FakeBus(),
        "xid": None,
        "window": None,
        "icon_ready": False,
    }]
    bridge._get_or_create_slot = lambda: 0
    bridge._icon_cache = {}
    bridge._bus = SimpleNamespace(get_object=lambda *_args: watcher)
    bridge._atoms = {"_XEMBED": "_XEMBED"}

    with (
        patch.object(wine_sni_bridge.GLib, "timeout_add"),
        patch.object(wine_sni_bridge.dbus, "Interface", return_value=watcher),
        patch.object(
            wine_sni_bridge.protocol.event,
            "ClientMessage",
            side_effect=lambda **kwargs: kwargs,
        ),
    ):
        bridge._dock_icon(icon.id)

    assert ("save_set", X.SetModeInsert) in icon.operations


def test_window_close_requests_a_controlled_service_restart():
    tray = FakeTrayWindow()
    event = SimpleNamespace(
        type=X.ClientMessage,
        window=tray,
        client_type="WM_PROTOCOLS",
        data=(32, ["WM_DELETE_WINDOW", 0, 0, 0, 0]),
    )
    bridge = object.__new__(wine_sni_bridge.WineSNIBridge)
    bridge._dead = False
    bridge._tray_window = tray
    bridge._display = FakeDisplay(events=[event])
    bridge._atoms = {
        "WM_PROTOCOLS": "WM_PROTOCOLS",
        "WM_DELETE_WINDOW": "WM_DELETE_WINDOW",
        "_NET_SYSTEM_TRAY_OPCODE": "_NET_SYSTEM_TRAY_OPCODE",
    }
    bridge._loop = SimpleNamespace(quit=lambda: setattr(bridge, "quit_called", True))
    bridge.quit_called = False
    bridge._restart_requested = False

    bridge._process_x11()

    assert bridge.quit_called
    assert bridge._restart_requested
    assert not bridge._dead


def test_undock_releases_a_surviving_icon_before_removing_it():
    icon = FakeIconWindow()
    tray = FakeTrayWindow()
    root = object()
    bridge = object.__new__(wine_sni_bridge.WineSNIBridge)
    bridge._dead = False
    bridge._tray_window = tray
    bridge._root = root
    bridge._display = FakeDisplay()
    bridge._active_icons = {42: 0}
    bridge._slots = [{
        "sni": FakeSNI(),
        "dbus_name": object(),
        "slot_bus": FakeBus(),
        "window": icon,
    }]

    bridge._undock_icon(icon.id)

    assert icon.operations[:3] == [
        ("unmap",),
        ("reparent", root, 0, 0),
        ("save_set", X.SetModeDelete),
    ]
    assert tray.configure_calls[-1] == {"width": 1, "height": 1}
    assert tray.clear_count == 0
