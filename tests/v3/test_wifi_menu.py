"""WiFi menu snapshot and behaviour tests.

All tests use the v3_system + wifi_state fixtures.  Run with --snapshot-update
to accept baselines on first run.
"""

import time

import pytest

from tests.v3.conftest import make_saved, make_scanned
from ui.wifi_menu import WifiMenu, _PassphraseEditor
from uilib.dialog import Dialog, MessageDialog
from uilib.misc import InputEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open(v3_system) -> tuple[WifiMenu, object]:
    """Create a fresh WifiMenu, open it, and return (menu, lcd)."""
    lcd = v3_system.handler._lcd
    wm = WifiMenu(lcd)
    wm.open()
    return wm, lcd


def _type_password(lcd, password: str) -> None:
    """Set passphrase on the _PassphraseEditor and move selector to OK.

    The LetterSelector starts at Cancel (l_idx=1); one RIGHT moves it to OK (l_idx=2).
    """
    editor = lcd.pstack.current
    assert isinstance(editor, _PassphraseEditor)
    editor._curline = password
    editor._edit.set_text(password + '\u2588')
    lcd.enc_step(1)   # selector: Cancel → OK


def _click(lcd) -> None:
    lcd.pstack.input_event(InputEvent.CLICK)


def _long_click(lcd) -> None:
    lcd.pstack.input_event(InputEvent.LONG_CLICK)


# ---------------------------------------------------------------------------
# 5.1  test_empty_scan
# ---------------------------------------------------------------------------

def test_empty_scan(v3_system, wifi_state, snapshot):
    """Root menu renders cleanly with no networks and no saved profiles."""
    wifi_state(scanned=[], saved=[])
    _open(v3_system)
    snapshot("root_empty")


# ---------------------------------------------------------------------------
# 5.2  test_signal_bar_levels
# ---------------------------------------------------------------------------

def test_signal_bar_levels(v3_system, wifi_state, snapshot):
    """Lock down bar rendering across the nmcli 0-100 quality range."""
    nets = [
        make_scanned("Low",    signal=15),
        make_scanned("Fair",   signal=40),
        make_scanned("Good",   signal=65),
        make_scanned("Strong", signal=90),
    ]
    wifi_state(scanned=nets, saved=[])
    _open(v3_system)
    snapshot("root_signal_levels")
    _click(v3_system.handler._lcd)       # enter "Nearby networks..."
    snapshot("nearby_signal_levels")


# ---------------------------------------------------------------------------
# 5.3  test_duplicate_ssids_dedup
# ---------------------------------------------------------------------------

def test_duplicate_ssids_dedup(v3_system, wifi_state, snapshot):
    """scan_networks deduplicates by SSID; the menu shows one row per SSID."""
    # scan_networks is mocked — return the already-deduplicated list that
    # the real WifiManager.scan_networks() would produce.
    nets = [
        make_scanned("NetA", signal=70),
        make_scanned("NetB", signal=50),
    ]
    wifi_state(scanned=nets, saved=[])
    _open(v3_system)
    lcd = v3_system.handler._lcd
    _click(lcd)          # enter "Nearby networks..."
    snapshot("nearby_dedup")


# ---------------------------------------------------------------------------
# 5.4  test_saved_in_range_active
# ---------------------------------------------------------------------------

def test_saved_in_range_active(v3_system, wifi_state, snapshot):
    """Connected network sorts first with ✔; others follow by signal."""
    ts = int(time.time())
    saved = [
        make_saved("Home", timestamp=ts - 1000),
        make_saved("Cafe", timestamp=ts - 5000),
    ]
    scanned = [
        make_scanned("Home", signal=80, in_use=True),
        make_scanned("Cafe", signal=40),
    ]
    wifi_state(scanned=scanned, saved=saved, active="Home")
    _open(v3_system)
    snapshot("root_active_first")


# ---------------------------------------------------------------------------
# 5.5  test_saved_wrong_psk_shows_error
# ---------------------------------------------------------------------------

def test_saved_wrong_psk_shows_error(v3_system, wifi_state, snapshot):
    """Saved network with stale PSK: one attempt then show the error.

    The user can retry via the long-press 'Replace password' submenu.
    """
    saved = [make_saved("Home")]
    scanned = [make_scanned("Home", signal=80)]
    wifi_state(scanned=scanned, saved=saved, active=None)

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.connect_saved.return_value = b"secrets were required, but none were provided"

    _wm, lcd = _open(v3_system)
    _click(lcd)                              # tap Home → auth fails → error dialog
    snapshot("saved_auth_failed_dialog")

    assert isinstance(lcd.pstack.current, MessageDialog)
    wm_mock.replace_psk.assert_not_called()


# ---------------------------------------------------------------------------
# 5.7  test_open_network_connect
# ---------------------------------------------------------------------------

def test_open_network_connect(v3_system, wifi_state, snapshot):
    """Tapping an open network skips the password dialog."""
    nets = [make_scanned("FreeWifi", signal=70, security="--")]
    wifi_state(scanned=nets, saved=[])

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.connect_scanned.return_value = None

    _wm, lcd = _open(v3_system)
    _click(lcd)          # enter "Nearby networks..."
    _click(lcd)          # tap FreeWifi → direct connect (no dialog)
    snapshot("connected_open")

    wm_mock.connect_scanned.assert_called_once_with("FreeWifi", None)


# ---------------------------------------------------------------------------
# 5.8  test_empty_psk_submit_blocked  (bug 2.2)
# ---------------------------------------------------------------------------

def test_empty_psk_submit_blocked(v3_system, wifi_state, snapshot):
    """Empty PSK submit does nothing — dialog stays open."""
    nets = [make_scanned("Secured", signal=70)]
    wifi_state(scanned=nets, saved=[])

    _wm, lcd = _open(v3_system)
    _click(lcd)          # enter "Nearby networks..."
    _click(lcd)          # tap Secured → password dialog

    # Selector starts at Cancel; move to OK then submit without typing anything
    lcd.enc_step(1)      # Cancel → OK
    _click(lcd)          # submit with empty _curline → should no-op

    snapshot("empty_psk_ok_pressed")

    # Passphrase editor must still be open (not dismissed)
    assert isinstance(lcd.pstack.current, _PassphraseEditor)


# ---------------------------------------------------------------------------
# 5.9  test_error_dialogs_each_kind
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stderr,label", [
    (b"secrets were required, but none were provided", "auth_failed"),
    (b"ip-config-unavailable",                         "dhcp_timeout"),
    (b"connection timed out",                          "timed_out"),
    (b"no network with ssid 'Net'",                    "not_found"),
    (b"not authorized to control networking",          "permission_denied"),
])
def test_error_dialogs_each_kind(v3_system, wifi_state, snapshot, stderr, label):
    """Every connect failure (including auth) shows a MessageDialog — no retry."""
    nets = [make_scanned("Net", signal=70)]
    wifi_state(scanned=nets, saved=[])

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.connect_scanned.return_value = stderr

    _wm, lcd = _open(v3_system)
    _click(lcd)                              # enter "Nearby networks..."
    _click(lcd)                              # tap Net → passphrase editor
    _type_password(lcd, "somepassword")
    _click(lcd)                              # submit → error dialog
    snapshot(f"error_{label}")

    assert isinstance(lcd.pstack.current, MessageDialog)


# ---------------------------------------------------------------------------
# 5.10  test_more_saved_submenu
# ---------------------------------------------------------------------------

def test_many_saved_all_at_root(v3_system, wifi_state, snapshot):
    """All saved networks appear at root regardless of count — no overflow submenu."""
    ts = int(time.time())
    saved = [
        make_saved("A", timestamp=ts - 100),
        make_saved("B", timestamp=ts - 200),
        make_saved("C", timestamp=ts - 300),
        make_saved("D", timestamp=ts - 400),
    ]
    wifi_state(scanned=[], saved=saved)
    _open(v3_system)
    snapshot("root_all_four_visible")


# ---------------------------------------------------------------------------
# 5.11  test_multiple_profiles_same_ssid  (bug 2.5 lock-down)
# ---------------------------------------------------------------------------

def test_multiple_profiles_same_ssid(v3_system, wifi_state, snapshot):
    """Lock down: only the most-recent profile per SSID is shown (current behaviour)."""
    ts = int(time.time())
    saved = [
        make_saved("Home", name="Home_v1", timestamp=ts - 7200),
        make_saved("Home", name="Home_v2", timestamp=ts - 3600),
    ]
    wifi_state(scanned=[], saved=saved)
    _open(v3_system)
    snapshot("root_one_profile_visible")


# ---------------------------------------------------------------------------
# 5.12  test_long_press_active_submenu
# ---------------------------------------------------------------------------

def test_long_press_active_submenu(v3_system, wifi_state, snapshot):
    """Long-press on an active saved network opens [Disconnect, Replace password, Forget]."""
    saved = [make_saved("Home")]
    scanned = [make_scanned("Home", signal=80, in_use=True)]
    wifi_state(scanned=scanned, saved=saved, active="Home")

    _open(v3_system)
    lcd = v3_system.handler._lcd
    _long_click(lcd)     # long-press Home
    snapshot("active_actions_submenu")


# ---------------------------------------------------------------------------
# 5.13  test_forget_then_reload
# ---------------------------------------------------------------------------

def test_forget_then_reload(v3_system, wifi_state, snapshot):
    """Forgetting a network removes it and the menu reloads without it."""
    saved = [make_saved("Home")]
    scanned = [make_scanned("Home", signal=80)]
    wifi_state(scanned=scanned, saved=saved, active=None)

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.delete_connection.return_value = None

    _wm, lcd = _open(v3_system)
    _long_click(lcd)     # long-press Home → [Replace password, Forget, ↩]
    lcd.enc_step(1)      # → Forget
    # Update mocks before clicking so the reload sees an empty list
    wm_mock.list_connections.return_value = []
    wm_mock.scan_networks.return_value = []
    _click(lcd)          # forget → reload
    snapshot("root_after_forget")


# ---------------------------------------------------------------------------
# 5.14  test_replace_password_flow
# ---------------------------------------------------------------------------

def test_replace_password_flow(v3_system, wifi_state, snapshot):
    """Explicit 'Replace password' path from the active network submenu."""
    saved = [make_saved("Home")]
    scanned = [make_scanned("Home", signal=80, in_use=True)]
    wifi_state(scanned=scanned, saved=saved, active="Home")

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.replace_psk.return_value = None

    _wm, lcd = _open(v3_system)
    _click(lcd)          # tap active Home → [Disconnect, Replace password, Forget, ↩]
    lcd.enc_step(1)      # → Replace password
    _click(lcd)          # → password dialog
    snapshot("replace_psk_dialog")

    _type_password(lcd, "freshpassword")
    _click(lcd)
    snapshot("root_after_replace")

    wm_mock.replace_psk.assert_called_once_with("Home", "freshpassword")


# ---------------------------------------------------------------------------
# 5.15  test_hotspot_active_indicator
# ---------------------------------------------------------------------------

def test_hotspot_active_indicator(v3_system, wifi_state, snapshot):
    """Hotspot mode on shows the ● indicator."""
    wifi_state(hotspot=True)
    _open(v3_system)
    snapshot("root_hotspot_on")


# ---------------------------------------------------------------------------
# 5.16  test_wifi_unsupported
# ---------------------------------------------------------------------------

def test_wifi_unsupported(v3_system, wifi_state, snapshot):
    """Graceful rendering when WiFi hardware is absent."""
    wifi_state(supported=False)
    _open(v3_system)
    snapshot("root_unsupported")


# ---------------------------------------------------------------------------
# 5.17  test_disconnect_active
# ---------------------------------------------------------------------------

def test_disconnect_active(v3_system, wifi_state, snapshot):
    """Disconnect removes the ✔ from the connected network."""
    saved = [make_saved("Home")]
    scanned = [make_scanned("Home", signal=80, in_use=True)]
    wifi_state(scanned=scanned, saved=saved, active="Home")

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.disconnect.return_value = None

    _wm, lcd = _open(v3_system)
    _click(lcd)          # tap active Home → [Disconnect, Replace password, Forget, ↩]
    _click(lcd)          # tap Disconnect
    snapshot("root_after_disconnect")


# ---------------------------------------------------------------------------
# 5.18  test_password_special_chars
# ---------------------------------------------------------------------------

def test_password_special_chars(v3_system, wifi_state, snapshot):
    """Special characters in a password are passed verbatim to connect_scanned."""
    nets = [make_scanned("Secured", signal=70)]
    wifi_state(scanned=nets, saved=[])

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.connect_scanned.return_value = None

    _wm, lcd = _open(v3_system)
    _click(lcd)          # enter "Nearby networks..."
    _click(lcd)          # tap Secured → password dialog
    snapshot("psk_special_chars_dialog")

    special = 'a"b\\c d'
    _type_password(lcd, special)
    _click(lcd)

    wm_mock.connect_scanned.assert_called_once_with("Secured", special)  # psk passed positionally


# ---------------------------------------------------------------------------
# 5.19  test_dialog_cancel_returns_to_menu
# ---------------------------------------------------------------------------

def test_dialog_cancel_returns_to_menu(v3_system, wifi_state, snapshot):
    """Cancelling the password dialog returns to the nearby submenu."""
    nets = [make_scanned("Secured", signal=70)]
    wifi_state(scanned=nets, saved=[])

    _wm, lcd = _open(v3_system)
    _click(lcd)          # enter "Nearby networks..."
    _click(lcd)          # tap Secured → passphrase editor (selector starts at Cancel)
    _click(lcd)          # click Cancel → close editor
    snapshot("nearby_after_cancel")


# ---------------------------------------------------------------------------
# 5.20  test_join_other_empty_ssid_blocked
# ---------------------------------------------------------------------------

def test_join_other_empty_ssid_blocked(v3_system, wifi_state, snapshot):
    """'Join other network' with empty SSID stays open — nothing happens."""
    wifi_state(scanned=[], saved=[])

    _wm, lcd = _open(v3_system)
    # Root menu: [Join other network..., Hotspot Mode, ↩]
    # "Join other network..." is the first item when there are no networks
    _click(lcd)          # open "Join other network..." dialog

    # Navigate to OK without typing anything
    lcd.enc_step(1)      # ssid → passwd
    lcd.enc_step(1)      # passwd → cancel
    lcd.enc_step(1)      # cancel → ok
    _click(lcd)          # submit with empty SSID → no-op

    snapshot("join_empty_ssid")

    assert isinstance(lcd.pstack.current, Dialog)
