# pyright: reportAttributeAccessIssue=false
"""Unit tests for WifiManager — orchestration around nmcli / systemctl.

These tests mock `subprocess` and don't construct a polling thread; they
exercise the manager API directly.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from modalapi.wifi import KeyMgmt, WifiManager


@pytest.fixture
def wm() -> WifiManager:
    """A WifiManager with the polling thread suppressed."""
    with patch.object(WifiManager, "_polling_thread", lambda self: None):
        return WifiManager(ifname="wlan0")


# ---------------------------------------------------------------------------
# list_connections — filter AP-mode profiles regardless of name
# ---------------------------------------------------------------------------

def test_list_connections_filters_ap_mode_profile(wm):
    """Hotspot profiles (mode=ap) are excluded even when named differently.

    Covers both images: arch (`pistomp-hotspot`) and pi-gen (`Hotspot`).
    """
    bulk_stdout = (
        "Home:uuid-home:802-11-wireless:1700000000\n"
        "pistomp-hotspot:uuid-pshot:802-11-wireless:0\n"
        "Hotspot:uuid-hshot:802-11-wireless:0\n"
        "Cafe:uuid-cafe:802-11-wireless:1699000000\n"
        "eth0:uuid-eth:802-3-ethernet:1700000000\n"
    )
    per_uuid = {
        "uuid-home": "802-11-wireless.ssid:Home\n802-11-wireless.mode:infrastructure\n",
        "uuid-pshot": "802-11-wireless.ssid:pistomp\n802-11-wireless.mode:ap\n",
        "uuid-hshot": "802-11-wireless.ssid:pistomp\n802-11-wireless.mode:ap\n",
        "uuid-cafe": "802-11-wireless.ssid:Cafe\n802-11-wireless.mode:infrastructure\n",
    }

    def fake_run(cmd, **kw):
        if "show" in cmd and len(cmd) == 6:  # bulk: nmcli -t -f ... connection show
            return MagicMock(stdout=bulk_stdout, stderr="", returncode=0)
        uuid = cmd[-1]
        return MagicMock(stdout=per_uuid.get(uuid, ""), stderr="", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        conns = wm.list_connections()

    ssids = [c["ssid"] for c in conns]
    assert ssids == ["Home", "Cafe"]


def test_list_connections_bulk_call_uses_only_valid_columns(wm):
    """Regression: NM 1.42+ rejects per-setting fields like 802-11-wireless.ssid
    in bulk `connection show -f`. Only the list-column names are valid."""
    BULK_VALID = {
        "NAME", "UUID", "TYPE", "TIMESTAMP", "TIMESTAMP-REAL", "AUTOCONNECT",
        "AUTOCONNECT-PRIORITY", "READONLY", "DBUS-PATH", "ACTIVE", "DEVICE",
        "STATE", "ACTIVE-PATH", "SLAVE", "FILENAME",
    }
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return MagicMock(stdout="", stderr="", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        wm.list_connections()

    bulk = next(c for c in calls if "connection" in c and "show" in c and len(c) == 6)
    f_idx = bulk.index("-f")
    fields = bulk[f_idx + 1].split(",")
    invalid = [f for f in fields if f not in BULK_VALID]
    assert not invalid, f"bulk `connection show -f` rejects these fields: {invalid}"


# ---------------------------------------------------------------------------
# disable_hotspot — synchronous orchestration: stop service + reconnect
# ---------------------------------------------------------------------------

def test_disable_hotspot_returns_none_on_clean_reconnect(wm):
    """Happy path: systemctl stops, most-recent saved profile activates."""
    saved = [
        {"name": "Cafe", "ssid": "Cafe", "timestamp": 1699000000},
        {"name": "Home", "ssid": "Home", "timestamp": 1700000000},  # most recent
    ]
    with (
        patch.object(wm, "list_connections", return_value=saved),
        patch("subprocess.check_output") as co,
    ):
        co.return_value = b""
        err = wm.disable_hotspot()

    assert err is None
    # First call: systemctl disable --now wifi-hotspot
    # Second call: nmcli connection up Home
    calls = [c.args[0] for c in co.call_args_list]
    assert any("systemctl" in args and "wifi-hotspot" in args for args in calls)
    assert any(
        "nmcli" in args and "up" in args and "Home" in args for args in calls
    ), f"expected nmcli connection up Home, got: {calls}"


def test_disable_hotspot_returns_none_when_no_saved_profile(wm):
    """No saved profile → stop service silently, no reconnect attempt."""
    with (
        patch.object(wm, "list_connections", return_value=[]),
        patch("subprocess.check_output") as co,
    ):
        co.return_value = b""
        err = wm.disable_hotspot()

    assert err is None
    calls = [c.args[0] for c in co.call_args_list]
    # systemctl must have been called; nmcli connection up must NOT.
    assert any("systemctl" in args for args in calls)
    assert not any("nmcli" in args and "up" in args for args in calls)


def test_disable_hotspot_uses_nmcli_wait_zero(wm):
    """Reconnect must be fire-and-forget — UI shouldn't block on DHCP."""
    saved = [{"name": "Home", "ssid": "Home", "timestamp": 1700000000}]
    with (
        patch.object(wm, "list_connections", return_value=saved),
        patch("subprocess.check_output") as co,
    ):
        co.return_value = b""
        wm.disable_hotspot()

    nmcli_calls = [c.args[0] for c in co.call_args_list if "nmcli" in c.args[0]]
    assert nmcli_calls, "expected an nmcli call"
    args = nmcli_calls[0]
    assert "--wait" in args and args[args.index("--wait") + 1] == "0", \
        f"expected --wait 0, got: {args}"


# ---------------------------------------------------------------------------
# poll() — bridges the polling thread to on_status_change on the main thread
# ---------------------------------------------------------------------------

def test_poll_fires_callback_only_when_changed_flag_set():
    """poll() invokes on_status_change with the cached snapshot when changed=True,
    then clears the flag. Subsequent polls with no new updates are no-ops."""
    calls: list = []
    with patch.object(WifiManager, "_polling_thread", lambda self: None):
        wm = WifiManager(ifname="wlan0", on_status_change=calls.append)

    snapshot = {"wifi_supported": True, "wifi_connected": True, "hotspot_active": False}
    with wm.lock:
        wm.last_status = snapshot
        wm.changed = True

    wm.poll()
    assert calls == [snapshot]
    assert wm.changed is False

    # Second poll with no new change: callback must not fire again.
    wm.poll()
    assert calls == [snapshot]


def test_poll_noop_when_callback_unset():
    """poll() must not raise when on_status_change is None, even with changed=True."""
    with patch.object(WifiManager, "_polling_thread", lambda self: None):
        wm = WifiManager(ifname="wlan0", on_status_change=None)
    with wm.lock:
        wm.last_status = {"wifi_connected": True}
        wm.changed = True

    wm.poll()
    assert wm.changed is False


# ---------------------------------------------------------------------------
# _polling_thread — refreshes _cached_saved alongside last_status
# ---------------------------------------------------------------------------

def test_polling_thread_iteration_refreshes_status_and_saved():
    """One iteration of the polling-thread body updates both last_status and
    _cached_saved under the lock, and sets `changed` when status differs."""
    saved = [{"name": "Home", "ssid": "Home", "timestamp": 1700000000}]

    with patch.object(WifiManager, "_polling_thread", lambda self: None):
        wm = WifiManager(ifname="wlan0")

    # Stop the loop after a single pass.
    original_wait = wm.stop.wait
    def stop_after_first(_timeout):
        wm.stop.set()
        return original_wait(0)

    with (
        patch.object(wm, "_is_wifi_supported", return_value=True),
        patch.object(wm, "_is_wifi_connected", return_value=True),
        patch.object(wm, "_is_hotspot_active", return_value=False),
        patch.object(wm, "_get_wpa_status",
                     side_effect=lambda s: s.update(ssid="Home", ip4_address="10.0.0.2")),
        patch.object(wm, "list_connections", return_value=saved),
        patch.object(wm.stop, "wait", side_effect=stop_after_first),
    ):
        WifiManager._polling_thread(wm)

    assert wm._cached_saved == saved
    assert wm.last_status.get("wifi_connected") is True
    assert wm.last_status.get("ssid") == "Home"
    assert wm.last_status.get("ip4_address") == "10.0.0.2"
    assert wm.changed is True


def test_polling_thread_skips_saved_when_wifi_unsupported():
    """When wifi isn't supported, the polling thread must not call
    list_connections (no nmcli on the box) and _cached_saved stays empty."""
    with patch.object(WifiManager, "_polling_thread", lambda self: None):
        wm = WifiManager(ifname="wlan0")

    def stop_after_first(_timeout):
        wm.stop.set()
        return True

    with (
        patch.object(wm, "_is_wifi_supported", return_value=False),
        patch.object(wm, "_is_wifi_connected", return_value=False),
        patch.object(wm, "_is_hotspot_active", return_value=False),
        patch.object(wm, "list_connections") as list_conns,
        patch.object(wm.stop, "wait", side_effect=stop_after_first),
    ):
        WifiManager._polling_thread(wm)
        list_conns.assert_not_called()

    assert wm._cached_saved == []


def test_disable_hotspot_returns_error_when_reconnect_fails(wm):
    """If `nmcli connection up <saved>` fails, propagate the stderr bytes."""
    saved = [{"name": "Home", "ssid": "Home", "timestamp": 1700000000}]

    def fake_check_output(cmd, **kwargs):
        if "systemctl" in cmd:
            return b""
        # nmcli connection up — fail
        raise subprocess.CalledProcessError(1, cmd, output=b"no network with ssid 'Home'")

    with (
        patch.object(wm, "list_connections", return_value=saved),
        patch("subprocess.check_output", side_effect=fake_check_output),
    ):
        err = wm.disable_hotspot()

    assert err == b"no network with ssid 'Home'"


# ---------------------------------------------------------------------------
# KeyMgmt — mapping from `nmcli dev wifi list` SECURITY column
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("security,expected", [
    ("", KeyMgmt.NONE),
    ("--", KeyMgmt.NONE),
    ("WPA2", KeyMgmt.WPA_PSK),
    ("WPA1 WPA2", KeyMgmt.WPA_PSK),
    ("WPA2 802.1X", KeyMgmt.WPA_EAP),  # enterprise wins over PSK keyword
    ("WPA3", KeyMgmt.SAE),
    ("WPA2 WPA3", KeyMgmt.SAE),  # presence of SAE means it's available
    ("SAE", KeyMgmt.SAE),
    ("802.1X", KeyMgmt.WPA_EAP),
])
def test_keymgmt_from_scan_security(security, expected):
    assert KeyMgmt.from_scan_security(security) is expected


@pytest.mark.parametrize("security", ["WEP", "garbage", "OWE"])
def test_keymgmt_from_scan_security_unsupported(security):
    with pytest.raises(ValueError):
        KeyMgmt.from_scan_security(security)


def test_keymgmt_is_str_compatible():
    """str-Enum: instances must drop into subprocess args as their value string."""
    assert KeyMgmt.WPA_PSK == "wpa-psk"
    assert ["wifi-sec.key-mgmt", KeyMgmt.SAE][1] == "sae"


# ---------------------------------------------------------------------------
# connect_scanned — explicit key-mgmt, scoped failure cleanup
# ---------------------------------------------------------------------------

def test_connect_scanned_wpa2_passes_explicit_key_mgmt(wm):
    calls: list[list[str]] = []

    def fake_check_output(cmd, **kw):
        calls.append(list(cmd))
        return b""

    with (
        patch.object(wm, "list_connections", return_value=[]),
        patch("subprocess.check_output", side_effect=fake_check_output),
    ):
        err = wm.connect_scanned("BELL592", "WPA2", "secret")

    assert err is None
    add = next(c for c in calls if "add" in c)
    assert "wifi-sec.key-mgmt" in add and "wpa-psk" in add
    assert "wifi-sec.psk" in add and "secret" in add


def test_connect_scanned_open_omits_security_fields(wm):
    calls: list[list[str]] = []

    def fake_check_output(cmd, **kw):
        calls.append(list(cmd))
        return b""

    with (
        patch.object(wm, "list_connections", return_value=[]),
        patch("subprocess.check_output", side_effect=fake_check_output),
    ):
        err = wm.connect_scanned("Cafe", "", None)

    assert err is None
    add = next(c for c in calls if "add" in c)
    assert "wifi-sec.psk" not in add
    # key-mgmt=none is acceptable; what matters is no psk leaks in
    if "wifi-sec.key-mgmt" in add:
        assert "wpa-psk" not in add and "sae" not in add


def test_connect_scanned_wpa3_uses_sae(wm):
    calls: list[list[str]] = []

    with (
        patch.object(wm, "list_connections", return_value=[]),
        patch("subprocess.check_output", side_effect=lambda c, **kw: calls.append(list(c)) or b""),
    ):
        wm.connect_scanned("Net3", "WPA3", "secret")

    add = next(c for c in calls if "add" in c)
    assert "sae" in add


def test_connect_scanned_deletes_only_freshly_added_profile_on_failure(wm):
    """If `connection up` fails, we delete the profile *we just added* — not
    any pre-existing sibling profile that happens to share the SSID."""
    calls: list[list[str]] = []

    def fake_check_output(cmd, **kw):
        calls.append(list(cmd))
        if "up" in cmd:
            raise subprocess.CalledProcessError(1, cmd, output=b"auth failed")
        return b""

    # `preconfigured` already exists with SSID BELL592 — must not be touched.
    saved = [{"name": "preconfigured", "ssid": "BELL592", "timestamp": 1}]
    with (
        patch.object(wm, "list_connections", return_value=saved),
        patch("subprocess.check_output", side_effect=fake_check_output),
    ):
        err = wm.connect_scanned("BELL592", "WPA2", "wrongpw")

    assert err == b"auth failed"
    delete_calls = [c for c in calls if "delete" in c]
    assert len(delete_calls) == 1
    # We deleted the profile we just created — never the pre-existing `preconfigured`.
    deleted_name = delete_calls[0][-1]
    assert deleted_name == "BELL592"
    assert "preconfigured" not in delete_calls[0]


def test_connect_scanned_requires_psk_for_secured_network(wm):
    with patch.object(wm, "list_connections", return_value=[]):
        err = wm.connect_scanned("BELL592", "WPA2", None)
    assert err is not None and b"password" in err


def test_connect_scanned_rejects_enterprise(wm):
    with patch.object(wm, "list_connections", return_value=[]):
        err = wm.connect_scanned("CorpNet", "WPA2 802.1X", "x")
    assert err is not None and b"enterprise" in err.lower()


# ---------------------------------------------------------------------------
# connect_saved — idempotent when already activated
# ---------------------------------------------------------------------------

def test_connect_saved_skips_nmcli_when_already_activated(wm):
    """Tapping a saved row that's already active must not invoke `nmcli
    connection up` (which would tear down and re-cycle, ~14s on real NM)."""
    co_calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        return MagicMock(stdout="GENERAL.STATE:activated\n", stderr="", returncode=0)

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("subprocess.check_output", side_effect=lambda c, **kw: co_calls.append(list(c)) or b""),
    ):
        err = wm.connect_saved("preconfigured")

    assert err is None
    assert not any("up" in c for c in co_calls), \
        f"expected no `nmcli connection up`, got: {co_calls}"


def test_connect_saved_runs_when_not_activated(wm):
    co_calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        # Inactive profile: nmcli returns empty GENERAL.STATE
        return MagicMock(stdout="GENERAL.STATE:\n", stderr="", returncode=0)

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("subprocess.check_output", side_effect=lambda c, **kw: co_calls.append(list(c)) or b""),
    ):
        err = wm.connect_saved("Home")

    assert err is None
    assert any("up" in c and "Home" in c for c in co_calls)


def test_connect_saved_reconnect_bypasses_idempotency_check(wm):
    """replace_psk path: even if the profile is already activated, the caller
    can demand a cycle so a freshly-modified setting (PSK) takes effect."""
    co_calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        return MagicMock(stdout="GENERAL.STATE:activated\n", stderr="", returncode=0)

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("subprocess.check_output", side_effect=lambda c, **kw: co_calls.append(list(c)) or b""),
    ):
        wm.connect_saved("Home", reconnect=True)

    assert any("up" in c and "Home" in c for c in co_calls)


def test_replace_psk_uses_reconnect(wm):
    """After modifying a PSK we must cycle the active link, not skip-via-idempotency."""
    calls: list[list[str]] = []

    def fake_check_output(cmd, **kw):
        calls.append(list(cmd))
        return b""

    def fake_run(cmd, **kw):
        # get_psk_for (returncode irrelevant for our assertions) + _is_profile_activated
        if "show" in cmd and "-g" in cmd:
            return MagicMock(stdout="oldpw\n", returncode=0)
        return MagicMock(stdout="GENERAL.STATE:activated\n", stderr="", returncode=0)

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("subprocess.check_output", side_effect=fake_check_output),
    ):
        err = wm.replace_psk("Home", "newpw")

    assert err is None
    assert any("up" in c and "Home" in c for c in calls), \
        f"replace_psk must trigger `connection up` to cycle the new PSK; got: {calls}"
