# pyright: reportAttributeAccessIssue=false
"""Unit tests for WifiManager — orchestration around nmcli / systemctl.

These tests mock `subprocess` and don't construct a polling thread; they
exercise the manager API directly.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from modalapi.wifi import WifiManager


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
    # Terse nmcli output with the new field set: NAME,TYPE,TIMESTAMP,SSID,MODE
    stdout = (
        "Home:802-11-wireless:1700000000:Home:infrastructure\n"
        "pistomp-hotspot:802-11-wireless:0:pistomp:ap\n"
        "Hotspot:802-11-wireless:0:pistomp:ap\n"
        "Cafe:802-11-wireless:1699000000:Cafe:infrastructure\n"
        "eth0:802-3-ethernet:1700000000::\n"
    )
    result = MagicMock(stdout=stdout, returncode=0)
    with patch("subprocess.run", return_value=result):
        conns = wm.list_connections()

    ssids = [c["ssid"] for c in conns]
    assert ssids == ["Home", "Cafe"]


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
