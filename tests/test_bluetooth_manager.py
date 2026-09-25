"""Bluetooth ops/manager tests. The filter-predicate cases are pure functions
with no fixture — they encode what a live scan actually returned on a Pi 5."""

import asyncio
import time
from unittest.mock import patch

import pytest
from dbus_fast import DBusError

from modalapi.bluetooth import DeviceKind, device_kind, is_interesting, parse_bluez_error
from modalapi.bluetooth import bluez
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
        (
            "org.bluez.Error.ConnectionAttemptFailed: br-connection-page-timeout",
            "couldn't connect — is it still in pairing mode?",
        ),
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


def test_has_adapter_false_when_no_hci_node_is_registered(tmp_path):
    """An empty sysfs dir — a board whose controller never attached. Not the
    Pi 3/4 case: they give Bluetooth the mini UART and do register hci0."""
    assert has_adapter(str(tmp_path)) is False


def test_has_adapter_false_when_directory_is_absent():
    assert has_adapter("/nonexistent/sysfs/path") is False

# ----- ghost eviction: stale unpaired devices must vanish -----


def _msg(interface, member, body, path=""):
    """A bare dbus_fast Message shaped like a bluez signal."""
    from dbus_fast import Message, MessageType

    return Message(
        message_type=MessageType.SIGNAL,
        interface=interface,
        member=member,
        path=path,
        body=body,
    )


def _client_with_ghost():
    """A BluezClient whose adapter is up and whose device table holds one
    unpaired device. The device object stays in the table — that's what
    bluez does mid-discovery after the device has gone dark — but the
    snapshot must stop listing it once it is stale."""
    client = bluez.BluezClient()
    with client._lock:
        client._adapter_path = "/org/bluez/hci0"
        client._devices["/org/bluez/hci0/dev_X"] = {
            "Address": "AA:BB:CC:DD:EE:FF",
            "Name": "Ghost Pedal",
            "UUIDs": [MIDI_UUID],
            "Paired": False,
            "Connected": False,
        }
    return client


def test_stale_unpaired_device_is_withheld_from_snapshot():
    client = _client_with_ghost()
    client._seen["/org/bluez/hci0/dev_X"] = time.monotonic() - bluez._STALE_AFTER_S - 1
    assert client.snapshot() == []


def test_fresh_unpaired_device_stays_in_snapshot():
    client = _client_with_ghost()
    client._seen["/org/bluez/hci0/dev_X"] = time.monotonic()
    assert [d["name"] for d in client.snapshot()] == ["Ghost Pedal"]


def test_paired_device_never_goes_stale():
    """A bonded device idle with discovery off doesn't advertise either —
    staleness must not mark it absent and cost the user their connect row."""
    client = _client_with_ghost()
    with client._lock:
        client._devices["/org/bluez/hci0/dev_X"]["Paired"] = True
    client._seen["/org/bluez/hci0/dev_X"] = time.monotonic() - bluez._STALE_AFTER_S * 10
    assert [d["name"] for d in client.snapshot()] == ["Ghost Pedal"]


def test_connected_device_never_goes_stale():
    client = _client_with_ghost()
    with client._lock:
        client._devices["/org/bluez/hci0/dev_X"]["Connected"] = True
    client._seen["/org/bluez/hci0/dev_X"] = time.monotonic() - bluez._STALE_AFTER_S * 10
    assert [d["name"] for d in client.snapshot()] == ["Ghost Pedal"]


def test_rssi_change_refreshes_the_heartbeat():
    """PropertiesChanged carrying RSSI is the advertisement heartbeat; the
    same signal without RSSI (e.g. a ServicesResolved flip) must not."""
    client = _client_with_ghost()
    path = "/org/bluez/hci0/dev_X"
    old = time.monotonic() - bluez._STALE_AFTER_S - 1
    client._seen[path] = old
    client._on_signal(_msg("org.freedesktop.DBus.Properties", "PropertiesChanged", ["org.bluez.Device1", {"RSSI": -50}], path=path))
    assert client._seen[path] > old
    assert [d["name"] for d in client.snapshot()] == ["Ghost Pedal"]


def test_non_rssi_change_does_not_refresh_the_heartbeat():
    client = _client_with_ghost()
    path = "/org/bluez/hci0/dev_X"
    client._seen[path] = time.monotonic() - bluez._STALE_AFTER_S - 1
    client._on_signal(
        _msg("org.freedesktop.DBus.Properties", "PropertiesChanged", ["org.bluez.Device1", {"ServicesResolved": True}], path=path)
    )
    assert client.snapshot() == []


def test_interfaces_added_marks_device_fresh():
    client = _client_with_ghost()
    client._seen["/org/bluez/hci0/dev_X"] = time.monotonic() - bluez._STALE_AFTER_S - 1
    client._on_signal(
        _msg(
            "org.freedesktop.DBus.ObjectManager",
            "InterfacesAdded",
            ["/org/bluez/hci0/dev_X", {"org.bluez.Device1": {"Name": "Ghost Pedal", "UUIDs": [MIDI_UUID]}}],
            path="/org/bluez/hci0",
        )
    )
    assert [d["name"] for d in client.snapshot()] == ["Ghost Pedal"]


def test_interfaces_removed_clears_the_heartbeat():
    client = _client_with_ghost()
    path = "/org/bluez/hci0/dev_X"
    client._seen[path] = time.monotonic()
    client._on_signal(
        _msg("org.freedesktop.DBus.ObjectManager", "InterfacesRemoved", [path, ["org.bluez.Device1"]], path="/org/bluez/hci0")
    )
    assert client.snapshot() == []
    assert path not in client._seen


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


# ----- Busy retry -----


class _FlakyAdapter:
    """Answers Busy for the first `busy_times` calls, as a bluetoothd that is
    still initialising does."""

    def __init__(self, busy_times: int, error: str = "org.bluez.Error.Busy"):
        self.busy_times = busy_times
        self.calls = 0
        self.error = error

    async def set_adapter_property(self, name, value):
        self.calls += 1
        if self.calls <= self.busy_times:
            raise DBusError(self.error, self.error)


def _run_set_flag(adapter):
    with patch.object(ops.asyncio, "sleep", new=_no_sleep):
        return asyncio.run(ops._set_adapter_flag(adapter, "Powered"))


async def _no_sleep(_seconds):
    return None


def test_busy_is_retried_until_it_succeeds():
    adapter = _FlakyAdapter(busy_times=3)
    _run_set_flag(adapter)
    assert adapter.calls == 4


def test_busy_gives_up_after_the_retry_cap():
    adapter = _FlakyAdapter(busy_times=ops._BUSY_RETRIES + 1)
    with pytest.raises(DBusError):
        _run_set_flag(adapter)
    assert adapter.calls == ops._BUSY_RETRIES + 1


def test_non_busy_errors_are_not_retried():
    adapter = _FlakyAdapter(busy_times=1, error="org.bluez.Error.NotReady")
    with pytest.raises(DBusError):
        _run_set_flag(adapter)
    assert adapter.calls == 1


# ----- enable/disable owns the radio, not just the daemon -----


class _FakeClient:
    """Records the order of everything set_enabled does to the adapter."""

    def __init__(self, log, available=True):
        self._log = log
        self.available = available
        self.powered = True

    def call(self, coro):
        # Log the verb the manager handed us, so on/off cases read differently.
        name = getattr(coro, "__name__", "adapter_call")
        coro.close()  # never awaited in this fake
        self._log.append(name)

    def stop(self, join=True):
        self._log.append("client.stop")

    def start(self, on_change=None):
        self._log.append("client.start")
        return True


def _disable_with_fakes(manager, client_available=True):
    log = []
    manager.client = _FakeClient(log, available=client_available)
    with (
        patch.object(ops, "power_off", lambda c: _named_coro("power_off")),
        patch.object(ops, "disable_service", lambda: log.append("disable_service")),
        patch.object(ops, "rfkill_set_blocked", lambda b: log.append("rfkill_block" if b else "rfkill_unblock")),
    ):
        assert manager.set_enabled(False) is None
    return log


def _named_coro(name):
    """A throwaway coroutine whose __name__ the fake client logs."""

    async def _c():
        return None

    _c.__name__ = name
    return _c()


def test_disable_powers_the_radio_off_before_the_daemon_goes_away(manager):
    """The adapter's D-Bus object disappears with bluetoothd, so a power-off
    issued after stop/disable silently does nothing and the radio stays up."""
    log = _disable_with_fakes(manager)
    assert log == ["power_off", "client.stop", "disable_service", "rfkill_block"]


def test_disable_still_blocks_the_radio_when_dbus_is_unavailable(manager):
    """No bluez connection means no D-Bus power-off; the rfkill block is the
    guarantee."""
    log = _disable_with_fakes(manager, client_available=False)
    assert log == ["client.stop", "disable_service", "rfkill_block"]


def test_disable_reports_the_error_and_does_not_block_when_the_unit_fails(manager):
    log = []
    manager.client = _FakeClient(log)
    with (
        patch.object(ops, "power_off", lambda c: _named_coro("power_off")),
        patch.object(ops, "disable_service", lambda: "Failed to disable unit"),
        patch.object(ops, "rfkill_set_blocked", lambda b: log.append("rfkill")),
    ):
        assert manager.set_enabled(False) == "Failed to disable unit"
    assert "rfkill" not in log
    assert manager._enabled is False


def test_enable_unblocks_the_radio_before_starting_the_unit(manager):
    """The adapter boots soft-blocked; starting bluetoothd against a blocked
    radio leaves it off-blocked."""
    log = []
    manager.client = _FakeClient(log)
    with (
        patch.object(ops, "power_on", lambda c: _named_coro("power_on")),
        patch.object(ops, "enable_service", lambda: log.append("enable_service")),
        patch.object(ops, "rfkill_set_blocked", lambda b: log.append("rfkill_block" if b else "rfkill_unblock")),
    ):
        assert manager.set_enabled(True) is None
    assert log == ["rfkill_unblock", "enable_service", "client.start", "power_on"]
    assert "rfkill_block" not in log
