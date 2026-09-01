"""Bluetooth menu snapshot suite.

Mirrors the wifi suite's categories, which are the ones that caught real bugs
there: multi-frame sagas via a deferred-callback list, scan pacing, error
kinds, and modal safety."""

import pytest

from modalapi.bluetooth import DeviceKind
from tests.v3.conftest import make_bt_device, make_bt_known, make_saved, make_scanned
from uilib.menu import Menu
from uilib.misc import InputEvent


def _open(v3_system):
    """Open the LCD's own BluetoothMenu, not a fresh one: the handler's status
    callback re-renders `lcd.bluetooth_menu`, so a private instance would never
    see the repaints a status change drives."""
    lcd = v3_system.handler._lcd
    lcd.bluetooth_menu.open()
    return lcd


def _footer_labels(menu):
    return [slot.text for slot in menu.footer if slot is not None]


def _labels(menu):
    from uilib.menu import _item_label, label_key

    return [label_key(_item_label(i)) for i in menu.items]


def _click_row(lcd, text):
    """Move the cursor onto the row whose label contains `text`, then click."""
    menu = lcd.pstack.current
    assert isinstance(menu, Menu)
    for idx, label in enumerate(_labels(menu)):
        if text in label:
            menu.sel_widget(menu.sel_children()[idx])
            menu.input_event(InputEvent.CLICK)
            return
    raise AssertionError("no row containing %r in %r" % (text, _labels(menu)))


# ----- root menu -----


def test_root_menu_lists_paired_device(v3_system, bluetooth_state, snapshot):
    bluetooth_state(
        devices=[make_bt_device(paired=True, connected=True)],
        known=[make_bt_known()],
    )
    _open(v3_system)
    snapshot("root_connected")


def test_root_menu_when_off_offers_only_power_on(v3_system, bluetooth_state, snapshot):
    bluetooth_state(enabled=False)
    lcd = _open(v3_system)
    menu = lcd.pstack.current
    assert "Turn Bluetooth on" in _labels(menu)
    assert "Nearby devices..." not in _labels(menu)
    snapshot("root_off")


def test_power_toggle_shows_wait_then_settles(v3_system, bluetooth_state, snapshot):
    """The toggle takes tens of seconds; the menu must say so instead of
    ignoring the click, then return to normal when it lands."""
    deferred: list = []
    bluetooth_state(enabled=False, deferred=deferred)
    lcd = _open(v3_system)
    _click_row(lcd, "Turn Bluetooth on")
    menu = lcd.pstack.current
    labels = _labels(menu)
    assert "Turning Bluetooth on…" in labels
    assert "Turn Bluetooth on" not in labels, "the toggle row must be replaced while in flight"

    # Second tap while waiting: no second PowerCmd is submitted — the queue
    # dedupes by key, and the wait row carries no action anyway.
    assert sum(type(c).__name__ == "PowerCmd" for c, _ in deferred) == 1

    _, on_done = deferred.pop()
    on_done(None)
    # Success publishes fresh status; the test harness has no poll loop, so
    # drive the publish the way poll() would.
    v3_system.handler._on_bluetooth_status_change(
        {"supported": True, "capable": True, "enabled": True, "powered": True, "discovering": False, "connected": []}
    )
    menu = lcd.pstack.current
    assert "Turning Bluetooth on…" not in _labels(menu)
    assert "Nearby devices..." in _labels(menu)
    snapshot("root_on")


def test_power_toggle_failure_clears_wait_and_shows_error(v3_system, bluetooth_state):
    deferred: list = []
    bluetooth_state(enabled=False, deferred=deferred)
    lcd = _open(v3_system)
    _click_row(lcd, "Turn Bluetooth on")
    assert "Turning Bluetooth on…" in _labels(lcd.pstack.current)

    _, on_done = deferred.pop()
    on_done("sudo: a password is required")
    menu = lcd.pstack.current
    assert not isinstance(menu, Menu), "a failure must raise a dialog over the menu"
    text = " ".join(
        w.text for w in getattr(menu, "sel_list", []) + getattr(menu, "widgets", []) if hasattr(w, "text")
    )
    assert "password" in text


def test_incapable_image_says_so_and_offers_nothing(v3_system, bluetooth_state, snapshot):
    bluetooth_state(capable=False)
    lcd = _open(v3_system)
    labels = _labels(lcd.pstack.current)
    assert "Please install pistomp-bluetooth" in labels
    assert not any("Install" in label for label in labels)
    assert "Nearby devices..." not in labels
    snapshot("root_needs_package")


def test_known_but_absent_device_shows_just_its_name(v3_system, bluetooth_state, snapshot):
    """A known device bluez can't see shows the plain name, like a saved
    wifi network that's out of range — no prescriptive hint. Tapping the
    row is what starts the search-and-pair flow."""
    bluetooth_state(devices=[], known=[make_bt_known()])
    lcd = _open(v3_system)
    menu = lcd.pstack.current
    labels = [label.strip() for label in _labels(menu)]
    assert "EV-1-WL" in labels
    assert not any("press its" in label for label in labels)
    snapshot("root_known_absent")


def test_hid_device_carries_an_input_badge(v3_system, bluetooth_state, snapshot):
    bluetooth_state(
        devices=[make_bt_device(name="R400 Presenter", kind=DeviceKind.INPUT, paired=True)],
        known=[make_bt_known(name="R400 Presenter", kind=DeviceKind.INPUT)],
    )
    _open(v3_system)
    snapshot("root_hid_badge")


# ----- nearby -----


def test_empty_nearby_list_names_pairing_mode(v3_system, bluetooth_state, snapshot):
    """BLE-MIDI peripherals only advertise while discoverable — this string
    prevents more confusion than anything else in the feature."""
    bluetooth_state(devices=[])
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    menu = lcd.pstack.current
    assert any("Put it in pairing mode" in label for label in _labels(menu))
    snapshot("nearby_empty")


def test_nearby_lists_only_unpaired_devices(v3_system, bluetooth_state, snapshot):
    bluetooth_state(
        devices=[
            make_bt_device(),
            make_bt_device(name="R400 Presenter", address="C8:3B:44:10:02:9A", kind=DeviceKind.INPUT, rssi=-71),
            make_bt_device(name="Already Paired", address="11:22:33:44:55:66", paired=True),
        ],
        known=[make_bt_known(name="Already Paired", address="11:22:33:44:55:66")],
    )
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    labels = _labels(lcd.pstack.current)
    assert any("EV-1-WL" in label for label in labels)
    assert not any("Already Paired" in label for label in labels)
    snapshot("nearby_list")


def test_opening_nearby_starts_discovery(v3_system, bluetooth_state):
    mgr = bluetooth_state(devices=[])
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    assert mgr.queue.submit_scan.called


def test_tick_does_not_rescan_while_the_root_menu_is_open(v3_system, bluetooth_state):
    """Discovery is held open only for the nearby list; leaving it running
    under the root menu would burn radio for nothing."""
    mgr = bluetooth_state(devices=[])
    lcd = _open(v3_system)
    mgr.queue.submit_scan.reset_mock()
    lcd.bluetooth_menu.tick()
    assert not mgr.queue.submit_scan.called


def test_leaving_nearby_stops_discovery(v3_system, bluetooth_state):
    mgr = bluetooth_state(devices=[])
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    lcd.pstack.pop_panel(lcd.pstack.current)
    mgr.queue.submit_scan.reset_mock()
    lcd.bluetooth_menu.tick()
    submitted = [c.args[0] for c in mgr.queue.submit_scan.call_args_list]
    assert any(type(cmd).__name__ == "StopDiscoveryCmd" for cmd in submitted)


def test_ghost_device_vanishes_from_nearby_once_stale(v3_system, bluetooth_state):
    """A device switched off mid-scan: bluez keeps its object with the last
    RSSI and never signals the disappearance, so the manager's staleness
    eviction is the only thing that drops the row. What the user must see:
    it disappears from the nearby list instead of sitting there as a
    tap-target for a doomed Pair()."""
    mgr = bluetooth_state(devices=[make_bt_device()])
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    assert any("EV-1-WL" in label for label in _labels(lcd.pstack.current))

    # The device went dark: the next poll's device list no longer has it.
    mgr.devices.return_value = []
    lcd.bluetooth_menu.notify_status_change()

    labels = _labels(lcd.pstack.current)
    assert not any("EV-1-WL" in label for label in labels), "stale ghost must leave the nearby list"
    assert any("Put it in pairing mode" in label for label in labels)


# ----- pairing saga -----


def test_pairing_shows_progress_then_settles(v3_system, bluetooth_state, snapshot):
    """Multi-frame: the in-row 'Pairing…' text must appear while the command
    is in flight, and success drops back to the root list showing the device."""
    deferred: list = []
    known: list = []
    mgr = bluetooth_state(devices=[make_bt_device()], known=known, deferred=deferred)
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    _click_row(lcd, "EV-1-WL")
    snapshot("pairing_in_flight")

    # The pair landed: bluez now holds it paired, and the manager remembered it.
    device = mgr.devices.return_value[0]
    device["paired"] = True
    device["connected"] = True
    known.append(make_bt_known())
    _, on_done = deferred.pop()
    on_done(None)
    menu = lcd.pstack.current
    assert _labels(menu)[0].startswith("EV-1-WL"), "pairing success must land on the root list"
    snapshot("pairing_done")


@pytest.mark.parametrize(
    "error,expected",
    [
        (Exception("org.bluez.Error.AuthenticationFailed: no"), "pairing failed"),
        (Exception("org.bluez.Error.ConnectionAttemptFailed: x"), "is it still in pairing mode?"),
        (Exception("org.bluez.Error.NotAvailable: gone"), "no longer in range"),
    ],
)
def test_pairing_failures_surface_a_dialog(v3_system, bluetooth_state, error, expected):
    deferred: list = []
    bluetooth_state(devices=[make_bt_device()], deferred=deferred)
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    _click_row(lcd, "EV-1-WL")
    _, on_done = deferred.pop()
    on_done(error)
    rendered = lcd.pstack.current
    assert not isinstance(rendered, Menu), "a failure must raise a dialog over the menu"


def test_pair_failure_snapshot(v3_system, bluetooth_state, snapshot):
    deferred: list = []
    bluetooth_state(devices=[make_bt_device()], deferred=deferred)
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    _click_row(lcd, "EV-1-WL")
    _, on_done = deferred.pop()
    on_done(Exception("org.bluez.Error.AuthenticationFailed: no"))
    snapshot("pair_failed_dialog")


# ----- modal safety -----


def test_status_change_does_not_close_an_open_dialog(v3_system, bluetooth_state):
    """A PropertiesChanged burst mid-dialog must not yank it out from under
    the user — bluez pushes these constantly while scanning."""
    deferred: list = []
    mgr = bluetooth_state(devices=[make_bt_device()], deferred=deferred)
    lcd = _open(v3_system)
    _click_row(lcd, "Nearby devices")
    _click_row(lcd, "EV-1-WL")
    _, on_done = deferred.pop()
    on_done(Exception("org.bluez.Error.AuthenticationFailed: no"))
    dialog = lcd.pstack.current
    assert not isinstance(dialog, Menu)

    mgr.devices.return_value = [make_bt_device(rssi=-40), make_bt_device(name="New Thing", address="AA:BB:CC:DD:EE:01")]
    lcd.bluetooth_menu.notify_status_change()
    assert lcd.pstack.current is dialog


def test_rssi_jitter_does_not_rebuild_the_menu(v3_system, bluetooth_state):
    """BT RSSI is noisier than wifi's; only a change in the drawn bar count
    may cost the user their cursor position."""
    mgr = bluetooth_state(devices=[make_bt_device(paired=True)], known=[make_bt_known()])
    lcd = _open(v3_system)
    menu = lcd.pstack.current
    mgr.devices.return_value = [make_bt_device(paired=True, rssi=-53)]
    lcd.bluetooth_menu.notify_status_change()
    assert lcd.pstack.current is menu


def test_bar_count_change_does_rebuild(v3_system, bluetooth_state):
    mgr = bluetooth_state(devices=[make_bt_device(paired=True, rssi=-95)], known=[make_bt_known()])
    lcd = _open(v3_system)
    menu = lcd.pstack.current
    mgr.devices.return_value = [make_bt_device(paired=True, rssi=-30)]
    lcd.bluetooth_menu.notify_status_change()
    assert lcd.pstack.current is not menu


# ----- wifi menu integration -----


def test_wifi_menu_hides_bluetooth_button_without_hardware(v3_system, bluetooth_state, wifi_state):
    """Pi 3/4 give the BT UART to DIN MIDI. No adapter, no mention anywhere."""
    wifi_state()
    bluetooth_state(supported=False)
    lcd = v3_system.handler._lcd
    lcd.wifi_menu.open()
    menu = lcd.pstack.current
    assert not any("Bluetooth" in label for label in _footer_labels(menu))


def test_wifi_menu_footer_counts_connected_devices(v3_system, bluetooth_state, wifi_state):
    wifi_state()
    bluetooth_state(devices=[make_bt_device(paired=True, connected=True)], known=[make_bt_known()])
    lcd = v3_system.handler._lcd
    lcd.wifi_menu.open()
    labels = _footer_labels(lcd.pstack.current)
    assert labels == ["Close", "Bluetooth (1)..."]


def test_wifi_menu_footer_without_connection(v3_system, bluetooth_state, wifi_state, snapshot):
    """Radio present, nothing connected — the button carries no count."""
    wifi_state(
        scanned=[make_scanned("HomeWifi", signal=78, in_use=True), make_scanned("StudioNet", signal=61)],
        saved=[make_saved("HomeWifi"), make_saved("StudioNet")],
        active="HomeWifi",
    )
    bluetooth_state(devices=[], known=[make_bt_known()])
    lcd = v3_system.handler._lcd
    lcd.wifi_menu.open()
    labels = _footer_labels(lcd.pstack.current)
    assert labels == ["Close", "Bluetooth..."]
    snapshot("wifi_bt_none_connected")


def test_wifi_menu_many_saved_with_bluetooth_connected(v3_system, bluetooth_state, wifi_state, snapshot):
    """The layout under real load: several saved networks plus a live BT device."""
    saved = [
        make_saved("HomeWifi"),
        make_saved("StudioNet"),
        make_saved("CoffeeShop"),
        make_saved("Backline Guest"),
    ]
    scanned = [
        make_scanned("HomeWifi", signal=78, in_use=True),
        make_scanned("StudioNet", signal=61),
        make_scanned("CoffeeShop", signal=44),
    ]
    wifi_state(scanned=scanned, saved=saved, active="HomeWifi")
    bluetooth_state(devices=[make_bt_device(paired=True, connected=True)], known=[make_bt_known()])
    lcd = v3_system.handler._lcd
    lcd.wifi_menu.open()
    snapshot("wifi_many_saved_bt_connected")
