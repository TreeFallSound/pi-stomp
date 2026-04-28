"""v3-specific system menu behaviour."""

from unittest.mock import patch

from pistomp.sync import SyncResult
from tests.types import SystemFixture


def test_system_info_load(v3_system: SystemFixture):
    """On v3 (no relay), system_info_load reads bypass state from the audiocard."""
    handler = v3_system.handler
    handler.audiocard.get_switch_parameter.return_value = True
    handler.audiocard.get_bypass_left.return_value = False
    handler.audiocard.get_bypass_right.return_value = True

    with patch("subprocess.check_output", return_value=b"v1.0.0-abc\n"):
        handler.system_info_load()

    assert handler.software_version == "v1.0.0-abc\n"
    assert handler.eq_status is True
    assert handler.bypass_left is False
    assert handler.bypass_right is True


# ---------------------------------------------------------------------------
# sync_pedalboards LCD flow — each SyncResult status branch
# ---------------------------------------------------------------------------

def _sync_lcd(v3_system: SystemFixture, result: SyncResult):
    """Patch system_menu_sync_pedalboards and drive the LCD flow."""
    lcd = v3_system.handler.lcd
    with patch.object(v3_system.handler, "system_menu_sync_pedalboards", return_value=result):
        lcd.sync_pedalboards(None)


def test_sync_lcd_up_to_date(v3_system: SystemFixture, snapshot):
    _sync_lcd(v3_system, SyncResult(status="up_to_date", message="Up to date"))
    snapshot()


def test_sync_lcd_applied(v3_system: SystemFixture, snapshot):
    _sync_lcd(v3_system, SyncResult(status="applied", count=3, message="3 update(s) applied"))
    snapshot()


def test_sync_lcd_network_error(v3_system: SystemFixture, snapshot):
    _sync_lcd(v3_system, SyncResult(status="network_error", message="Sync failed: no network"))
    snapshot()


def test_sync_lcd_conflicts(v3_system: SystemFixture, snapshot):
    conflicts = ["Metal.pedalboard/config.yml", "Jazz.pedalboard/config.yml (uncommitted edit)"]
    _sync_lcd(v3_system, SyncResult(status="conflicts", conflicts=conflicts, message="Sync aborted: conflicts"))
    snapshot()


def test_sync_lcd_error(v3_system: SystemFixture, snapshot):
    _sync_lcd(v3_system, SyncResult(status="error", message="Sync error — see logs: journalctl -u mod-ala-pi-stomp"))
    snapshot()


# ---------------------------------------------------------------------------
# Notification icon visibility
# ---------------------------------------------------------------------------


def test_notification_icon_hidden_by_default(v3_system: SystemFixture, snapshot):
    """Toolbar shows no notification icon when handler.notification is None."""
    v3_system.handler.lcd.main_panel.refresh()
    snapshot()


def test_notification_icon_visible_when_set(v3_system: SystemFixture, snapshot):
    """Toolbar shows notification icon after set_notification is called."""
    v3_system.handler.set_notification("Remote mismatch: local commits not on origin.")
    snapshot()


def test_notification_clears_after_successful_sync(v3_system: SystemFixture, snapshot):
    """Notification icon disappears after a successful sync."""
    v3_system.handler.set_notification("stale error")
    _sync_lcd(v3_system, SyncResult(status="up_to_date", message="Up to date"))
    snapshot()
