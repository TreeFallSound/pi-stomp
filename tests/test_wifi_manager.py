# pyright: reportAttributeAccessIssue=false
"""Unit tests for WifiManager — orchestration around nmcli.

These tests mock `subprocess` and don't construct a polling thread; they
exercise the manager API directly. Hotspot mode is driven directly via
nmcli.
"""

from unittest.mock import MagicMock, patch

import pytest

from modalapi.wifi import KeyMgmt, WifiManager
from modalapi.wifi import ops


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
        "NAME",
        "UUID",
        "TYPE",
        "TIMESTAMP",
        "TIMESTAMP-REAL",
        "AUTOCONNECT",
        "AUTOCONNECT-PRIORITY",
        "READONLY",
        "DBUS-PATH",
        "ACTIVE",
        "DEVICE",
        "STATE",
        "ACTIVE-PATH",
        "SLAVE",
        "FILENAME",
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
# disable_hotspot — nmcli orchestration: down AP + reconnect saved
# ---------------------------------------------------------------------------


def _hotspot_run(run_calls, *, hotspot_name="pistomp-hotspot"):
    """side_effect for subprocess.run that:
    - returns an AP-mode profile from `connection show` listing
    - reports mode=ap for that profile's per-uuid lookup
    - returns success for every other nmcli call
    """
    bulk = f"{hotspot_name}:uuid-hs:802-11-wireless:0\n"

    def _eff(cmd, **kw):
        run_calls.append(list(cmd))
        # Per-uuid mode lookup
        if "show" in cmd and "uuid-hs" in cmd:
            return MagicMock(stdout="802-11-wireless.ssid:pistomp\n802-11-wireless.mode:ap\n", stderr="", returncode=0)
        # Bulk list (`nmcli -t -f NAME,UUID,TYPE connection show`)
        if "connection" in cmd and "show" in cmd and "-f" in cmd:
            f_idx = cmd.index("-f")
            fields = cmd[f_idx + 1]
            if "NAME" in fields and "TYPE" in fields and "TIMESTAMP" not in fields:
                return MagicMock(stdout=bulk, stderr="", returncode=0)
        return MagicMock(stdout="", stderr="", returncode=0)

    return _eff


def test_disable_hotspot_returns_none_on_clean_reconnect(wm):
    """Happy path: AP profile is brought down, most-recent saved profile activates."""
    saved = [
        {"name": "Cafe", "ssid": "Cafe", "timestamp": 1699000000},
        {"name": "Home", "ssid": "Home", "timestamp": 1700000000},  # most recent
    ]
    run_calls: list[list[str]] = []
    with (
        patch.object(ops, "list_connections", return_value=saved),
        patch("subprocess.run", side_effect=_hotspot_run(run_calls)),
    ):
        err = wm.disable_hotspot()

    assert err is None
    # AP brought down explicitly via nmcli (no systemctl).
    assert any("connection" in c and "down" in c and "pistomp-hotspot" in c for c in run_calls), (
        f"expected nmcli connection down pistomp-hotspot, got: {run_calls}"
    )
    assert not any("systemctl" in c for c in run_calls), "disable_hotspot must not call systemctl"
    assert any("connection" in c and "up" in c and "Home" in c for c in run_calls), (
        f"expected nmcli connection up Home, got: {run_calls}"
    )


def test_disable_hotspot_returns_none_when_no_saved_profile(wm):
    """No saved client profile → bring AP down silently, no reconnect attempt."""
    run_calls: list[list[str]] = []
    with (
        patch("modalapi.wifi.ops.list_connections", return_value=[]),
        patch("subprocess.run", side_effect=_hotspot_run(run_calls)),
    ):
        err = wm.disable_hotspot()

    assert err is None
    assert any("connection" in c and "down" in c and "pistomp-hotspot" in c for c in run_calls)
    assert not any("connection" in c and "up" in c for c in run_calls), "no saved profile → no `connection up` call"


def test_disable_hotspot_uses_nmcli_wait_zero(wm):
    """Reconnect must be fire-and-forget — UI shouldn't block on DHCP."""
    saved = [{"name": "Home", "ssid": "Home", "timestamp": 1700000000}]
    run_calls: list[list[str]] = []
    with (
        patch.object(ops, "list_connections", return_value=saved),
        patch("subprocess.run", side_effect=_hotspot_run(run_calls)),
    ):
        wm.disable_hotspot()

    up_calls = [c for c in run_calls if "up" in c and "Home" in c]
    assert up_calls, f"expected an nmcli connection up call, got: {run_calls}"
    args = up_calls[0]
    assert "--wait" in args and args[args.index("--wait") + 1] == "0", f"expected --wait 0, got: {args}"


def test_disable_hotspot_when_no_ap_profile_exists(wm):
    """If no AP-mode profile is found, skip the `down` call and just try to
    reactivate the most-recent saved client profile."""
    saved = [{"name": "Home", "ssid": "Home", "timestamp": 1700000000}]
    run_calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        run_calls.append(list(cmd))
        # Empty connection-show listing → no hotspot profile found.
        return MagicMock(stdout="", stderr="", returncode=0)

    with (
        patch.object(ops, "list_connections", return_value=saved),
        patch("subprocess.run", side_effect=fake_run),
    ):
        err = wm.disable_hotspot()

    assert err is None
    assert not any("down" in c for c in run_calls), "no AP profile → no `connection down` call"
    assert any("up" in c and "Home" in c for c in run_calls)


def test_enable_hotspot_creates_profile_when_missing(wm):
    """If no AP-mode profile exists, enable_hotspot creates `pistomp-hotspot`
    with WPA-PSK + shared IPv4, then activates it. No systemctl."""
    run_calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        run_calls.append(list(cmd))
        # Bulk listing returns no profiles → triggers creation path.
        return MagicMock(stdout="", stderr="", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        err = wm.enable_hotspot()

    assert err is None
    assert not any("systemctl" in c for c in run_calls)
    add = next((c for c in run_calls if "add" in c and "pistomp-hotspot" in c), None)
    assert add is not None, f"expected `connection add pistomp-hotspot`, got: {run_calls}"
    assert "ap" in add and "ipv4.method" in add and "shared" in add
    assert "wifi-sec.psk" in add and "pistompwifi" in add
    up = next((c for c in run_calls if "up" in c and "pistomp-hotspot" in c), None)
    assert up is not None, f"expected `connection up pistomp-hotspot`, got: {run_calls}"


def test_enable_hotspot_reuses_existing_ap_profile(wm):
    """If an AP-mode profile already exists (any name), don't recreate it."""
    run_calls: list[list[str]] = []
    with patch("subprocess.run", side_effect=_hotspot_run(run_calls, hotspot_name="Hotspot")):
        err = wm.enable_hotspot()

    assert err is None
    assert not any("add" in c for c in run_calls), f"existing AP profile must be reused, not recreated: {run_calls}"
    assert any("up" in c and "Hotspot" in c for c in run_calls)


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
        patch.object(
            wm,
            "_get_wpa_status",
            side_effect=lambda s: s.update(ssid="Home", ip4_address="10.0.0.2", hotspot_active=False),
        ),
        patch.object(ops, "list_connections", return_value=saved),
        patch.object(wm.stop, "wait", side_effect=stop_after_first),
    ):
        WifiManager._polling_thread(wm)

    assert wm._cached_saved == saved
    assert wm.last_status.get("wifi_connected") is True
    assert wm.last_status.get("ssid") == "Home"
    assert wm.last_status.get("ip4_address") == "10.0.0.2"
    assert wm.last_status.get("hotspot_active") is False
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
        patch.object(ops, "list_connections") as list_conns,
        patch.object(wm.stop, "wait", side_effect=stop_after_first),
    ):
        WifiManager._polling_thread(wm)
        list_conns.assert_not_called()

    assert wm._cached_saved == []


def test_disable_hotspot_returns_error_when_reconnect_fails(wm):
    """If `nmcli connection up <saved>` fails, propagate the stderr bytes.

    The AP-`down` call must still succeed for this path to be reached, so we
    differentiate by argv: succeed on `down`/`show`, fail on `up`."""
    saved = [{"name": "Home", "ssid": "Home", "timestamp": 1700000000}]

    def fake_run(cmd, **kw):
        # AP profile lookup → return a hotspot row + AP mode.
        if "show" in cmd and "uuid-hs" in cmd:
            return MagicMock(stdout="802-11-wireless.ssid:pistomp\n802-11-wireless.mode:ap\n", stderr="", returncode=0)
        if "connection" in cmd and "show" in cmd and "-f" in cmd:
            return MagicMock(stdout="pistomp-hotspot:uuid-hs:802-11-wireless:0\n", stderr="", returncode=0)
        if "up" in cmd and "Home" in cmd:
            return MagicMock(stdout="", stderr="no network with ssid 'Home'", returncode=1)
        return MagicMock(stdout="", stderr="", returncode=0)

    with (
        patch.object(ops, "list_connections", return_value=saved),
        patch("subprocess.run", side_effect=fake_run),
    ):
        err = wm.disable_hotspot()

    assert err == b"no network with ssid 'Home'"


# ---------------------------------------------------------------------------
# KeyMgmt — mapping from `nmcli dev wifi list` SECURITY column
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "security,expected",
    [
        ("", KeyMgmt.NONE),
        ("--", KeyMgmt.NONE),
        ("WPA2", KeyMgmt.WPA_PSK),
        ("WPA1 WPA2", KeyMgmt.WPA_PSK),
        ("WPA2 802.1X", KeyMgmt.WPA_EAP),  # enterprise wins over PSK keyword
        ("WPA3", KeyMgmt.SAE),
        ("WPA2 WPA3", KeyMgmt.SAE),  # presence of SAE means it's available
        ("SAE", KeyMgmt.SAE),
        ("802.1X", KeyMgmt.WPA_EAP),
    ],
)
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


def _ok_run(calls):
    """side_effect for subprocess.run that records argv and returns success."""

    def _eff(cmd, **kw):
        calls.append(list(cmd))
        return MagicMock(stdout="", stderr="", returncode=0)

    return _eff


def test_connect_scanned_wpa2_passes_explicit_key_mgmt(wm):
    calls: list[list[str]] = []
    with (
        patch.object(wm, "list_connections", return_value=[]),
        patch("subprocess.run", side_effect=_ok_run(calls)),
    ):
        err = wm.connect_scanned("BELL592", "WPA2", "secret")

    assert err is None
    add = next(c for c in calls if "add" in c)
    assert "wifi-sec.key-mgmt" in add and "wpa-psk" in add
    assert "wifi-sec.psk" in add and "secret" in add


def test_connect_scanned_open_omits_security_fields(wm):
    calls: list[list[str]] = []
    with (
        patch.object(wm, "list_connections", return_value=[]),
        patch("subprocess.run", side_effect=_ok_run(calls)),
    ):
        err = wm.connect_scanned("Cafe", "", None)

    assert err is None
    add = next(c for c in calls if "add" in c)
    # nmcli treats wifi-sec.key-mgmt=none as WEP, breaking association with
    # genuinely open APs. The wifi-sec section must be omitted entirely.
    assert "wifi-sec.psk" not in add
    assert "wifi-sec.key-mgmt" not in add


def test_connect_scanned_wpa3_uses_sae(wm):
    calls: list[list[str]] = []
    with (
        patch.object(wm, "list_connections", return_value=[]),
        patch("subprocess.run", side_effect=_ok_run(calls)),
    ):
        wm.connect_scanned("Net3", "WPA3", "secret")

    add = next(c for c in calls if "add" in c)
    assert "sae" in add


def test_connect_scanned_deletes_only_freshly_added_profile_on_failure(wm):
    """If `connection up` fails, we delete the profile *we just added* — not
    any pre-existing sibling profile that happens to share the SSID."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if "up" in cmd:
            return MagicMock(stdout="", stderr="auth failed", returncode=1)
        return MagicMock(stdout="", stderr="", returncode=0)

    saved = [{"name": "preconfigured", "ssid": "BELL592", "timestamp": 1}]
    with (
        patch.object(wm, "list_connections", return_value=saved),
        patch("subprocess.run", side_effect=fake_run),
    ):
        err = wm.connect_scanned("BELL592", "WPA2", "wrongpw")

    assert err == b"auth failed"
    delete_calls = [c for c in calls if "delete" in c]
    assert len(delete_calls) == 1
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
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return MagicMock(stdout="GENERAL.STATE:activated\n", stderr="", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        err = wm.connect_saved("preconfigured")

    assert err is None
    assert not any("up" in c for c in calls), f"expected no `nmcli connection up`, got: {calls}"


def test_connect_saved_runs_when_not_activated(wm):
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        # _is_profile_activated: empty state. Then `connection up`: success.
        return MagicMock(stdout="GENERAL.STATE:\n", stderr="", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        err = wm.connect_saved("Home")

    assert err is None
    assert any("up" in c and "Home" in c for c in calls)


def test_connect_saved_reconnect_bypasses_idempotency_check(wm):
    """replace_psk path: even if the profile is already activated, the caller
    can demand a cycle so a freshly-modified setting (PSK) takes effect."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return MagicMock(stdout="GENERAL.STATE:activated\n", stderr="", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        wm.connect_saved("Home", reconnect=True)

    assert any("up" in c and "Home" in c for c in calls)


def test_replace_psk_uses_reconnect(wm):
    """After modifying a PSK we must cycle the active link, not skip-via-idempotency."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        # get_psk_for: returns old psk; _is_profile_activated: activated; everything else: ok
        if "802-11-wireless-security.psk" in cmd and "-s" in cmd:
            return MagicMock(stdout="802-11-wireless-security.psk:oldpw\n", stderr="", returncode=0)
        return MagicMock(stdout="GENERAL.STATE:activated\n", stderr="", returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        err = wm.replace_psk("Home", "newpw")

    assert err is None
    assert any("up" in c and "Home" in c for c in calls), (
        f"replace_psk must trigger `connection up` to cycle the new PSK; got: {calls}"
    )
