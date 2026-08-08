"""Bluetooth ops/manager tests. The filter-predicate cases are pure functions
with no fixture — they encode what a live scan actually returned on a Pi 5."""

from unittest.mock import patch

import pytest

from modalapi.bluetooth import DeviceKind, device_kind, is_interesting, parse_bluez_error
from modalapi.bluetooth import manager as manager_mod
from modalapi.bluetooth import ops
from modalapi.bluetooth.manager import BluetoothManager, has_adapter

MIDI_UUID = "03B80E5A-EDE8-4B33-A751-6CE34EC4C700"
HOG_UUID = "00001812-0000-1000-8000-00805f9b34fb"


# ----- filter predicate -----


def test_midi_device_is_midi():
    props = {"Name": "EV-1-WL", "UUIDs": [MIDI_UUID]}
    assert is_interesting(props)
    assert device_kind(props) is DeviceKind.MIDI


def test_hid_over_gatt_is_input():
    props = {"Name": "R400 Presenter", "UUIDs": [HOG_UUID]}
    assert is_interesting(props)
    assert device_kind(props) is DeviceKind.INPUT


def test_nameless_beacon_is_filtered_out():
    """BlueZ fills Alias with a MAC-derived string, so Alias is always truthy.
    Testing Name is the only thing that keeps beacons out of the list."""
    assert not is_interesting({"Alias": "D4-06-0F-EE-16-83", "RSSI": -80})


def test_named_but_uninteresting_is_filtered_out():
    assert not is_interesting({"Name": "Fitbit Charge", "UUIDs": ["0000180d-0000-1000-8000-00805f9b34fb"]})


def test_paired_device_always_shows_even_without_a_name():
    assert is_interesting({"Paired": True, "Alias": "AA-BB-CC-DD-EE-FF"})


def test_peripheral_major_class_is_input():
    assert device_kind({"Name": "Keyboard", "Class": 0x000540}) is DeviceKind.INPUT


def test_appearance_hid_range_is_input():
    assert device_kind({"Name": "Mouse", "Appearance": 0x03C2}) is DeviceKind.INPUT


def test_midi_wins_over_hid_when_a_device_advertises_both():
    assert device_kind({"Name": "Both", "UUIDs": [MIDI_UUID, HOG_UUID]}) is DeviceKind.MIDI


# ----- error mapping -----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("org.bluez.Error.AuthenticationFailed: x", "pairing failed"),
        ("org.bluez.Error.ConnectionAttemptFailed: br-connection-page-timeout", "couldn't connect — is it still in pairing mode?"),
        ("org.bluez.Error.NotAvailable: no", "the device is no longer in range"),
        ("something InProgress happened", "already connecting"),
    ],
)
def test_parse_bluez_error(raw, expected):
    assert parse_bluez_error(Exception(raw)) == expected


# ----- capability probe -----


@pytest.mark.parametrize(
    "exec_start,capable",
    [
        ("{ path=/usr/libexec/bluetooth/bluetoothd ; argv[]=/usr/libexec/bluetooth/bluetoothd -E ; }", True),
        ("{ path=/usr/libexec/bluetooth/bluetoothd ; argv[]=/usr/libexec/bluetooth/bluetoothd ; }", False),
        ("argv[]=/usr/libexec/bluetooth/bluetoothd --experimental", True),
        ("argv[]=/usr/libexec/bluetooth/bluetoothd -nE", True),
        # A long option that merely contains E must not read as the short flag.
        ("argv[]=/usr/libexec/bluetooth/bluetoothd --nodetach --EXPERIMENTAL-NOPE", False),
    ],
)
def test_has_experimental_flag(exec_start, capable):
    assert ops.has_experimental_flag(exec_start) is capable


def test_bluetoothd_is_capable_false_when_systemctl_fails():
    with patch.object(ops, "_run", return_value=(1, "not found")):
        assert ops.bluetoothd_is_capable() is False


# ----- adapter presence -----


def test_has_adapter_true_when_hci_node_exists(tmp_path):
    (tmp_path / "hci0").mkdir()
    assert has_adapter(str(tmp_path)) is True


def test_has_adapter_false_on_pi3_pi4(tmp_path):
    """dtoverlay=pi3-disable-bt hands the UART to DIN MIDI, so the directory
    exists but registers no hci device."""
    assert has_adapter(str(tmp_path)) is False


def test_has_adapter_false_when_directory_is_absent():
    assert has_adapter("/nonexistent/sysfs/path") is False


# ----- known-device store -----


class _FakeSettings:
    def __init__(self):
        self.data = {}

    def get_setting(self, name):
        return self.data.get(name)

    def set_setting(self, name, value):
        self.data[name] = value


@pytest.fixture
def manager():
    """A BluetoothManager with the startup probe stubbed out — no D-Bus, no
    systemctl, no threads reaching the network."""
    with patch.object(manager_mod.BluetoothManager, "_startup", lambda self: None):
        mgr = BluetoothManager(settings=_FakeSettings())
    yield mgr
    mgr.shutdown()


def _device(address="AA:BB:CC:DD:EE:FF", name="EV-1-WL", kind=DeviceKind.MIDI):
    return {
        "path": "/org/bluez/hci0/dev_x",
        "address": address,
        "name": name,
        "kind": kind,
        "paired": True,
        "connected": True,
        "trusted": True,
        "rssi": -50,
    }


def test_remember_then_read_back(manager):
    manager.remember(_device())
    known = manager.known_devices()
    assert [(k["address"], k["name"], k["kind"]) for k in known] == [("AA:BB:CC:DD:EE:FF", "EV-1-WL", "midi")]


def test_remember_is_idempotent_for_the_same_device(manager):
    manager.remember(_device())
    manager.remember(_device())
    assert len(manager.known_devices()) == 1


def test_rotated_private_address_under_a_known_name_is_the_same_device(manager):
    """BLE resolvable private addresses re-randomise; keying on MAC alone would
    accumulate a duplicate row every time the device reappears."""
    manager.remember(_device(address="74:9F:EF:44:A6:99"))
    manager.remember(_device(address="55:4F:14:89:F7:5F"))
    known = manager.known_devices()
    assert len(known) == 1
    assert known[0]["address"] == "55:4F:14:89:F7:5F"


def test_forget_removes_the_entry(manager):
    manager.remember(_device())
    manager.forget("AA:BB:CC:DD:EE:FF", "EV-1-WL")
    assert manager.known_devices() == []


def test_known_devices_survives_a_garbage_setting(manager):
    manager.settings.set_setting("bluetooth.known_devices", "not a list")
    assert manager.known_devices() == []


def test_unsupported_manager_reports_no_devices(manager):
    """No adapter → the menu row never appears at all."""
    manager._has_adapter = False
    assert manager.supported is False
    assert manager.devices() == []
