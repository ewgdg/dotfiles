#!/usr/bin/env python3
"""
XEmbed SNI Proxy - X11 System Tray to StatusNotifierItem bridge for Wayland.
Replaces xembedsniproxy without creating focus-stealing unmanaged X11 windows.

Byte order note
---------------
The DBus StatusNotifierItem spec describes IconPixmap as "ARGB32 in network
byte order" (big-endian A,R,G,B bytes). Every real host reads exactly that:
waybar and noctalia decode byte 0 as alpha, Quickshell bswaps per pixel, and
KDE's own SNI library swaps to network order before sending. So 'network'
(default) is correct everywhere; 'native' (little-endian B,G,R,A) is only for
hypothetical hosts that build a QImage straight from the raw payload.
"""

import argparse
import math
import os
import sys
import struct
import signal
import time

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
from Xlib import X, display, Xatom, protocol, error
from Xlib.error import ConnectionClosedError

APPLICATION_ID = "xembed-sni-proxy"
SNI_WATCHER_BUS = "org.kde.StatusNotifierWatcher"
SNI_WATCHER_PATH = "/StatusNotifierWatcher"
SNI_ITEM_IFACE = "org.kde.StatusNotifierItem"

SYSTEM_TRAY_REQUEST_DOCK = 0
XEMBED_EMBEDDED_NOTIFY = 0
XEMBED_VERSION = 0

TRAY_ICON_SIZE = 32
EMPTY_TRAY_SIZE = 1
ICON_MATCH_SIZE = 24
# Only publish an inferred app title when one top-level window icon is both a
# strong match and clearly better than every differently titled candidate.
ICON_MATCH_MIN_SIMILARITY = 0.85
ICON_MATCH_MIN_MARGIN = 0.05
ICON_VISIBLE_THRESHOLD = 30
# Wine's standalone Shell_TrayWnd is created with WS_CAPTION | WS_SYSMENU.
# Matching these bits, the Wine PID, and WM_DELETE_WINDOW lets us close only
# the fallback tray without relying on its DPI-dependent pixel dimensions.
WINE_FALLBACK_TRAY_STYLE_MASK = 0x00C80000
WINE_FALLBACK_CLOSE_DELAY_MS = 500


def _iter_net_wm_icons(data):
    offset = 0
    while offset + 2 < len(data):
        width, height = int(data[offset]), int(data[offset + 1])
        offset += 2
        pixel_count = width * height
        if width <= 0 or height <= 0 or offset + pixel_count > len(data):
            break
        yield width, height, data[offset:offset + pixel_count]
        offset += pixel_count


def _normalize_icon_pixels(pixels, width, height):
    if width <= 0 or height <= 0 or len(pixels) != width * height:
        return None

    visible = [
        (index % width, index // width)
        for index, pixel in enumerate(pixels)
        if sum(pixel) > ICON_VISIBLE_THRESHOLD
    ]
    if not visible:
        return None

    min_x = min(x for x, _y in visible)
    max_x = max(x for x, _y in visible)
    min_y = min(y for _x, y in visible)
    max_y = max(y for _x, y in visible)
    crop_width = max_x - min_x + 1
    crop_height = max_y - min_y + 1
    scale = min(ICON_MATCH_SIZE / crop_width, ICON_MATCH_SIZE / crop_height)
    output_width = max(1, round(crop_width * scale))
    output_height = max(1, round(crop_height * scale))
    offset_x = (ICON_MATCH_SIZE - output_width) // 2
    offset_y = (ICON_MATCH_SIZE - output_height) // 2
    normalized = [(0, 0, 0)] * (ICON_MATCH_SIZE * ICON_MATCH_SIZE)

    for output_y in range(output_height):
        source_y = min_y + output_y * crop_height // output_height
        for output_x in range(output_width):
            source_x = min_x + output_x * crop_width // output_width
            normalized[(offset_y + output_y) * ICON_MATCH_SIZE + offset_x + output_x] = (
                pixels[source_y * width + source_x]
            )
    return normalized


def _icon_similarity(first, second):
    first_values = [channel for pixel in first for channel in pixel]
    second_values = [channel for pixel in second for channel in pixel]
    magnitude = math.sqrt(
        sum(value * value for value in first_values)
        * sum(value * value for value in second_values)
    )
    if magnitude == 0:
        return 0.0
    return sum(
        first_value * second_value
        for first_value, second_value in zip(first_values, second_values)
    ) / magnitude


def _select_matching_icon_title(source_pixels, source_width, source_height,
                                candidates):
    source = _normalize_icon_pixels(source_pixels, source_width, source_height)
    if source is None:
        return ""

    scores_by_title = {}
    for title, pixels, width, height in candidates:
        candidate = _normalize_icon_pixels(pixels, width, height)
        if not title or candidate is None:
            continue
        score = _icon_similarity(source, candidate)
        scores_by_title[title] = max(score, scores_by_title.get(title, 0.0))

    ranked = sorted(scores_by_title.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < ICON_MATCH_MIN_SIMILARITY:
        return ""
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < ICON_MATCH_MIN_MARGIN:
        return ""
    return ranked[0][0]


def _raw_rgb_pixels(raw, width, height):
    area = width * height
    if area <= 0 or len(raw) % area:
        return None
    bytes_per_pixel = len(raw) // area
    if bytes_per_pixel not in (3, 4):
        return None
    return [
        (raw[offset + 2], raw[offset + 1], raw[offset])
        for offset in range(0, len(raw), bytes_per_pixel)
    ]


def log(msg):
    print(f"[bridge] {msg}", flush=True)


class SNIItem(dbus.service.Object):
    """Persistent SNI item that can be reused across dock/undock cycles."""

    def __init__(self, bus_name, path, bridge):
        self._bridge = bridge
        self._icon_xid = 0
        self._icon_data = []
        self._title = ""
        self._active = False
        dbus.service.Object.__init__(self, bus_name, path)

    def bind(self, icon_xid, title=""):
        """Bind to a new tray icon window."""
        self._icon_xid = icon_xid
        self._icon_data = []
        self._title = title
        self._active = True
        self.NewStatus("Active")

    def update_title(self, title):
        if title and title != self._title:
            self._title = title
            self.NewTitle()

    def set_passive(self):
        """Icon window hidden: keep the item but report Passive status."""
        if self._active:
            self._active = False
            self.NewStatus("Passive")

    def set_active(self):
        """Icon window visible again: report Active status."""
        if not self._active:
            self._active = True
            self.NewStatus("Active")

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v")
    def Get(self, iface, prop):
        if iface != SNI_ITEM_IFACE:
            return ""
        return self._props().get(prop, "")

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return self._props() if iface == SNI_ITEM_IFACE else {}

    def _props(self):
        return {
            "Category": "ApplicationStatus",
            "Id": f"wine-tray-{self._icon_xid}",
            "Title": self._title,
            "Status": "Active" if self._active else "Passive",
            "IconName": "",
            "IconPixmap": dbus.Array(self._icon_data, signature="(iiay)"),
            "OverlayIconName": "",
            "OverlayIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionIconName": "",
            "AttentionIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionMovieName": "",
            "ToolTip": dbus.Struct(
                ("", dbus.Array([], signature="(iiay)"), "", ""),
                signature="sa(iiay)ss"),
            "ItemIsMenu": dbus.Boolean(False),
            # Standard sentinel for "no menu" (libappindicator/KDE): hosts like
            # noctalia only fall back to the SNI ContextMenu method when the
            # Menu path is empty or exactly /NO_DBUSMENU. Any other path makes
            # them render an empty host-side menu instead of the app's.
            "Menu": dbus.ObjectPath("/NO_DBUSMENU"),
            "WindowId": dbus.Int32(self._icon_xid),
        }

    @dbus.service.method(SNI_ITEM_IFACE, in_signature="ii")
    def Activate(self, x, y):
        if self._active:
            self._bridge.send_click(self._icon_xid, 1, x, y)

    @dbus.service.method(SNI_ITEM_IFACE, in_signature="ii")
    def SecondaryActivate(self, x, y):
        if self._active:
            self._bridge.send_click(self._icon_xid, 2, x, y)

    @dbus.service.method(SNI_ITEM_IFACE, in_signature="ii")
    def ContextMenu(self, x, y):
        if self._active:
            self._bridge.send_click(self._icon_xid, 3, x, y)

    @dbus.service.method(SNI_ITEM_IFACE, in_signature="is")
    def Scroll(self, delta, orientation):
        pass

    @dbus.service.signal(SNI_ITEM_IFACE)
    def NewIcon(self):
        pass

    @dbus.service.signal(SNI_ITEM_IFACE)
    def NewTitle(self):
        pass

    @dbus.service.signal(SNI_ITEM_IFACE)
    def NewStatus(self, status):
        pass

    def update_icon(self, icon_data):
        if icon_data and icon_data != self._icon_data:
            self._icon_data = icon_data
            self.NewIcon()


class XEmbedSNIProxy:
    def __init__(self, byte_order="native"):
        # struct pack format: "<I" = little-endian (native on x86_64),
        # ">I" = big-endian (DBus SNI spec literal).
        self._pack_fmt = "<I" if byte_order == "native" else ">I"
        # Alpha sits at byte 3 in native (B,G,R,A) packing, byte 0 in network
        # (A,R,G,B) packing; crop/alpha scans must use the right offset.
        self._alpha_off = 3 if byte_order == "native" else 0
        self._dead = False
        self._restart_requested = False
        self._display = display.Display()
        self._display.set_error_handler(lambda *a: None)
        self._screen = self._display.screen()
        self._root = self._screen.root
        self._atoms = {}
        self._tray_window = None
        self._bus = None
        self._loop = None
        self._icon_cache = {}  # cache icon data per app (keyed by WM_NAME or class)

        # SNI slot pool: reusable slots to avoid DBus path conflicts
        self._slots = []       # list of {sni, bus_name, dbus_name, xid, icon_ready}
        self._slot_counter = 0

        # Active icon tracking
        self._active_icons = {}  # xid -> slot_index

        for name in ["_NET_SYSTEM_TRAY_S0", "_NET_SYSTEM_TRAY_OPCODE",
                      "_NET_SYSTEM_TRAY_ORIENTATION", "MANAGER",
                      "_XEMBED", "_XEMBED_INFO", "_NET_WM_ICON",
                      "WM_NAME", "_NET_WM_NAME", "UTF8_STRING",
                      "_NET_WM_PID", "_WINE_HWND_STYLE",
                      "WM_PROTOCOLS", "WM_DELETE_WINDOW"]:
            self._atoms[name] = self._display.intern_atom(name)

    def _fatal(self, reason):
        # The X11 connection is unrecoverable from inside the same Display
        # object — pending_events() / queued errors keep allocating inside
        # python-xlib forever. Bail out and let systemd Restart= bring us
        # back with a fresh display.
        if self._dead:
            return False
        self._dead = True
        log(f"X11 connection lost ({reason}); exiting for systemd restart")
        if self._loop is not None:
            self._loop.quit()
        else:
            sys.exit(1)
        return False

    def _init_dbus(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SessionBus()
        for _ in range(20):
            try:
                self._bus.get_object(SNI_WATCHER_BUS, SNI_WATCHER_PATH)
                log("StatusNotifierWatcher found")
                return True
            except dbus.DBusException:
                time.sleep(0.5)
        log("StatusNotifierWatcher not available")
        return False

    def _get_or_create_slot(self):
        """Create an independently addressable SNI slot.

        Separate connections provide independent service lifetimes; separate
        paths keep hosts from deduplicating multiple items from this process.
        """
        self._slot_counter += 1
        bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-{self._slot_counter}"
        object_path = f"/StatusNotifierItem/{self._slot_counter}"

        # Get the session bus address and create an independent connection
        bus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS") or dbus.bus.BUS_SESSION
        slot_bus = dbus.bus.BusConnection(bus_addr)

        dbus_name = dbus.service.BusName(bus_name, slot_bus, do_not_queue=True)
        sni = SNIItem(dbus_name, object_path, self)

        slot = {"sni": sni, "bus_name": bus_name,
                "object_path": object_path,
                "registration_id": f"{bus_name}{object_path}",
                "dbus_name": dbus_name, "slot_bus": slot_bus,
                "xid": None, "window": None, "icon_ready": False}

        # Find an empty position or append
        for i, s in enumerate(self._slots):
            if s is None:
                self._slots[i] = slot
                return i
        self._slots.append(slot)
        return len(self._slots) - 1

    def _claim_tray(self):
        sel_atom = self._atoms["_NET_SYSTEM_TRAY_S0"]

        self._tray_window = self._root.create_window(
            0, 0, EMPTY_TRAY_SIZE, EMPTY_TRAY_SIZE, 0,
            self._screen.root_depth, X.InputOutput, X.CopyFromParent,
            event_mask=(X.StructureNotifyMask | X.SubstructureNotifyMask |
                       X.PropertyChangeMask | X.ExposureMask),
            background_pixel=self._screen.black_pixel,
            override_redirect=False
        )
        self._tray_window.set_wm_name(APPLICATION_ID)
        self._tray_window.set_wm_class(APPLICATION_ID, APPLICATION_ID)
        self._tray_window.set_wm_protocols([self._atoms["WM_DELETE_WINDOW"]])
        self._tray_window.change_property(
            self._display.intern_atom("_NET_WM_WINDOW_TYPE"),
            Xatom.ATOM, 32,
            [self._display.intern_atom("_NET_WM_WINDOW_TYPE_UTILITY")])
        self._tray_window.change_property(
            self._display.intern_atom("_NET_WM_STATE"),
            Xatom.ATOM, 32,
            [self._display.intern_atom("_NET_WM_STATE_SKIP_TASKBAR"),
             self._display.intern_atom("_NET_WM_STATE_SKIP_PAGER")])
        self._tray_window.configure(x=-9999, y=-9999)
        self._tray_window.map()
        self._tray_window.change_property(
            self._atoms["_NET_SYSTEM_TRAY_ORIENTATION"],
            Xatom.CARDINAL, 32, [0])

        self._tray_window.set_selection_owner(sel_atom, X.CurrentTime)
        self._display.sync()

        owner = self._display.get_selection_owner(sel_atom)
        if not owner or owner.id != self._tray_window.id:
            log("Failed to claim tray selection")
            return False

        ev = protocol.event.ClientMessage(
            window=self._root,
            client_type=self._atoms["MANAGER"],
            data=(32, [X.CurrentTime, sel_atom, self._tray_window.id, 0, 0]))
        self._root.send_event(ev, event_mask=X.StructureNotifyMask)
        self._display.flush()

        log(f"Claimed tray selection")
        return True

    def _get_window_title(self, window):
        try:
            prop = window.get_full_property(
                self._atoms["_NET_WM_NAME"], self._atoms["UTF8_STRING"])
            if prop and isinstance(prop.value, bytes):
                title = prop.value.decode("utf-8", "replace").strip("\0 ")
                if title:
                    return title
            title = window.get_wm_name()
            return title.strip() if isinstance(title, str) else ""
        except Exception:
            return ""

    def _get_icon_key(self, icon_win):
        """Get a cache key for the icon window based on its WM_CLASS."""
        try:
            cls = icon_win.get_wm_class()
            if cls:
                return cls[1] or cls[0] or "unknown"
        except Exception:
            pass
        return "unknown"

    def _get_application_icon_candidates(self):
        candidates = []
        try:
            windows = self._root.query_tree().children
        except Exception:
            return candidates

        for window in windows:
            if window.id == self._tray_window.id:
                continue
            title = self._get_window_title(window)
            if not title:
                continue
            try:
                prop = window.get_full_property(
                    self._atoms["_NET_WM_ICON"], Xatom.CARDINAL)
                if not prop or prop.value is None:
                    continue
                for width, height, values in _iter_net_wm_icons(prop.value):
                    if width > 256 or height > 256:
                        continue
                    pixels = [
                        ((int(value) >> 16) & 0xFF,
                         (int(value) >> 8) & 0xFF,
                         int(value) & 0xFF)
                        for value in values
                    ]
                    candidates.append((title, pixels, width, height))
            except Exception:
                continue
        return candidates

    def _match_application_title(self, raw, width, height):
        pixels = _raw_rgb_pixels(raw, width, height)
        if pixels is None:
            return ""
        return _select_matching_icon_title(
            pixels, width, height, self._get_application_icon_candidates())

    def _resize_tray(self, width, height):
        self._tray_window.configure(width=width, height=height)

    def _close_wine_fallback_trays(self, icon_win):
        """Hide Wine's standalone tray after its icon docks externally."""
        if self._dead or icon_win.id not in self._active_icons:
            return False
        try:
            icon_pid = icon_win.get_full_property(
                self._atoms["_NET_WM_PID"], X.AnyPropertyType)
            if not icon_pid or not icon_pid.value:
                return False
            icon_pid = int(icon_pid.value[0])
            windows = self._root.query_tree().children
        except Exception:
            return False

        closed_any = False
        for window in windows:
            try:
                if window.id in (icon_win.id, self._tray_window.id):
                    continue
                attributes = window.get_attributes()
                pid = window.get_full_property(
                    self._atoms["_NET_WM_PID"], X.AnyPropertyType)
                style = window.get_full_property(
                    self._atoms["_WINE_HWND_STYLE"], X.AnyPropertyType)
                protocols = window.get_wm_protocols() or []
                if not (
                    attributes.map_state == X.IsViewable
                    and pid and pid.value and int(pid.value[0]) == icon_pid
                    and style and style.value
                    and (
                        int(style.value[0]) & WINE_FALLBACK_TRAY_STYLE_MASK
                    ) == WINE_FALLBACK_TRAY_STYLE_MASK
                    and not (window.get_wm_name() or "")
                    and self._atoms["WM_DELETE_WINDOW"] in protocols
                ):
                    continue

                # A restart can briefly leave Wine without an XEmbed owner.
                # Wine then shows Shell_TrayWnd, but an ownership race can
                # leave it mapped even after the icon re-docks. Its WM_CLOSE
                # contract hides that fallback without destroying it.
                ev = protocol.event.ClientMessage(
                    window=window,
                    client_type=self._atoms["WM_PROTOCOLS"],
                    data=(32, [self._atoms["WM_DELETE_WINDOW"],
                               X.CurrentTime, 0, 0, 0]))
                window.send_event(ev)
                closed_any = True
                log(
                    f"Closed Wine fallback tray {window.id} "
                    f"after docking {icon_win.id}")
            except Exception:
                continue
        if closed_any:
            self._display.flush()
        return False

    def _dock_icon(self, icon_xid):
        if self._dead or icon_xid in self._active_icons:
            return

        try:
            icon_win = self._display.create_resource_object("window", icon_xid)

            # Resize tray window
            n = len(self._active_icons) + 1
            self._resize_tray(n * TRAY_ICON_SIZE, TRAY_ICON_SIZE)

            x_offset = len(self._active_icons) * TRAY_ICON_SIZE
            # SaveSet protection keeps the foreign icon alive if this bridge
            # crashes and X11 destroys its tray window. KDE's proxy uses the
            # same mechanism before embedding app-owned windows.
            icon_win.change_save_set(X.SetModeInsert)
            icon_win.reparent(self._tray_window, x_offset, 0)
            icon_win.configure(width=TRAY_ICON_SIZE, height=TRAY_ICON_SIZE)
            icon_win.map()
            icon_win.change_attributes(
                event_mask=(X.StructureNotifyMask | X.PropertyChangeMask |
                           X.ExposureMask))

            ev = protocol.event.ClientMessage(
                window=icon_win,
                client_type=self._atoms["_XEMBED"],
                data=(32, [X.CurrentTime, XEMBED_EMBEDDED_NOTIFY, 0,
                           self._tray_window.id, XEMBED_VERSION]))
            icon_win.send_event(ev)
            self._display.flush()

            # Get or reuse an SNI slot
            slot_idx = self._get_or_create_slot()
            slot = self._slots[slot_idx]
            slot["xid"] = icon_xid
            slot["window"] = icon_win
            slot["icon_ready"] = False
            slot["icon_key"] = self._get_icon_key(icon_win)
            title = self._get_window_title(icon_win)
            slot["title_ready"] = bool(title)
            slot["sni"].bind(icon_xid, title)

            # Reuse cached icon for this app so it's not white on re-dock
            cached = self._icon_cache.get(slot["icon_key"])
            if cached:
                slot["sni"].update_icon(cached)

            self._active_icons[icon_xid] = slot_idx
            self._close_wine_fallback_trays(icon_win)
            # Wine processes the old proxy's reparent events asynchronously;
            # close once more after that restart race has settled.
            GLib.timeout_add(
                WINE_FALLBACK_CLOSE_DELAY_MS,
                self._close_wine_fallback_trays,
                icon_win)

            # Register with watcher
            for attempt in range(10):
                try:
                    watcher = self._bus.get_object(SNI_WATCHER_BUS, SNI_WATCHER_PATH)
                    # A unique path prevents hosts from collapsing distinct
                    # items created by separate connections in this process.
                    dbus.Interface(watcher, SNI_WATCHER_BUS).RegisterStatusNotifierItem(
                        slot["registration_id"])
                    break
                except dbus.DBusException:
                    if attempt < 9:
                        time.sleep(0.5)

            log(f"Docked icon {icon_xid} -> slot {slot_idx} ({slot['bus_name']})")

            # Start icon extraction retries
            GLib.timeout_add(500, self._extract_icon_retry, icon_xid)

        except Exception as e:
            log(f"Dock error {icon_xid}: {e}")

    def _release_icon_window(self, icon_win):
        """End XEmbed without destroying the app-owned icon window."""
        try:
            # XEmbed's normal shutdown sequence is unmap, reparent to root.
            # Removing it from our SaveSet afterward prevents redundant rescue
            # processing when this X11 connection closes.
            icon_win.unmap()
            icon_win.reparent(self._root, 0, 0)
            icon_win.change_save_set(X.SetModeDelete)
            self._display.flush()
        except Exception:
            # DestroyNotify reaches us after the icon is already invalid.
            pass

    def _undock_icon(self, icon_xid):
        if icon_xid not in self._active_icons:
            return

        slot_idx = self._active_icons.pop(icon_xid)
        slot = self._slots[slot_idx]
        self._release_icon_window(slot["window"])

        # Fully remove from DBus so waybar drops the icon
        try:
            slot["sni"].remove_from_connection()
        except Exception:
            pass
        try:
            del slot["dbus_name"]
        except Exception:
            pass
        # Close the slot's bus connection
        try:
            slot["slot_bus"].close()
        except Exception:
            pass

        # Remove slot entirely so a fresh one is created next time
        self._slots[slot_idx] = None

        # Resize tray window. Wrapped because a dead X server raises here
        # straight into the GLib idle callback, which is what flooded the
        # journal and leaked python-xlib internal queues for days.
        n = len(self._active_icons)
        try:
            if n:
                self._resize_tray(n * TRAY_ICON_SIZE, TRAY_ICON_SIZE)
            else:
                self._resize_tray(EMPTY_TRAY_SIZE, EMPTY_TRAY_SIZE)
            for i, (xid, si) in enumerate(self._active_icons.items()):
                try:
                    self._slots[si]["window"].configure(
                        x=i * TRAY_ICON_SIZE, y=0)
                except Exception:
                    pass
            self._display.flush()
        except (ConnectionClosedError, IOError, OSError) as e:
            return self._fatal(f"_undock_icon: {e!r}")
        except Exception:
            pass
        log(f"Undocked icon {icon_xid} ({n} remaining)")

    def _extract_icon(self, icon_xid):
        if self._dead or icon_xid not in self._active_icons:
            return False

        slot = self._slots[self._active_icons[icon_xid]]
        if slot["icon_ready"]:
            return False

        icon_win = slot["window"]
        sni = slot["sni"]

        try:
            # Prefer the painted window content — it is what the app actually
            # displays. Wine/Steam often leave a generic/stale _NET_WM_ICON on
            # the icon window while painting the real icon, so _NET_WM_ICON is
            # only a provisional fallback shown until the paint lands.
            self._display.sync()
            geom = icon_win.get_geometry()
            w, h = geom.width, geom.height
            if w > 0 and h > 0:
                pix = icon_win.create_pixmap(w, h, geom.depth)
                gc = icon_win.create_gc()
                try:
                    pix.copy_area(gc, icon_win, 0, 0, w, h, 0, 0)
                    self._display.sync()
                    img = pix.get_image(0, 0, w, h, X.ZPixmap, 0xFFFFFFFF)
                    if img and img.data:
                        bpp = len(img.data) // (w * h) if w * h else 4
                        drawn = sum(1 for i in range(0, len(img.data), bpp)
                                    if any(img.data[i+j] > 10
                                           for j in range(min(3, bpp))))
                        if drawn > (w * h * 0.05):
                            icon_data = self._raw_to_argb(img.data, w, h, geom.depth)
                            if icon_data:
                                sni.update_icon(icon_data)
                                if not slot.get("title_ready"):
                                    title = self._match_application_title(img.data, w, h)
                                    if title:
                                        sni.update_title(title)
                                        slot["title_ready"] = True
                                        log(f"Icon {icon_xid}: matched title {title!r}")
                                self._icon_cache[slot.get("icon_key", "unknown")] = icon_data
                                slot["icon_ready"] = True
                                log(f"Icon {icon_xid}: extracted ({w}x{h}, {drawn}px)")
                                return False
                finally:
                    gc.free()
                    pix.free()

            # Painted content not usable (yet): fall back to _NET_WM_ICON as a
            # provisional icon and keep retrying the paint on the next pass.
            icon_prop = icon_win.get_full_property(
                self._atoms["_NET_WM_ICON"], Xatom.CARDINAL)
            if icon_prop and icon_prop.value is not None and len(icon_prop.value) >= 3:
                icons = self._parse_net_wm_icon(icon_prop.value)
                if icons:
                    # Provisional: show it but don't cache/mark ready so the
                    # real painted icon can replace it when drawn.
                    sni.update_icon(icons)
                    log(f"Icon {icon_xid}: provisional _NET_WM_ICON")
            return True  # retry - painted content not ready
        except (ConnectionClosedError, IOError, OSError) as e:
            return self._fatal(f"_extract_icon: {e!r}")
        except Exception as e:
            log(f"Icon error {icon_xid}, undocking: {e}")
            GLib.idle_add(self._undock_icon, icon_xid)
        return False

    def _extract_icon_retry(self, icon_xid):
        if icon_xid not in self._active_icons:
            return False
        slot = self._slots[self._active_icons[icon_xid]]
        if slot["icon_ready"]:
            return False
        retries = slot.get("retries", 0)
        if retries >= 30:
            return False
        slot["retries"] = retries + 1
        return self._extract_icon(icon_xid)

    def _parse_net_wm_icon(self, data):
        best = None
        best_size = 0
        for w, h, pixels in _iter_net_wm_icons(data):
            if w * h > best_size and w <= 256:
                best_size = w * h
                best = (w, h, b"".join(
                    struct.pack(self._pack_fmt, int(p) & 0xFFFFFFFF) for p in pixels))
        if best:
            w, h, argb = best
            return [dbus.Struct((dbus.Int32(w), dbus.Int32(h),
                                 dbus.ByteArray(argb)), signature="iiay")]
        return []

    def _raw_to_argb(self, raw, w, h, depth):
        try:
            area = w * h
            if area <= 0:
                return None
            bpp = len(raw) // area
            if bpp not in (3, 4):
                return None
            # Alpha handling: respect the source alpha when it carries real
            # information (semi-transparent pixels, or a 0/255 mask). Wine
            # often hands us degenerate 32-bit data (alpha all zero, or
            # uniformly 255 from a 24-bit buffer) — treat that as opaque and
            # chroma-key the black background instead. Keying only applies
            # when the icon sits on a black background (all four corners
            # near-black), so flat opaque icons with dark content stay intact.
            if bpp == 4:
                alphas = {raw[i * bpp + 3] for i in range(area)}
                respect_alpha = (any(0 < a < 255 for a in alphas)
                                 or (0 in alphas and 255 in alphas))
            else:
                respect_alpha = False
            key = not respect_alpha and all(
                sum(raw[c * bpp:c * bpp + 3]) < 30
                for c in (0, w - 1, (h - 1) * w, (h - 1) * w + w - 1))
            pixels = []
            for i in range(area):
                o = i * bpp
                b, g, r = raw[o], raw[o + 1], raw[o + 2]
                if respect_alpha:
                    a = raw[o + 3]
                else:
                    a = 255
                    if key and r + g + b < 30:
                        a = 0
                pixels.append(struct.pack(self._pack_fmt,
                                          (a << 24) | (r << 16) | (g << 8) | b))
            argb = b"".join(pixels)
            if argb:
                cropped = self._crop_argb(argb, w, h)
                if cropped:
                    cw, ch, cdata = cropped
                    scaled = self._scale_argb(cdata, cw, ch, 48, 48)
                    return [dbus.Struct((dbus.Int32(48), dbus.Int32(48),
                                        dbus.ByteArray(scaled)), signature="iiay")]
        except Exception:
            pass
        return None

    def _crop_argb(self, argb, w, h):
        min_x, min_y, max_x, max_y = w, h, 0, 0
        for y in range(h):
            for x in range(w):
                # Alpha is the byte this packing puts in the slot the host
                # reads as alpha; the earlier fixed byte-3 check mis-cropped
                # icons with no blue channel (pure red/yellow) and was wrong
                # entirely in network order.
                if argb[(y * w + x) * 4 + self._alpha_off] > 0:
                    min_x, min_y = min(min_x, x), min(min_y, y)
                    max_x, max_y = max(max_x, x), max(max_y, y)
        if max_x < min_x:
            return None
        min_x, min_y = max(0, min_x - 1), max(0, min_y - 1)
        max_x, max_y = min(w - 1, max_x + 1), min(h - 1, max_y + 1)
        cw, ch = max_x - min_x + 1, max_y - min_y + 1
        out = bytearray(cw * ch * 4)
        for y in range(ch):
            s = ((min_y + y) * w + min_x) * 4
            d = y * cw * 4
            out[d:d + cw * 4] = argb[s:s + cw * 4]
        return (cw, ch, bytes(out))

    def _scale_argb(self, argb, sw, sh, dw, dh):
        out = bytearray(dw * dh * 4)
        for y in range(dh):
            for x in range(dw):
                s = ((y * sh // dh) * sw + (x * sw // dw)) * 4
                d = (y * dw + x) * 4
                out[d:d+4] = argb[s:s+4]
        return bytes(out)

    def send_click(self, icon_xid, button, root_x=0, root_y=0):
        if self._dead or icon_xid not in self._active_icons:
            return
        slot = self._slots[self._active_icons[icon_xid]]
        icon_win = slot["window"]
        try:
            geom = icon_win.get_geometry()
            ex, ey = geom.width // 2, geom.height // 2
            rx, ry = (root_x, root_y) if (root_x or root_y) else (ex, ey)
            # Apps pop their menu at the pointer, not at the event coords, so
            # warp the X pointer to the host-reported interaction point
            # (best-effort: Xwayland may ignore it over native surfaces).
            if root_x or root_y:
                self._root.warp_pointer(X.NONE, 0, 0, 0, 0, rx, ry)
                self._display.flush()
            # Send both events with propagate=true and a combined mask: the
            # client may only have selected one of the two masks, and without
            # propagation a missing selection drops the event entirely
            # (synthetic right-clicks opened no menu before this fix).
            mask = X.ButtonPressMask | X.ButtonReleaseMask
            for EvType in [protocol.event.ButtonPress, protocol.event.ButtonRelease]:
                state = 0 if EvType == protocol.event.ButtonPress \
                    else (1 << (7 + button))
                icon_win.send_event(EvType(
                    time=X.CurrentTime, root=self._root, window=icon_win,
                    child=X.NONE, root_x=rx, root_y=ry, event_x=ex, event_y=ey,
                    state=state, detail=button, same_screen=True),
                    propagate=True, event_mask=mask)
            self._display.flush()
        except (ConnectionClosedError, IOError, OSError) as e:
            self._fatal(f"send_click: {e!r}")
        except Exception as e:
            log(f"Click error {icon_xid}, undocking stale icon: {e}")
            GLib.idle_add(self._undock_icon, icon_xid)

    def _process_x11(self):
        if self._dead:
            return False
        try:
            while self._display.pending_events():
                ev = self._display.next_event()
                if ev.type == X.ClientMessage:
                    event_window = getattr(ev, "window", None)
                    event_window_id = getattr(event_window, "id", event_window)
                    if (ev.client_type == self._atoms["WM_PROTOCOLS"] and
                            ev.data[1][0] == self._atoms["WM_DELETE_WINDOW"] and
                            event_window_id == self._tray_window.id):
                        log("Tray window close requested; restarting service.")
                        self._restart_requested = True
                        self._loop.quit()
                        return False
                    if (hasattr(ev, 'client_type') and
                            ev.client_type == self._atoms["_NET_SYSTEM_TRAY_OPCODE"] and
                            ev.data[1][1] == SYSTEM_TRAY_REQUEST_DOCK):
                        xid = ev.data[1][2]
                        if xid:
                            GLib.idle_add(self._dock_icon, xid)
                elif ev.type == X.DestroyNotify:
                    xid = getattr(ev, 'window', None)
                    if xid and xid.id in self._active_icons:
                        GLib.idle_add(self._undock_icon, xid.id)
                elif ev.type == X.UnmapNotify:
                    # Icon window hidden (e.g. Wine toggling tray visibility):
                    # keep the item, report Passive. Only destruction undocks.
                    xid = getattr(ev, 'window', None)
                    if xid and xid.id in self._active_icons:
                        self._slots[self._active_icons[xid.id]]["sni"].set_passive()
                elif ev.type == X.MapNotify:
                    xid = getattr(ev, 'window', None)
                    if xid and xid.id in self._active_icons:
                        slot = self._slots[self._active_icons[xid.id]]
                        slot["sni"].set_active()
                        slot["icon_ready"] = False
                        slot.pop("retries", None)
                        GLib.timeout_add(100, self._extract_icon_retry, xid.id)
                elif ev.type == X.Expose:
                    xid = getattr(ev, 'window', None)
                    if xid and xid.id in self._active_icons:
                        GLib.timeout_add(100, self._extract_icon_retry, xid.id)
        except (ConnectionClosedError, IOError, OSError) as e:
            return self._fatal(f"_process_x11: {e!r}")
        except Exception:
            pass
        return True

    def _re_register_all(self):
        if not self._active_icons:
            return False
        log(f"Re-registering {len(self._active_icons)} icons...")
        for xid, si in self._active_icons.items():
            slot = self._slots[si]
            try:
                watcher = self._bus.get_object(SNI_WATCHER_BUS, SNI_WATCHER_PATH)
                dbus.Interface(watcher, SNI_WATCHER_BUS).RegisterStatusNotifierItem(
                    slot["registration_id"])
                slot["sni"].NewIcon()
                log(f"Re-registered {xid}")
            except Exception as e:
                log(f"Re-register failed {xid}: {e}")
        return False

    def run(self):
        log("Starting...")
        if not self._init_dbus():
            return 1
        if not self._claim_tray():
            # Another tray host owns the selection (e.g. Plasma's proxy); don't
            # fight it — exit cleanly so Restart=on-failure doesn't loop forever.
            log("Another tray host owns the selection; exiting cleanly.")
            return 0

        self._bus.watch_name_owner(SNI_WATCHER_BUS,
            lambda owner: GLib.timeout_add(1000, self._re_register_all)
                          if owner and self._active_icons else None)

        self._root.change_attributes(event_mask=X.StructureNotifyMask)
        self._loop = GLib.MainLoop()
        GLib.timeout_add(50, self._process_x11)

        signal.signal(signal.SIGINT, lambda *_: self._loop.quit())
        signal.signal(signal.SIGTERM, lambda *_: self._loop.quit())

        log("Ready")
        try:
            self._loop.run()
        except KeyboardInterrupt:
            pass

        for xid in list(self._active_icons.keys()):
            self._undock_icon(xid)
        try:
            self._display.close()
        except Exception:
            pass
        if self._dead:
            log("Stopped (X11 dead — exiting nonzero so systemd restarts).")
            return 1
        if self._restart_requested:
            log("Stopped (tray window closed — exiting nonzero so systemd restarts).")
            return 1
        log("Stopped.")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="XEmbed SNI Proxy - X11 tray to StatusNotifierItem for Wayland")
    parser.add_argument(
        "--byte-order",
        choices=["native", "network"],
        default="network",
        help=(
            "IconPixmap packing byte order. 'network' (default) follows the DBus "
            "SNI spec (bytes A,R,G,B) and is what every major host reads: "
            "waybar, noctalia, Quickshell and KDE all decode the spec's ARGB32 "
            "order. 'native' packs little-endian (B,G,R,A) and is only for "
            "hosts that build a QImage directly from the raw bytes without "
            "conversion."
        ),
    )
    args = parser.parse_args()
    sys.exit(XEmbedSNIProxy(byte_order=args.byte_order).run())


if __name__ == "__main__":
    main()
