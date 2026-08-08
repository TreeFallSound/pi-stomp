# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from typing import TYPE_CHECKING, Optional, Protocol, TypedDict, cast

from modalapi.bluetooth import (
    BluetoothManager,
    BtDevice,
    BtStatus,
    ConnectCmd,
    DeviceKind,
    DisconnectCmd,
    ForgetCmd,
    InstallSupportCmd,
    PairCmd,
    PowerCmd,
    StartDiscoveryCmd,
    StopDiscoveryCmd,
    parse_bluez_error,
)
from uilib import Config, MessageDialog, get_line_height
from uilib.glyphs import PillGlyph, SignalBarsGlyph
from uilib.menu import Menu, MenuItem
from uilib.rich_text import IconSeg, Segment, Spacer, TextSeg

if TYPE_CHECKING:
    from pistomp.lcd320x240 import Lcd


class _BluetoothHost(Protocol):
    """The handler-side surface BluetoothMenu needs."""

    bluetooth_manager: BluetoothManager
    bluetooth_status: Optional[BtStatus]


MENU_WIDTH = 288  # wider than the default; device names run long

ACTIVE_GLYPH = "✔"
SEP = "·"

# BLE-MIDI peripherals only advertise while discoverable.
EMPTY_NEARBY = ("No devices found.", "Put it in pairing mode.")
PAIRING_HINT = "press its button"


class BtRow(TypedDict):
    address: str
    name: str
    kind: DeviceKind
    paired: bool
    connected: bool
    present: bool  # bluez currently holds an object for it
    rssi: Optional[int]
    device: Optional[BtDevice]


def signal_bars_level(rssi: int) -> int:
    """0..4-bar bucket for a dBm RSSI. BT RSSI is noisier than wifi's, so the
    bucketing is what keeps jitter out of the row signature."""
    return max(1, min(4, (rssi + 100) // 18))


RowSig = tuple[str, str, bool, bool, bool, Optional[int], Optional[str]]


def _rows_sig(rows: list[BtRow], busy: dict[str, str]) -> tuple[RowSig, ...]:
    return tuple(
        (
            r["address"],
            r["name"],
            r["paired"],
            r["connected"],
            r["present"],
            None if r["rssi"] is None else signal_bars_level(r["rssi"]),
            busy.get(r["address"]),
        )
        for r in rows
    )


def _glyph_height() -> int:
    return get_line_height(Config().get_font("default"))


class BluetoothMenu:
    """Pair, connect, and forget BLE-MIDI and HID devices; toggle the radio."""

    def __init__(self, lcd: "Lcd") -> None:
        self.lcd: "Lcd" = lcd
        self._root_menu: Optional["Menu"] = None
        self._nearby_menu: Optional["Menu"] = None
        self._root_sig: tuple[RowSig, ...] = ()
        self._nearby_sig: tuple[RowSig, ...] = ()
        self._busy: dict[str, str] = {}
        self._awaiting: Optional[str] = None  # address to pair as soon as it appears
        self._discovering: bool = False

    @property
    def _host(self) -> _BluetoothHost:
        h = self.lcd.handler
        assert h is not None, "BluetoothMenu requires lcd.handler to be set"
        return cast(_BluetoothHost, h)

    @property
    def _manager(self) -> BluetoothManager:
        return self._host.bluetooth_manager

    @property
    def _status(self) -> BtStatus:
        return self._host.bluetooth_status or {}

    @property
    def _pstack(self):
        return self.lcd.pstack

    # ----- entry points -----

    def open(self, event: object = None, widget: object = None) -> None:
        self._render_root_menu()

    def tick(self) -> None:
        """Handler poll hook (2s). Discovery is held open only while the nearby
        list is on screen — bluez purges unpaired device objects the moment it
        stops, so leaving it running elsewhere would just burn radio."""
        nearby_open = self._nearby_menu is not None and self._pstack.current is self._nearby_menu
        if nearby_open and not self._discovering:
            self._start_discovery()
        elif not nearby_open and self._discovering:
            self._stop_discovery()

    def _start_discovery(self) -> None:
        self._discovering = True
        self._manager.queue.submit_scan(StartDiscoveryCmd(), self._on_discovery_change)

    def _stop_discovery(self) -> None:
        self._discovering = False
        self._awaiting = None
        self._manager.queue.submit_scan(StopDiscoveryCmd(), self._on_discovery_change)

    def _on_discovery_change(self, result: object) -> None:
        if isinstance(result, Exception):
            self._discovering = False

    # ----- rows -----

    def _current_rows(self) -> tuple[list[BtRow], list[BtRow]]:
        """Returns (root_rows, nearby_rows).

        The root list is the union of our known-device store and bluez's paired
        set: a non-bonding device drops to unpaired the moment it disconnects,
        so bluez alone would silently lose it from the menu."""
        devices = self._manager.devices()
        by_address = {d["address"].upper(): d for d in devices}

        root: list[BtRow] = []
        claimed: set[str] = set()
        for known in self._manager.known_devices():
            device = by_address.get(known["address"].upper())
            if device is None and known["name"]:
                # A rotated resolvable private address under a known name is
                # the same device, not a new one.
                device = next((d for d in devices if d["name"] == known["name"]), None)
            if device is not None:
                claimed.add(device["address"].upper())
            root.append(self._row(known["name"], known["address"], known["kind"], device))

        for device in devices:
            if device["address"].upper() in claimed or not device["paired"]:
                continue
            claimed.add(device["address"].upper())
            root.append(self._row(device["name"], device["address"], device["kind"].value, device))

        nearby = [
            self._row(d["name"], d["address"], d["kind"].value, d)
            for d in devices
            if d["address"].upper() not in claimed and not d["paired"]
        ]

        root.sort(key=lambda r: (not r["connected"], not r["present"], r["name"].lower()))
        nearby.sort(key=lambda r: -(r["rssi"] if r["rssi"] is not None else -999))
        return root, nearby

    @staticmethod
    def _row(name: str, address: str, kind: str, device: Optional[BtDevice]) -> BtRow:
        try:
            device_kind = DeviceKind(kind)
        except ValueError:
            device_kind = DeviceKind.OTHER
        return BtRow(
            address=device["address"] if device is not None else address,
            name=(device["name"] if device is not None and device["name"] else name) or address,
            kind=device["kind"] if device is not None else device_kind,
            paired=bool(device is not None and device["paired"]),
            connected=bool(device is not None and device["connected"]),
            present=device is not None,
            rssi=device["rssi"] if device is not None else None,
            device=device,
        )

    def _row_segments(self, row: BtRow, known: bool) -> list[Segment]:
        h = _glyph_height()
        busy = self._busy.get(row["address"])
        label = row["name"]
        if busy is None and known and not row["present"]:
            # Say what to do, not just "Disconnected" — a non-bonding device
            # needs the physical button before anything can reach it.
            label = "%s %s %s" % (row["name"], SEP, PAIRING_HINT)
        segs: list[Segment] = [TextSeg(label)]
        if row["kind"] is not DeviceKind.OTHER:
            segs.append(TextSeg(" "))
            segs.append(IconSeg(PillGlyph("M" if row["kind"] is DeviceKind.MIDI else "I", height=h)))
        if row["connected"]:
            segs.append(TextSeg(" " + ACTIVE_GLYPH))
        segs.append(Spacer())
        if busy is not None:
            segs.append(TextSeg(busy))
        elif row["rssi"] is not None:
            segs.append(IconSeg(SignalBarsGlyph(signal_bars_level(row["rssi"]), height=h)))
        return segs

    # ----- render -----

    def _title(self) -> str:
        connected = self._status.get("connected") or []
        if connected:
            return "Bluetooth %s %s" % (SEP, connected[0])
        if not self._status.get("enabled"):
            return "Bluetooth %s Off" % SEP
        return "Bluetooth"

    def _build_items(self, rows: list[BtRow]) -> list[MenuItem]:
        items: list[MenuItem] = []
        if not self._status.get("capable"):
            items.append(("Needs a system update", None, None))
            items.append(("Install Bluetooth support", self._install_support, None))
            return items
        if not self._status.get("enabled"):
            items.append(("Turn Bluetooth on", self._toggle_power, None))
            return items
        items.extend(
            (self._row_segments(r, known=True), self._on_device_tap, r, None, self._on_device_long_tap) for r in rows
        )
        items.append(("Nearby devices...", self._open_nearby_menu, None))
        items.append(("Turn Bluetooth off", self._toggle_power, None))
        return items

    def _render_root_menu(self, default_label: Optional[str] = None) -> None:
        rows, _ = self._current_rows()
        self._root_sig = _rows_sig(rows, self._busy)
        self._root_menu = self.lcd.draw_selection_menu(
            self._build_items(rows), self._title(), dismiss_option=True, default_item=default_label, width=MENU_WIDTH
        )

    def _render_nearby_menu(self, default_label: Optional[str] = None) -> None:
        _, nearby = self._current_rows()
        if nearby:
            items: list[MenuItem] = [(self._row_segments(r, known=False), self._on_nearby_tap, r) for r in nearby]
        else:
            items = [(line, None, None) for line in EMPTY_NEARBY]
        self._nearby_sig = _rows_sig(nearby, self._busy)
        self._nearby_menu = self.lcd.draw_selection_menu(
            items, "Nearby Devices", dismiss_option=True, default_item=default_label, width=MENU_WIDTH
        )

    def notify_status_change(self) -> None:
        """Rebuild in place, preserving the cursor. Refuses to touch anything
        unless one of our menus is on top, so a rebuild can't yank a dialog
        out from under the user."""
        current = self._pstack.current
        rows, nearby = self._current_rows()
        if self._nearby_menu is not None and current is self._nearby_menu:
            self._maybe_pair_awaited(nearby)
            if _rows_sig(nearby, self._busy) != self._nearby_sig:
                self._rerender_nearby()
        elif self._root_menu is not None and current is self._root_menu:
            self._maybe_pair_awaited(rows)
            if _rows_sig(rows, self._busy) != self._root_sig:
                self._rerender_root()

    def _maybe_pair_awaited(self, rows: list[BtRow]) -> None:
        """A known device the user tapped while it was out of range: pair it
        the moment discovery turns it up, so their only job is the button."""
        if self._awaiting is None:
            return
        for row in rows:
            if row["address"].upper() == self._awaiting.upper() and row["present"]:
                self._awaiting = None
                self._submit_pair(row)
                return

    def _rerender_root(self) -> None:
        assert self._root_menu is not None
        keep = self._root_menu.selected_label()
        old = self._root_menu
        self._root_menu = None
        self._pstack.pop_panel(old)
        self._render_root_menu(default_label=keep)

    def _rerender_nearby(self) -> None:
        assert self._nearby_menu is not None
        keep = self._nearby_menu.selected_label()
        old = self._nearby_menu
        self._nearby_menu = None
        self._pstack.pop_panel(old)
        self._render_nearby_menu(default_label=keep)

    # ----- actions -----

    def _toggle_power(self, _: object = None) -> None:
        enable = not self._status.get("enabled")
        self._pstack.pop_panel(None)
        self._manager.queue.submit(PowerCmd(enable), self._on_op_done)

    def _install_support(self, _: object = None) -> None:
        self._pstack.pop_panel(None)
        self._manager.queue.submit(InstallSupportCmd(), self._on_op_done)

    def _open_nearby_menu(self, _: object = None) -> None:
        self._render_nearby_menu()
        self._start_discovery()

    def _on_device_tap(self, row: BtRow) -> None:
        if row["connected"]:
            self._open_device_submenu(row)
            return
        if not row["present"]:
            # Out of range: start looking and pair on sight.
            self._awaiting = row["address"]
            self._start_discovery()
            self._mark_busy(row, "Waiting…")
            return
        if row["paired"]:
            self._submit_connect(row)
        else:
            self._submit_pair(row)

    def _on_nearby_tap(self, row: BtRow) -> None:
        self._submit_pair(row)

    def _on_device_long_tap(self, row: BtRow) -> None:
        self._open_device_submenu(row)

    def _open_device_submenu(self, row: BtRow) -> None:
        items: list[MenuItem] = []
        if row["connected"]:
            items.append(("Disconnect", self._disconnect, row))
        items.append(("Forget", self._forget, row))
        self.lcd.draw_selection_menu(items, row["name"], dismiss_option=True)

    # ----- command submission -----

    def _device_of(self, row: BtRow) -> BtDevice:
        device = row["device"]
        assert device is not None, "callers gate on row['present']"
        return device

    def _mark_busy(self, row: BtRow, text: str) -> None:
        self._busy[row["address"]] = text
        self.notify_status_change()

    def _clear_busy(self, address: str) -> None:
        self._busy.pop(address, None)
        self.notify_status_change()

    def _submit_pair(self, row: BtRow) -> None:
        self._mark_busy(row, "Pairing…")
        address = row["address"]
        self._manager.queue.submit(PairCmd(self._device_of(row)), lambda err: self._on_device_op_done(err, address))

    def _submit_connect(self, row: BtRow) -> None:
        self._mark_busy(row, "Connecting…")
        address = row["address"]
        self._manager.queue.submit(ConnectCmd(self._device_of(row)), lambda err: self._on_device_op_done(err, address))

    def _disconnect(self, row: BtRow) -> None:
        self._pstack.pop_panel(None)
        self._manager.queue.submit(DisconnectCmd(self._device_of(row)), self._on_op_done)

    def _forget(self, row: BtRow) -> None:
        self._pstack.pop_panel(None)
        device = row["device"] or BtDevice(
            path="",
            address=row["address"],
            name=row["name"],
            kind=row["kind"],
            paired=row["paired"],
            connected=row["connected"],
            trusted=False,
            rssi=None,
        )
        self._manager.queue.submit(ForgetCmd(device), self._on_op_done)

    # ----- results -----

    def _on_device_op_done(self, err: object, address: str) -> None:
        self._clear_busy(address)
        self._on_op_done(err)

    def _on_op_done(self, err: object) -> None:
        if isinstance(err, Exception):
            self._show_error(parse_bluez_error(err))
        elif isinstance(err, str):
            self._show_error(parse_bluez_error(err))

    def _show_error(self, message: str) -> None:
        self._pstack.push_panel(MessageDialog(self._pstack, message, title="Bluetooth"))
