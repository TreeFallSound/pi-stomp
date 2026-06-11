"""WiFi menu snapshot and behaviour tests.

All tests use the v3_system + wifi_state fixtures.  Run with --snapshot-update
to accept baselines on first run.
"""

import time

import pytest

from tests.v3.conftest import make_saved, make_scanned
from ui.wifi_menu import Row, WifiMenu, _PassphraseEditor
from uilib.dialog import Dialog, MessageDialog
from uilib.misc import InputEvent
from uilib.text import LetterSelector, TextEditor, TextWidget
from pistomp.lcd320x240 import Lcd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open(v3_system) -> tuple[WifiMenu, Lcd]:
    """Create a fresh WifiMenu, open it, and return (menu, lcd).

    The wifi_state fixture installs an inline CommandQueue shim, so
    submit/submit_scan callbacks fire synchronously.
    """
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
    editor._edit.set_text(password + "\u2588")
    lcd.enc_step(1)  # selector: Cancel → OK


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


def test_nearby_loading_then_populated(v3_system, wifi_state, snapshot):
    """Saga: open wifi → tap Nearby networks (empty / 'Scanning...') → scan returns → list populates."""
    wifi_state(scanned=[], saved=[])
    wm_mock = v3_system.handler.wifi_manager

    # Defer scan callbacks instead of firing inline.
    pending: list = []

    def _defer(cmd, on_done):
        pending.append((cmd, on_done))
        return True

    wm_mock.queue.submit_scan.side_effect = _defer

    wm, lcd = _open(v3_system)
    snapshot("root_before_scan")

    # Tap "Nearby networks..." (first menu item).
    _click(lcd)
    snapshot("nearby_scanning")

    # Scan returns with two networks.
    wm_mock.scan_networks.return_value = [
        make_scanned("Alpha", signal=80),
        make_scanned("Bravo", signal=40),
    ]
    for cmd, on_done in pending:
        on_done(cmd.run(wm_mock))
    snapshot("nearby_populated")


# ---------------------------------------------------------------------------
# 5.2  test_signal_bar_levels
# ---------------------------------------------------------------------------


def test_signal_bar_levels(v3_system, wifi_state, snapshot):
    """Lock down bar rendering across the nmcli 0-100 quality range."""
    nets = [
        make_scanned("Low", signal=15),
        make_scanned("Fair", signal=40),
        make_scanned("Good", signal=65),
        make_scanned("Strong", signal=90),
    ]
    wifi_state(scanned=nets, saved=[])
    _open(v3_system)
    snapshot("root_signal_levels")
    _click(v3_system.handler._lcd)  # enter "Nearby networks..."
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
    _click(lcd)  # enter "Nearby networks..."
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
    _click(lcd)  # tap Home → auth fails → error dialog
    snapshot("saved_auth_failed_dialog")

    assert isinstance(lcd.pstack.current, MessageDialog)
    wm_mock.replace_psk.assert_not_called()


def test_open_network_badge_in_nearby_list(v3_system, wifi_state, snapshot):
    """Unsaved open networks render the public-network pill badge in the nearby submenu."""
    nets = [
        make_scanned("FreeWifi", signal=80, security="--"),
        make_scanned("Secured", signal=50, security="WPA2"),
    ]
    wifi_state(scanned=nets, saved=[])
    _wm, lcd = _open(v3_system)
    _click(lcd)  # enter "Nearby networks..."
    snapshot("nearby_with_open_badge")


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
    _click(lcd)  # enter "Nearby networks..."
    _click(lcd)  # tap FreeWifi → direct connect (no dialog)
    snapshot("connected_open")

    wm_mock.connect_scanned.assert_called_once_with("FreeWifi", "--", None)


# ---------------------------------------------------------------------------
# 5.8  test_empty_psk_submit_blocked  (bug 2.2)
# ---------------------------------------------------------------------------


def test_empty_psk_submit_blocked(v3_system, wifi_state, snapshot):
    """Empty PSK submit does nothing — dialog stays open."""
    nets = [make_scanned("Secured", signal=70)]
    wifi_state(scanned=nets, saved=[])

    _wm, lcd = _open(v3_system)
    _click(lcd)  # enter "Nearby networks..."
    _click(lcd)  # tap Secured → password dialog

    # Selector starts at Cancel; move to OK then submit without typing anything
    lcd.enc_step(1)  # Cancel → OK
    _click(lcd)  # submit with empty _curline → should no-op

    snapshot("empty_psk_ok_pressed")

    # Passphrase editor must still be open (not dismissed)
    assert isinstance(lcd.pstack.current, _PassphraseEditor)


# ---------------------------------------------------------------------------
# 5.9  test_error_dialogs_each_kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stderr",
    [
        b"secrets were required, but none were provided",
        b"ip-config-unavailable",
        b"connection timed out",
        b"no network with ssid 'Net'",
        b"not authorized to control networking",
    ],
)
def test_error_dialogs_each_kind(v3_system, wifi_state, stderr):
    """Every connect failure shows a MessageDialog — no retry."""
    nets = [make_scanned("Net", signal=70)]
    wifi_state(scanned=nets, saved=[])

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.connect_scanned.return_value = stderr

    _wm, lcd = _open(v3_system)
    _click(lcd)  # enter "Nearby networks..."
    _click(lcd)  # tap Net → passphrase editor
    _type_password(lcd, "somepassword")
    _click(lcd)  # submit → error dialog

    assert isinstance(lcd.pstack.current, MessageDialog)


def test_error_dialog_snapshot(v3_system, wifi_state, snapshot):
    """Auth failure error dialog — one snapshot covers the shared visual layout."""
    nets = [make_scanned("Net", signal=70)]
    wifi_state(scanned=nets, saved=[])
    v3_system.handler.wifi_manager.connect_scanned.return_value = b"secrets were required, but none were provided"

    _wm, lcd = _open(v3_system)
    _click(lcd)
    _click(lcd)
    _type_password(lcd, "somepassword")
    _click(lcd)
    snapshot("error_dialog")


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
    """When several saved profiles share an SSID, rows surface the profile name
    so users can distinguish them (e.g. OEM `preconfigured` vs user-added)."""
    ts = int(time.time())
    saved = [
        make_saved("Home", name="Home_v1", timestamp=ts - 7200),
        make_saved("Home", name="Home_v2", timestamp=ts - 3600),
    ]
    wifi_state(scanned=[], saved=saved)
    _open(v3_system)
    snapshot("root_disambiguated_by_name")


def test_multiple_profiles_same_ssid_name_without_ssid():
    """If a profile name doesn't contain the SSID (e.g. the OEM 'preconfigured'),
    append the SSID in parens for clarity."""
    from ui.wifi_menu import WifiMenu

    ts = int(time.time())
    profiles = [
        make_saved("BELL592", name="preconfigured", timestamp=ts - 1000),
        make_saved("BELL592", name="BELL592", timestamp=ts),
    ]
    rows = []
    for p in profiles:
        row: Row = {"ssid": "BELL592", "signal": None, "security": None, "saved": True, "profile": p, "active": False}
        WifiMenu._maybe_disambiguate(row, profiles)
        rows.append(row)

    assert rows[0].get("display_name") == "preconfigured (BELL592)"
    assert rows[1].get("display_name") == "BELL592"


def test_disambiguate_skipped_when_single_profile():
    """Single saved profile for an SSID: no disambiguator (show plain SSID)."""
    from ui.wifi_menu import WifiMenu

    profile = make_saved("Home", name="anything", timestamp=1)
    row: Row = {"ssid": "Home", "signal": None, "security": None, "saved": True, "profile": profile, "active": False}
    WifiMenu._maybe_disambiguate(row, [profile])
    assert "display_name" not in row


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
    _long_click(lcd)  # long-press Home
    snapshot("active_actions_submenu")


# ---------------------------------------------------------------------------
# 5.13  test_forget_then_reload
# ---------------------------------------------------------------------------


def test_forget_active_falls_back_to_best_saved(v3_system, wifi_state, snapshot):
    """Saga: forget the active network → auto-connect to strongest saved+in-range fallback."""
    saved = [make_saved("Home"), make_saved("Cafe")]
    scanned = [
        make_scanned("Home", signal=80, in_use=True),
        make_scanned("Cafe", signal=60),
    ]
    wifi_state(scanned=scanned, saved=saved, active="Home")
    wm_mock = v3_system.handler.wifi_manager
    wm_mock.delete_connection.return_value = None
    wm_mock.connect_saved.return_value = None

    _wm, lcd = _open(v3_system)
    snapshot("root_before_forget")
    _click(lcd)  # Home is selected and active → submenu [Disconnect, Replace password, Forget, ↩]
    lcd.enc_step(1)  # Disconnect → Replace password
    lcd.enc_step(1)  # → Forget
    # Post-forget state: Home gone, Cafe now active (the fallback connected to it).
    wm_mock.list_connections.return_value = [make_saved("Cafe")]
    wm_mock.get_cached_saved.return_value = [make_saved("Cafe")]
    wm_mock.scan_networks.return_value = [make_scanned("Cafe", signal=60, in_use=True)]
    v3_system.handler.wifi_status = {
        "wifi_supported": True,
        "wifi_connected": True,
        "hotspot_active": False,
        "ssid": "Cafe",
        "connection": "Cafe",
    }
    _click(lcd)  # confirm Forget
    snapshot("root_after_fallback")

    # ConnectSavedCmd must have been submitted for the strongest fallback (Cafe).
    cmds = [call.args[0] for call in wm_mock.queue.submit.call_args_list]
    connect_calls = [c for c in cmds if type(c).__name__ == "ConnectSavedCmd"]
    assert connect_calls, "Forget on active network must auto-connect to a fallback"
    assert connect_calls[0].ssid == "Cafe"


def test_forget_active_no_fallback_when_only_out_of_range(v3_system, wifi_state):
    """If the only other saved profile is out of range, no auto-connect."""
    saved = [make_saved("Home"), make_saved("Faraway")]
    scanned = [make_scanned("Home", signal=80, in_use=True)]  # Faraway not visible
    wifi_state(scanned=scanned, saved=saved, active="Home")
    wm_mock = v3_system.handler.wifi_manager
    wm_mock.delete_connection.return_value = None

    _wm, lcd = _open(v3_system)
    _click(lcd)  # Home submenu
    lcd.enc_step(1)
    lcd.enc_step(1)  # → Forget
    wm_mock.list_connections.return_value = [make_saved("Faraway")]
    wm_mock.get_cached_saved.return_value = [make_saved("Faraway")]
    wm_mock.scan_networks.return_value = []
    _click(lcd)

    cmds = [call.args[0] for call in wm_mock.queue.submit.call_args_list]
    assert not [c for c in cmds if type(c).__name__ == "ConnectSavedCmd"]


def test_forget_inactive_does_not_auto_connect(v3_system, wifi_state):
    """Forgetting a non-active saved profile must not trigger any auto-connect."""
    saved = [make_saved("Home"), make_saved("Cafe")]
    scanned = [
        make_scanned("Home", signal=80, in_use=True),
        make_scanned("Cafe", signal=60),
    ]
    wifi_state(scanned=scanned, saved=saved, active="Home")
    wm_mock = v3_system.handler.wifi_manager
    wm_mock.delete_connection.return_value = None

    _wm, lcd = _open(v3_system)
    lcd.enc_step(1)  # Home → Cafe (inactive)
    _long_click(lcd)  # Cafe submenu [Replace password, Forget, ↩]
    lcd.enc_step(1)  # → Forget
    wm_mock.list_connections.return_value = [make_saved("Home")]
    wm_mock.get_cached_saved.return_value = [make_saved("Home")]
    wm_mock.scan_networks.return_value = scanned
    _click(lcd)

    cmds = [call.args[0] for call in wm_mock.queue.submit.call_args_list]
    assert not [c for c in cmds if type(c).__name__ == "ConnectSavedCmd"]


def test_forget_then_reload(v3_system, wifi_state, snapshot):
    """Forgetting a network removes it and the menu reloads without it."""
    saved = [make_saved("Home")]
    scanned = [make_scanned("Home", signal=80)]
    wifi_state(scanned=scanned, saved=saved, active=None)

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.delete_connection.return_value = None

    _wm, lcd = _open(v3_system)
    _long_click(lcd)  # long-press Home → [Replace password, Forget, ↩]
    lcd.enc_step(1)  # → Forget
    # Update mocks before clicking so the reload sees an empty list
    wm_mock.list_connections.return_value = []
    wm_mock.get_cached_saved.return_value = []
    wm_mock.scan_networks.return_value = []
    _click(lcd)  # forget → reload
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
    _click(lcd)  # tap active Home → [Disconnect, Replace password, Forget, ↩]
    lcd.enc_step(1)  # → Replace password
    _click(lcd)  # → password dialog
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
# Hotspot → WiFi recovery (multi-wifi feedback fix)
# ---------------------------------------------------------------------------


def test_open_in_hotspot_still_scans(v3_system, wifi_state):
    """While hotspot is active, opening the menu still triggers a scan.

    Without this, the cached scan stays empty across the hotspot toggle and
    'Nearby networks...' disappears from the menu.
    """
    wifi_state(scanned=[make_scanned("Home", signal=70)], saved=[], hotspot=True)
    wm_mock = v3_system.handler.wifi_manager
    _open(v3_system)
    assert wm_mock.scan_networks.called, "scan_networks must be called even when hotspot is active"


def test_notify_status_change_leaves_passphrase_dialog_open(v3_system, wifi_state):
    """An async status update arriving while the PSK editor is on top must NOT
    pop the editor or rebuild the root from under it."""
    nets = [make_scanned("Secured", signal=70)]
    wifi_state(scanned=nets, saved=[])

    wm, lcd = _open(v3_system)
    _click(lcd)  # enter "Nearby networks..."
    _click(lcd)  # tap Secured → password dialog
    assert isinstance(lcd.pstack.current, _PassphraseEditor)

    # Simulate polling-thread delivery while the modal is up.
    wifi_state(scanned=nets, saved=[make_saved("Secured")], active="Secured")
    wm.notify_status_change()

    assert isinstance(lcd.pstack.current, _PassphraseEditor), "notify_status_change must not disrupt an open modal"


def test_notify_status_change_leaves_error_dialog_open(v3_system, wifi_state):
    """Same guard for a MessageDialog sitting on top after a failed connect."""
    nets = [make_scanned("Net", signal=70)]
    wifi_state(scanned=nets, saved=[])
    v3_system.handler.wifi_manager.connect_scanned.return_value = b"connection timed out"

    wm, lcd = _open(v3_system)
    _click(lcd)  # enter "Nearby networks..."
    _click(lcd)  # tap Net → passphrase editor
    _type_password(lcd, "somepassword")
    _click(lcd)  # submit → error dialog
    assert isinstance(lcd.pstack.current, MessageDialog)

    wm.notify_status_change()

    assert isinstance(lcd.pstack.current, MessageDialog), (
        "notify_status_change must not pop a MessageDialog out from under the user"
    )


def test_tick_rescans_while_root_open(v3_system, wifi_state):
    """tick() submits a scan when the wifi root menu is the top panel."""
    wm_mock = v3_system.handler.wifi_manager
    wifi_state(scanned=[], saved=[make_saved("Home")], hotspot=False)
    wm, _lcd = _open(v3_system)
    scan_calls_after_open = wm_mock.scan_networks.call_count

    wm.tick()

    assert wm_mock.scan_networks.call_count > scan_calls_after_open, "tick must trigger a fresh scan"


def test_toggle_hotspot_off_shows_error_dialog_when_reconnect_fails(v3_system, wifi_state):
    """If the orchestrated disable+reconnect fails, surface a MessageDialog."""
    wifi_state(scanned=[], saved=[make_saved("Home")], hotspot=True)
    wm_mock = v3_system.handler.wifi_manager
    wm_mock.disable_hotspot.return_value = b"no network with ssid 'Home'"

    wm, lcd = _open(v3_system)
    # Root: [Home (saved), Join other network..., Hotspot Mode, dismiss]
    lcd.enc_step(1)  # Home → Join
    lcd.enc_step(1)  # Join → Hotspot Mode
    _click(lcd)

    assert isinstance(lcd.pstack.current, MessageDialog), (
        f"expected MessageDialog, got {type(lcd.pstack.current).__name__}"
    )


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
    _click(lcd)  # tap active Home → [Disconnect, Replace password, Forget, ↩]
    _click(lcd)  # tap Disconnect
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
    _click(lcd)  # enter "Nearby networks..."
    _click(lcd)  # tap Secured → password dialog
    snapshot("psk_special_chars_dialog")

    special = 'a"b\\c d'
    _type_password(lcd, special)
    _click(lcd)

    wm_mock.connect_scanned.assert_called_once_with("Secured", "WPA2", special)  # (ssid, security, psk)


# ---------------------------------------------------------------------------
# 5.19  test_dialog_cancel_returns_to_menu
# ---------------------------------------------------------------------------


def test_dialog_cancel_returns_to_menu(v3_system, wifi_state, snapshot):
    """Cancelling the password dialog returns to the nearby submenu."""
    nets = [make_scanned("Secured", signal=70)]
    wifi_state(scanned=nets, saved=[])

    _wm, lcd = _open(v3_system)
    _click(lcd)  # enter "Nearby networks..."
    _click(lcd)  # tap Secured → passphrase editor (selector starts at Cancel)
    _click(lcd)  # click Cancel → close editor
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
    _click(lcd)  # open "Join other network..." dialog

    # Navigate to OK without typing anything
    lcd.enc_step(1)  # ssid → passwd
    lcd.enc_step(1)  # passwd → cancel
    lcd.enc_step(1)  # cancel → ok
    _click(lcd)  # submit with empty SSID → no-op

    snapshot("join_empty_ssid")

    assert isinstance(lcd.pstack.current, Dialog)


# ---------------------------------------------------------------------------
# 5.21  test_join_other_with_space_in_ssid  (github #122)
# ---------------------------------------------------------------------------


def test_join_other_with_space_in_ssid(v3_system, wifi_state, type_in_editor, snapshot):
    """github #122: SSIDs with spaces are enterable, and the space renders as ␣ (U+2423)."""
    wifi_state(scanned=[], saved=[])

    wm_mock = v3_system.handler.wifi_manager
    wm_mock.connect_scanned.return_value = None

    _wm, lcd = _open(v3_system)
    lcd.enc_step(1)  # Nearby networks... → Join other network...
    _click(lcd)

    dialog = lcd.pstack.current
    assert isinstance(dialog, Dialog)

    _click(lcd)  # ssid_field → TextEditor
    editor = lcd.pstack.current
    assert isinstance(editor, TextEditor), type(editor)

    type_in_editor(lcd, "My")

    # Land the selector on the space character to verify the ␣ glyph renders.
    assert editor.sel is not None
    selector = editor.sel_list[editor.sel]
    assert isinstance(selector, LetterSelector)
    selector.l_idx = 3  # a non-control char: long-click cycles the charset
    while selector.mode != LetterSelector.MODE_SP:
        _long_click(lcd)
    selector.l_idx = LetterSelector.specials.index(" ")
    snapshot("space_char_selected")

    type_in_editor(lcd, " Wifi")

    # Commit the text back to the SSID field.
    selector.l_idx = selector.ctrl_OK
    _click(lcd)

    dialog = lcd.pstack.current
    assert isinstance(dialog, Dialog)
    ssid_field = dialog.sel_list[0]
    assert isinstance(ssid_field, TextWidget)
    assert ssid_field.text == "My Wifi"
    snapshot("join_dialog_ssid_with_space")

    # Selectable widgets: [0]=ssid_field, [1]=pw_field, [2]=cancel_btn, [3]=ok_btn
    dialog.sel_widget(dialog.sel_list[3])  # ok_btn
    _click(lcd)

    wm_mock.connect_scanned.assert_called_once()
    assert wm_mock.connect_scanned.call_args[0][0] == "My Wifi"
