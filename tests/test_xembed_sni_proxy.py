import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("dbus")
pytest.importorskip("Xlib")

from Xlib import X

REPO_ROOT = Path(__file__).parents[1]
PACKAGE_DIR = REPO_ROOT / "packages/linux/xembedsniproxy"
sys.path.insert(0, str(PACKAGE_DIR / "src"))

from xembed_sni_proxy import bridge as proxy  # noqa: E402


class FakeIconWindow:
    def __init__(self, xid=42, pid=9001, width=32, height=32,
                 button_event_mask=X.ButtonPressMask, children=None,
                 xembed_info=None, override_redirect=False):
        self.id = xid
        self.pid = pid
        self.width = width
        self.height = height
        self.button_event_mask = button_event_mask
        self.children = list(children or [])
        self.xembed_info = xembed_info
        self.override_redirect = override_redirect
        self.operations = []
        self.sent_events = []
        self.warp_pointer_calls = []

    def change_save_set(self, mode):
        self.operations.append(("save_set", mode))

    def reparent(self, parent, x, y):
        self.operations.append(("reparent", parent, x, y))

    def configure(self, **kwargs):
        self.operations.append(("configure", kwargs))

    def composite_redirect_window(self, update):
        self.operations.append(("composite_redirect", update))

    def composite_unredirect_window(self, update):
        self.operations.append(("composite_unredirect", update))

    def map(self):
        self.operations.append(("map",))

    def clear_area(self, x, y, width, height, exposures=False):
        self.operations.append(("clear_area", x, y, width, height, exposures))

    def unmap(self):
        self.operations.append(("unmap",))

    def change_attributes(self, **kwargs):
        self.operations.append(("attributes", kwargs))

    def send_event(self, event, **kwargs):
        self.operations.append(("send_event",))
        self.sent_events.append((event, kwargs))

    def get_geometry(self):
        return SimpleNamespace(width=self.width, height=self.height)

    def get_attributes(self):
        return SimpleNamespace(
            all_event_masks=self.button_event_mask,
            do_not_propagate_mask=0,
            override_redirect=self.override_redirect,
        )

    def query_tree(self):
        return SimpleNamespace(children=self.children)

    def shape_query_extents(self):
        return SimpleNamespace(bounding_shaped=False)

    def warp_pointer(self, x, y, src_window=X.NONE, src_x=0, src_y=0,
                     src_width=0, src_height=0, onerror=None):
        self.warp_pointer_calls.append((
            x, y, src_window, src_x, src_y, src_width, src_height, onerror,
        ))

    def get_wm_class(self):
        return ("late-host-probe", "late-host-probe")

    def get_full_property(self, atom, _property_type):
        if atom == "_NET_WM_PID":
            return SimpleNamespace(value=[self.pid])
        if atom == "_XEMBED_INFO" and self.xembed_info is not None:
            return SimpleNamespace(value=self.xembed_info)
        return None


class FakeApplicationWindow:
    def __init__(self, title, width, height):
        self.title = title
        self.width = width
        self.height = height
        self.map_count = 0

    def get_attributes(self):
        return SimpleNamespace(map_state=X.IsUnmapped)

    def get_geometry(self):
        return SimpleNamespace(width=self.width, height=self.height)

    def map(self):
        self.map_count += 1


class FakeWineFallbackTray:
    def __init__(self, pid=9001):
        self.id = 84
        self.pid = pid
        self.operations = []

    def get_attributes(self):
        return SimpleNamespace(map_state=X.IsViewable)

    def get_full_property(self, atom, _property_type):
        values = {
            "_NET_WM_PID": [self.pid],
            "_WINE_HWND_STYLE": [proxy.WINE_FALLBACK_TRAY_STYLE_MASK],
        }
        value = values.get(atom)
        return SimpleNamespace(value=value) if value is not None else None

    def get_wm_name(self):
        return ""

    def get_wm_protocols(self):
        return ["WM_DELETE_WINDOW"]

    def send_event(self, event):
        self.operations.append(("send_event", event))


class FakeTrayWindow:
    def __init__(self, xid=0x1234, x=0, y=0, width=32, height=32):
        self.id = xid
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.configure_calls = []
        self.wm_names = []
        self.wm_classes = []
        self.normal_hints = []
        self.protocols = []
        self.properties = []
        self.shape_rectangles_calls = []
        self.clear_count = 0
        self.map_count = 0
        self.destroy_count = 0

    def set_wm_name(self, name):
        self.wm_names.append(name)

    def set_wm_class(self, instance, window_class):
        self.wm_classes.append((instance, window_class))

    def change_property(self, *args):
        self.properties.append(args)

    def configure(self, **kwargs):
        self.configure_calls.append(kwargs)

    def get_geometry(self):
        return SimpleNamespace(
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
        )

    def map(self):
        self.map_count += 1

    def destroy(self):
        self.destroy_count += 1

    def shape_rectangles(self, *args):
        self.shape_rectangles_calls.append(args)

    def set_selection_owner(self, *_args):
        pass

    def set_wm_normal_hints(self, **kwargs):
        self.normal_hints.append(kwargs)

    def set_wm_protocols(self, protocols):
        self.protocols.append(protocols)

    def clear_area(self, *_args):
        self.clear_count += 1


class FakeRoot:
    def __init__(self, tray, children=None, created_windows=None):
        self.tray = tray
        self.children = list(children or [])
        self.created_windows = list(created_windows or [])
        self.create_window_args = None
        self.create_window_kwargs = None
        self.warp_pointer_calls = []

    def create_window(self, *args, **kwargs):
        self.create_window_args = args
        self.create_window_kwargs = kwargs
        if self.created_windows:
            return self.created_windows.pop(0)
        return self.tray

    def query_tree(self):
        return SimpleNamespace(children=self.children)

    def query_pointer(self):
        return SimpleNamespace(root_x=321, root_y=654)

    def send_event(self, *_args, **_kwargs):
        pass

    def warp_pointer(self, *args):
        self.warp_pointer_calls.append(args)


class FakeDisplay:
    def __init__(self, tray=None, events=None, resource=None):
        self.tray = tray
        self.events = list(events or [])
        self.resource = resource
        self.sync_count = 0
        self.xtest_fake_input_calls = []

    def create_resource_object(self, _resource_type, _xid):
        return self.resource

    def intern_atom(self, name):
        return name

    def get_selection_owner(self, _atom):
        return self.tray

    def sync(self):
        self.sync_count += 1

    def flush(self):
        pass

    def pending_events(self):
        return bool(self.events)

    def next_event(self):
        return self.events.pop(0)

    def xtest_fake_input(self, *args, **kwargs):
        self.xtest_fake_input_calls.append((args, kwargs))


class FakeSNI:
    def __init__(self, bind_error=None):
        self.bind_error = bind_error
        self.remove_count = 0

    def bind(self, _xid, _title=""):
        if self.bind_error is not None:
            raise self.bind_error

    def update_icon(self, _icon):
        pass

    def update_title(self, _title):
        pass

    def remove_from_connection(self):
        self.remove_count += 1


class FakeBus:
    def __init__(self):
        self.close_count = 0

    def close(self):
        self.close_count += 1


def make_claim_bridge():
    tray = FakeTrayWindow()
    root = FakeRoot(tray)
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._screen = SimpleNamespace(root_depth=24, black_pixel=0)
    bridge._root = root
    bridge._display = FakeDisplay(tray=tray)
    bridge._atoms = {
        name: name
        for name in (
            "_NET_SYSTEM_TRAY_S0",
            "_NET_SYSTEM_TRAY_ORIENTATION",
            "_XEMBED_INFO",
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
        patch.object(proxy.GLib, "timeout_add"),
        patch.object(
            proxy.protocol.event,
            "ClientMessage",
            side_effect=lambda **kwargs: kwargs,
        ),
    ):
        assert bridge._claim_tray()


def test_restart_redocks_existing_managed_xembed_icons_only():
    tray = FakeTrayWindow()
    icon = FakeIconWindow(xid=99, xembed_info=[0, 1])
    helper = FakeIconWindow(
        xid=100, xembed_info=[0, 1], override_redirect=True,
    )
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._root = FakeRoot(tray, children=[icon, helper])
    bridge._tray_window = tray
    bridge._atoms = {"_XEMBED_INFO": "_XEMBED_INFO"}
    bridge._dock_icon = Mock()

    bridge._redock_existing_icons()

    bridge._dock_icon.assert_called_once_with(icon.id)


def test_proxy_requires_native_input_extensions():
    runtime_display = Mock()
    runtime_display.query_extension.side_effect = lambda name: SimpleNamespace(
        present=name != "XTEST",
    )

    with (
        patch.object(proxy.display, "Display", return_value=runtime_display),
        pytest.raises(RuntimeError, match="XTEST"),
    ):
        proxy.XEmbedSNIProxy()


def test_project_identity_is_xembed_sni_proxy():
    bridge, _root, tray = make_claim_bridge()

    claim_tray(bridge)

    project = tomllib.loads((PACKAGE_DIR / "pyproject.toml").read_text())
    service = (
        PACKAGE_DIR / "files/config/systemd/user/xembedsniproxy.service"
    ).read_text()
    niri_rules = (
        REPO_ROOT / "packages/niri/files/config/niri/cfg/rules.kdl"
    ).read_text()
    assert project["project"]["name"] == "xembed-sni-proxy"
    assert project["project"]["scripts"] == {
        "xembed-sni-proxy": "xembed_sni_proxy.bridge:main"
    }
    assert tray.wm_names == []
    assert tray.wm_classes == []
    assert "ExecStart=%h/.local/bin/xembed-sni-proxy" in service
    assert 'match app-id=r#"^xembed-sni-proxy$"#' in niri_rules


def test_tray_has_explicit_black_background_for_automatic_repaint():
    bridge, root, _tray = make_claim_bridge()

    claim_tray(bridge)

    assert root.create_window_kwargs["background_pixel"] == bridge._screen.black_pixel


def test_tray_does_not_publish_size_hints():
    bridge, _root, tray = make_claim_bridge()

    claim_tray(bridge)

    assert tray.normal_hints == []


def test_selection_owner_stays_unmapped_and_bypasses_window_management():
    bridge, root, tray = make_claim_bridge()

    claim_tray(bridge)

    assert root.create_window_kwargs["override_redirect"] is True
    assert tray.map_count == 0
    assert tray.protocols == []


def test_each_sni_slot_gets_a_unique_object_path():
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._slot_counter = 0
    bridge._slots = []
    created_paths = []

    def make_sni(_bus_name, path, _bridge):
        created_paths.append(path)
        return FakeSNI()

    with (
        patch.object(
            proxy.dbus.bus,
            "BusConnection",
            side_effect=lambda _address: FakeBus(),
        ),
        patch.object(
            proxy.dbus.service,
            "BusName",
            side_effect=lambda *_args, **_kwargs: object(),
        ),
        patch.object(proxy, "SNIItem", side_effect=make_sni),
    ):
        first = bridge._get_or_create_slot()
        second = bridge._get_or_create_slot()

    assert created_paths == ["/StatusNotifierItem/1", "/StatusNotifierItem/2"]
    assert bridge._slots[first]["registration_id"].endswith("/StatusNotifierItem/1")
    assert bridge._slots[second]["registration_id"].endswith("/StatusNotifierItem/2")


def test_icon_host_uses_a_transparent_argb_visual_when_available():
    icon_host = FakeTrayWindow(xid=0x5678)
    visual = SimpleNamespace(
        visual_id=99,
        visual_class=X.TrueColor,
        red_mask=0x00FF0000,
        green_mask=0x0000FF00,
        blue_mask=0x000000FF,
    )
    argb_depth = SimpleNamespace(depth=32, visuals=[visual])
    root = FakeRoot(FakeTrayWindow(), created_windows=[icon_host])
    root.create_colormap = Mock(return_value="argb-colormap")
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._root = root
    bridge._screen = SimpleNamespace(
        root_depth=24,
        black_pixel=0,
        allowed_depths=[argb_depth],
    )
    bridge._display = FakeDisplay()
    bridge._atoms = {"_NET_WM_WINDOW_OPACITY": "_NET_WM_WINDOW_OPACITY"}

    bridge._create_icon_host()

    assert root.create_window_args[5:8] == (
        32, X.InputOutput, visual.visual_id,
    )
    assert root.create_window_kwargs["colormap"] == "argb-colormap"
    assert root.create_window_kwargs["background_pixel"] == 0


def test_failed_icon_host_creation_destroys_the_partial_window():
    icon_host = FakeTrayWindow(xid=0x5678)
    icon_host.set_wm_class = Mock(side_effect=RuntimeError("WM_CLASS failed"))
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._root = FakeRoot(FakeTrayWindow(), created_windows=[icon_host])
    bridge._screen = SimpleNamespace(root_depth=24, black_pixel=0)
    bridge._display = FakeDisplay()
    bridge._atoms = {
        "_NET_WM_WINDOW_OPACITY": "_NET_WM_WINDOW_OPACITY",
    }

    with pytest.raises(RuntimeError, match="WM_CLASS failed"):
        bridge._create_icon_host()

    assert icon_host.destroy_count == 1


def test_failed_sni_slot_creation_closes_the_partial_connection():
    slot_bus = FakeBus()
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._slot_counter = 0
    bridge._slots = []

    with (
        patch.object(
            proxy.dbus.bus,
            "BusConnection",
            return_value=slot_bus,
        ),
        patch.object(
            proxy.dbus.service,
            "BusName",
            side_effect=RuntimeError("name failed"),
        ),
        pytest.raises(RuntimeError, match="name failed"),
    ):
        bridge._get_or_create_slot()

    assert slot_bus.close_count == 1
    assert bridge._slots == []


def test_niri_uses_xtest_for_native_compositor_routed_input():
    icon = FakeIconWindow(button_event_mask=X.ButtonPressMask)
    bridge = object.__new__(proxy.XEmbedSNIProxy)

    with patch.dict(
        proxy.os.environ,
        {"XDG_SESSION_TYPE": "wayland", "NIRI_SOCKET": "test.sock"},
    ):
        assert bridge._select_inject_mode(icon) == proxy.INJECT_XTEST


def test_descendant_only_button_subscription_uses_xtest():
    child = FakeIconWindow(button_event_mask=X.ButtonPressMask)
    icon = FakeIconWindow(button_event_mask=0, children=[child])
    bridge = object.__new__(proxy.XEmbedSNIProxy)

    with patch.dict(
        proxy.os.environ,
        {"XDG_SESSION_TYPE": "x11", "NIRI_SOCKET": ""},
    ):
        assert bridge._select_inject_mode(icon) == proxy.INJECT_XTEST


def test_docking_protects_icon_registers_path_and_closes_wine_fallback_tray():
    icon = FakeIconWindow()
    wine_fallback_tray = FakeWineFallbackTray(pid=icon.pid)
    unrelated_wine_tray = FakeWineFallbackTray(pid=icon.pid + 1)
    unrelated_wine_tray.id += 1
    tray = FakeTrayWindow()
    icon_host = FakeTrayWindow(xid=0x5678)
    registrations = []
    watcher = SimpleNamespace(RegisterStatusNotifierItem=registrations.append)
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._dead = False
    bridge._active_icons = {}
    bridge._display = FakeDisplay(resource=icon)
    bridge._root = FakeRoot(
        tray,
        children=[wine_fallback_tray, unrelated_wine_tray],
        created_windows=[icon_host],
    )
    bridge._tray_window = tray
    bridge._slots = [{
        "sni": FakeSNI(),
        "bus_name": "org.example.Test",
        "object_path": "/StatusNotifierItem/1",
        "registration_id": "org.example.Test/StatusNotifierItem/1",
        "dbus_name": object(),
        "slot_bus": FakeBus(),
        "xid": None,
        "window": None,
        "icon_ready": False,
    }]
    bridge._get_or_create_slot = lambda: 0
    bridge._icon_cache = {}
    bridge._bus = SimpleNamespace(get_object=lambda *_args: watcher)
    bridge._screen = SimpleNamespace(root_depth=24, black_pixel=0)
    bridge._atoms = {
        "_XEMBED": "_XEMBED",
        "_NET_WM_WINDOW_OPACITY": "_NET_WM_WINDOW_OPACITY",
        "_NET_WM_PID": "_NET_WM_PID",
        "_WINE_HWND_STYLE": "_WINE_HWND_STYLE",
        "WM_PROTOCOLS": "WM_PROTOCOLS",
        "WM_DELETE_WINDOW": "WM_DELETE_WINDOW",
    }

    with (
        patch.dict(proxy.os.environ, {"NIRI_SOCKET": ""}),
        patch.object(proxy.GLib, "timeout_add") as timeout_add,
        patch.object(proxy.dbus, "Interface", return_value=watcher),
        patch.object(
            proxy.protocol.event,
            "ClientMessage",
            side_effect=lambda **kwargs: kwargs,
        ),
    ):
        bridge._dock_icon(icon.id)

    assert bridge._root.create_window_kwargs["override_redirect"] is True
    assert icon_host.wm_classes == [
        (proxy.APPLICATION_ID, proxy.APPLICATION_ID),
    ]
    assert icon_host.shape_rectangles_calls[0][-1] == []
    assert icon_host.map_count == 1
    assert ("save_set", X.SetModeInsert) in icon.operations
    assert ("clear_area", 0, 0, proxy.TRAY_ICON_SIZE,
            proxy.TRAY_ICON_SIZE, False) in icon.operations
    assert ("reparent", icon_host, 0, 0) in icon.operations
    assert (
        "composite_redirect", proxy.composite.RedirectManual,
    ) in icon.operations
    assert bridge._slots[0]["inject_mode"] == proxy.INJECT_DIRECT
    assert registrations == ["org.example.Test/StatusNotifierItem/1"]
    timeout_add.assert_any_call(
        proxy.WINE_FALLBACK_CLOSE_DELAY_MS,
        bridge._close_wine_fallback_trays,
        icon,
    )
    assert wine_fallback_tray.operations == [(
        "send_event",
        {
            "window": wine_fallback_tray,
            "client_type": "WM_PROTOCOLS",
            "data": (32, ["WM_DELETE_WINDOW", X.CurrentTime, 0, 0, 0]),
        },
    )]
    assert unrelated_wine_tray.operations == []


def test_failed_dock_releases_the_icon_host_and_sni_slot():
    icon = FakeIconWindow()
    icon_host = FakeTrayWindow(xid=0x5678)
    sni = FakeSNI(bind_error=RuntimeError("bind failed"))
    slot_bus = FakeBus()
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._dead = False
    bridge._active_icons = {}
    bridge._display = FakeDisplay(resource=icon)
    bridge._root = FakeRoot(FakeTrayWindow(), created_windows=[icon_host])
    bridge._screen = SimpleNamespace(root_depth=24, black_pixel=0)
    bridge._atoms = {
        "_XEMBED": "_XEMBED",
        "_NET_WM_WINDOW_OPACITY": "_NET_WM_WINDOW_OPACITY",
    }
    bridge._slots = [{
        "sni": sni,
        "dbus_name": object(),
        "slot_bus": slot_bus,
        "xid": None,
        "window": None,
        "icon_ready": False,
    }]
    bridge._get_or_create_slot = lambda: 0
    bridge._get_icon_key = lambda _icon: "test"
    bridge._get_window_title = lambda _window: ""

    with patch.object(
        proxy.protocol.event,
        "ClientMessage",
        side_effect=lambda **kwargs: kwargs,
    ):
        bridge._dock_icon(icon.id)

    assert bridge._active_icons == {}
    assert bridge._slots == [None]
    assert icon_host.destroy_count == 1
    assert sni.remove_count == 1
    assert slot_bus.close_count == 1


def test_host_services_embedded_icon_map_and_resize_requests():
    icon = FakeIconWindow()
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._dead = False
    bridge._active_icons = {icon.id: 0}
    bridge._slots = [{"window": icon}]
    bridge._display = FakeDisplay(events=[
        SimpleNamespace(type=X.MapRequest, window=icon),
        SimpleNamespace(
            type=X.ConfigureRequest,
            window=icon,
            value_mask=X.CWX | X.CWY | X.CWWidth | X.CWHeight,
            x=100,
            y=200,
            width=64,
            height=16,
        ),
    ])

    assert bridge._process_x11() is True

    assert ("map",) in icon.operations
    assert ("configure", {"width": 32, "height": 16}) in icon.operations


def test_every_activation_forwards_one_click_without_managing_application_windows():
    application_window = FakeApplicationWindow("Battle.net", 1713, 1390)
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._dead = False
    bridge._active_icons = {42: 0}
    bridge._slots = [{"title": "Battle.net"}]
    bridge._root = FakeRoot(FakeTrayWindow(), children=[application_window])
    bridge._display = FakeDisplay()
    bridge._get_window_title = lambda window: window.title
    bridge.send_click = Mock()
    item = object.__new__(proxy.SNIItem)
    item._bridge = bridge
    item._icon_xid = 42
    item._active = True

    item.Activate(100, 200)
    item.Activate(100, 200)

    assert bridge.send_click.call_args_list == [
        ((42, 1, 100, 200),),
        ((42, 1, 100, 200),),
    ]
    assert application_window.map_count == 0


def test_direct_activation_releases_the_pointer_without_moving_the_host():
    icon = FakeIconWindow()
    icon_host = FakeTrayWindow(xid=0x5678)
    root = FakeRoot(FakeTrayWindow())
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._dead = False
    bridge._active_icons = {icon.id: 0}
    bridge._slots = [{
        "window": icon,
        "host": icon_host,
        "inject_mode": proxy.INJECT_DIRECT,
    }]
    bridge._root = root
    bridge._display = FakeDisplay()
    item = object.__new__(proxy.SNIItem)
    item._bridge = bridge
    item._icon_xid = icon.id
    item._active = True
    scheduled = []

    def schedule(delay, callback, *args):
        scheduled.append((delay, callback, args))
        return 73

    with (
        patch.dict(
            proxy.os.environ,
            {"XDG_SESSION_TYPE": "wayland", "NIRI_SOCKET": ""},
        ),
        patch.object(proxy.GLib, "timeout_add", side_effect=schedule),
        patch.object(
            proxy.protocol.event,
            "ButtonPress",
            side_effect=lambda **kwargs: ("press", kwargs),
        ),
        patch.object(
            proxy.protocol.event,
            "ButtonRelease",
            side_effect=lambda **kwargs: ("release", kwargs),
        ),
    ):
        item.Activate(100, 200)

    assert {"x": 84, "y": 184} in icon_host.configure_calls
    assert icon_host.shape_rectangles_calls == [
        (proxy.shape.SO.Set, proxy.shape.SK.Input, X.YXBanded, 0, 0,
         [(0, 0, proxy.TRAY_ICON_SIZE, proxy.TRAY_ICON_SIZE)]),
        (proxy.shape.SO.Set, proxy.shape.SK.Input, X.YXBanded, 0, 0, []),
    ]
    assert icon.warp_pointer_calls == [
        (16, 16, X.NONE, 0, 0, 0, 0, None),
    ]
    assert root.warp_pointer_calls == []
    assert [event[0] for event, _kwargs in icon.sent_events] == [
        "press", "release",
    ]
    press_event, press_delivery = icon.sent_events[0]
    release_event, release_delivery = icon.sent_events[1]
    assert press_event[1]["state"] == 0
    assert release_event[1]["state"] == 0
    assert press_delivery == {
        "propagate": False,
        "event_mask": X.ButtonPressMask,
    }
    assert release_delivery == {
        "propagate": False,
        "event_mask": X.ButtonReleaseMask,
    }
    assert len(scheduled) == 1
    delay, callback, args = scheduled[0]
    assert delay == proxy.DIRECT_POINTER_RELEASE_DELAY_MS
    assert callback(*args) is False
    assert root.warp_pointer_calls == [(100, 200)]


def test_niri_activation_uses_the_compositor_host_position():
    icon = FakeIconWindow()
    icon_host = FakeTrayWindow(xid=0x5678, x=400, y=10)
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._dead = False
    bridge._active_icons = {icon.id: 0}
    bridge._slots = [{
        "window": icon,
        "host": icon_host,
        "inject_mode": proxy.INJECT_DIRECT,
    }]
    bridge._root = FakeRoot(FakeTrayWindow())
    bridge._display = FakeDisplay()
    item = object.__new__(proxy.SNIItem)
    item._bridge = bridge
    item._icon_xid = icon.id
    item._active = True
    scheduled = []

    def schedule(delay, callback, *args):
        scheduled.append((delay, callback, args))
        return 73

    with (
        patch.dict(
            proxy.os.environ,
            {"XDG_SESSION_TYPE": "wayland", "NIRI_SOCKET": "test.sock"},
        ),
        patch.object(proxy.GLib, "timeout_add", side_effect=schedule),
        patch.object(
            proxy.protocol.event,
            "ButtonPress",
            side_effect=lambda **kwargs: ("press", kwargs),
        ),
        patch.object(
            proxy.protocol.event,
            "ButtonRelease",
            side_effect=lambda **kwargs: ("release", kwargs),
        ),
    ):
        item.Activate(100, 200)

    assert not any("x" in call or "y" in call for call in icon_host.configure_calls)
    assert [event[1]["root_x"] for event, _kwargs in icon.sent_events] == [416, 416]
    assert [event[1]["root_y"] for event, _kwargs in icon.sent_events] == [26, 26]
    assert bridge._root.warp_pointer_calls == []

    _delay, callback, args = scheduled[0]
    assert callback(*args) is False
    assert bridge._root.warp_pointer_calls == [(416, 26)]


def test_activation_uses_xtest_and_delays_wayland_host_deactivation_when_needed():
    icon = FakeIconWindow()
    icon_host = FakeTrayWindow(xid=0x5678)
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._dead = False
    bridge._active_icons = {icon.id: 0}
    bridge._slots = [{
        "window": icon,
        "host": icon_host,
        "inject_mode": proxy.INJECT_XTEST,
    }]
    bridge._root = FakeRoot(FakeTrayWindow())
    bridge._display = FakeDisplay()
    item = object.__new__(proxy.SNIItem)
    item._bridge = bridge
    item._icon_xid = icon.id
    item._active = True
    scheduled = []

    def schedule(delay, callback, *args):
        scheduled.append((delay, callback, args))
        return 73

    with (
        patch.dict(
            proxy.os.environ,
            {"XDG_SESSION_TYPE": "wayland", "NIRI_SOCKET": "test.sock"},
        ),
        patch.object(proxy.GLib, "timeout_add", side_effect=schedule),
    ):
        item.Activate(100, 200)

    assert icon.sent_events == []
    assert bridge._display.sync_count == 1
    assert bridge._display.xtest_fake_input_calls == [
        ((X.ButtonPress, 1), {}),
        ((X.ButtonRelease, 1), {}),
    ]
    assert icon_host.shape_rectangles_calls == [
        (proxy.shape.SO.Set, proxy.shape.SK.Input, X.YXBanded, 0, 0,
         [(0, 0, proxy.TRAY_ICON_SIZE, proxy.TRAY_ICON_SIZE)]),
    ]
    assert scheduled[0][0] == proxy.XTEST_DEACTIVATION_DELAY_MS

    _delay, callback, args = scheduled[0]
    assert callback(*args) is False
    assert icon_host.shape_rectangles_calls[-1][-1] == []
    assert not any("x" in call or "y" in call for call in icon_host.configure_calls)
    assert bridge._root.warp_pointer_calls == [(16, 16)]


def test_scroll_forwards_one_native_wheel_click_at_the_pointer():
    bridge = object.__new__(proxy.XEmbedSNIProxy)
    bridge._root = FakeRoot(FakeTrayWindow())
    bridge.send_click = Mock()

    bridge.send_scroll(42, 120, "vertical")
    bridge.send_scroll(42, -120, "VERTICAL")
    bridge.send_scroll(42, 120, "horizontal")
    bridge.send_scroll(42, -120, "horizontal")

    assert bridge.send_click.call_args_list == [
        ((42, 4, 321, 654),),
        ((42, 5, 321, 654),),
        ((42, 6, 321, 654),),
        ((42, 7, 321, 654),),
    ]


def test_sni_scroll_reaches_the_embedded_icon():
    bridge = Mock()
    item = object.__new__(proxy.SNIItem)
    item._bridge = bridge
    item._icon_xid = 42
    item._active = True

    item.Scroll(120, "vertical")

    bridge.send_scroll.assert_called_once_with(42, 120, "vertical")


def test_sni_item_does_not_publish_a_fake_application_title():
    item = object.__new__(proxy.SNIItem)
    item._icon_xid = 0
    item._icon_data = []
    item._title = "stale title"
    item._active = False
    item.NewStatus = Mock()

    item.bind(42)

    assert item._props()["Title"] == ""
    assert item._props()["ToolTip"][2] == ""


def test_sni_item_publishes_a_learned_title_as_its_tooltip():
    item = object.__new__(proxy.SNIItem)
    item._icon_xid = 42
    item._icon_data = []
    item._title = ""
    item._active = True
    item.NewTitle = Mock()
    item.NewToolTip = Mock()

    item.update_title("Battle.net")

    assert item._props()["Title"] == "Battle.net"
    assert item._props()["ToolTip"][2:] == ("Battle.net", "")
    item.NewTitle.assert_called_once_with()
    item.NewToolTip.assert_called_once_with()


def test_visual_identity_selects_the_unique_matching_application_title():
    black = (0, 0, 0)
    blue = (0, 0, 255)
    blue_cross = [
        black, blue, black,
        blue, blue, blue,
        black, blue, black,
    ]
    red_square = [(255, 0, 0)] * 9
    padded_blue_cross = [
        black, black, black, black, black,
        black, black, blue, black, black,
        black, blue, blue, blue, black,
        black, black, blue, black, black,
        black, black, black, black, black,
    ]

    title = proxy._select_matching_icon_title(
        padded_blue_cross,
        5,
        5,
        [
            ("Battle.net", blue_cross, 3, 3),
            ("Hearthstone Deck Tracker", red_square, 3, 3),
        ],
    )

    assert title == "Battle.net"


def test_visual_identity_rejects_ambiguous_matches():
    icon = [(20, 100, 200)] * 9

    title = proxy._select_matching_icon_title(
        icon,
        3,
        3,
        [("first", icon, 3, 3), ("second", icon, 3, 3)],
    )

    assert title == ""


def test_undock_releases_a_surviving_icon_before_removing_it():
    icon = FakeIconWindow()
    icon_host = FakeTrayWindow(xid=0x5678)
    tray = FakeTrayWindow()
    root = object()
    bridge = object.__new__(proxy.XEmbedSNIProxy)
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
        "host": icon_host,
    }]

    bridge._undock_icon(icon.id)

    assert icon.operations[:4] == [
        ("composite_unredirect", proxy.composite.RedirectManual),
        ("unmap",),
        ("reparent", root, 0, 0),
        ("save_set", X.SetModeDelete),
    ]
    assert icon_host.destroy_count == 1
    assert tray.configure_calls == []
    assert tray.clear_count == 0
