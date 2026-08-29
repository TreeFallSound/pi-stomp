"""Snapshot saga for the first-boot WelcomePanel.

Exercises: open → nav across buttons → Start dismisses → not shown when seen →
Setup no-op → Restore success.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_welcome_panel.py --snapshot-update
"""

from unittest.mock import patch

import common.token as Token
from modalapi.archive import JobState
from tests.archive_fake import fake_jobs
from tests.types import SystemFixture
from tests.usb_fake import drive
from ui.archive_panel import ArchiveProgressPanel
from tests.v3.nav_helpers import nav_step, nav_click
from ui.welcome import WelcomePanel


def _open_welcome(v3_system: SystemFixture):
    handler = v3_system.handler
    handler.maybe_show_welcome()
    handler.poll_lcd_updates()


def _with_backup_drive(v3_system: SystemFixture):
    """Restore is only reachable when a drive holds a backup."""
    return patch.object(v3_system.handler, "usb_drives", return_value=[drive("USB")])


def test_welcome_saga(v3_system: SystemFixture, snapshot):
    """Open welcome, nav across buttons, click Start → dismissed."""
    handler = v3_system.handler

    with _with_backup_drive(v3_system):
        _open_welcome(v3_system)
    snapshot("opened")

    # Nav right twice to reach Setup..., then back to Start
    nav_step(handler, 1)
    handler.poll_lcd_updates()
    snapshot("restore_selected")
    nav_step(handler, 1)
    handler.poll_lcd_updates()
    snapshot("setup_selected")
    nav_step(handler, -2)
    handler.poll_lcd_updates()
    snapshot("start_selected")

    # Click Start
    nav_click(handler)
    snapshot("dismissed")

    handler.settings.set_setting.assert_called_with(Token.WELCOME_SEEN, True)  # pyright: ignore[reportAttributeAccessIssue]


def test_not_shown_when_seen(v3_system: SystemFixture):
    """Welcome panel is not pushed when WELCOME_SEEN is True."""
    handler = v3_system.handler
    with patch.object(handler.settings, "get_setting", return_value=True):
        handler.maybe_show_welcome()
    assert handler.lcd.pstack.find_panel_type(WelcomePanel) is None


def test_setup_noop(v3_system: SystemFixture, snapshot):
    """Setup... button shows message dialog when recovery is unavailable."""
    handler = v3_system.handler
    handler.recovery_available = False

    with _with_backup_drive(v3_system):
        _open_welcome(v3_system)

    # Nav to Setup... and click
    nav_step(handler, 2)
    nav_click(handler)
    handler.poll_lcd_updates()
    snapshot("setup_noop")

    # Welcome should still be current (dialog pushed above it)
    assert handler.lcd.pstack.find_panel_type(WelcomePanel) is not None


def test_restore_success(v3_system: SystemFixture, snapshot):
    """Restore calls load_settings before set_setting and pops welcome — but only once the
    user closes the progress panel, since the restore now runs off the UI thread."""
    handler = v3_system.handler

    with _with_backup_drive(v3_system):
        _open_welcome(v3_system)

    with (
        _with_backup_drive(v3_system),
        patch.object(handler, "restart_ui_stack") as mock_restart,
        fake_jobs() as jobs,
    ):
        nav_step(handler, 1)
        nav_click(handler)
        handler.poll_lcd_updates()

        # Welcome survives behind the progress panel until the restore finishes.
        assert handler.lcd.pstack.find_panel_type(WelcomePanel) is not None

        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None
        jobs[0].finish(JobState.DONE)
        handler.poll_lcd_updates()
        panel._on_button()
        handler.poll_lcd_updates()
        mock_restart.assert_called_once_with()

    snapshot("restore_success")

    assert handler.lcd.pstack.find_panel_type(WelcomePanel) is None


def test_restore_failure_keeps_welcome_and_never_restarts(v3_system: SystemFixture):
    """A failed restore from the welcome screen must leave the user where they started:
    welcome still up, WELCOME_SEEN unset so it reappears, and no restart into a
    half-written data/."""
    handler = v3_system.handler

    with _with_backup_drive(v3_system):
        _open_welcome(v3_system)

    with (
        _with_backup_drive(v3_system),
        patch.object(handler, "restart_ui_stack") as mock_restart,
        fake_jobs() as jobs,
    ):
        nav_step(handler, 1)
        nav_click(handler)
        handler.poll_lcd_updates()

        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None
        jobs[0].finish(JobState.FAILED, error="unzip: cannot find zipfile directory")
        handler.poll_lcd_updates()
        panel._on_button()
        handler.poll_lcd_updates()

    mock_restart.assert_not_called()
    assert handler.lcd.pstack.find_panel_type(WelcomePanel) is not None
    calls = handler.settings.set_setting.call_args_list  # pyright: ignore[reportAttributeAccessIssue]
    assert Token.WELCOME_SEEN not in [c.args[0] for c in calls]


def test_restore_button_is_dim_and_unreachable_with_no_backup(v3_system: SystemFixture, snapshot):
    """With no drive holding a backup there is nothing to restore. The button says so and
    NAV goes from Start straight to Setup."""
    handler = v3_system.handler

    _open_welcome(v3_system)
    snapshot("restore_disabled")

    panel = handler.lcd.pstack.find_panel_type(WelcomePanel)
    assert panel is not None
    assert panel._btn_restore not in panel.sel_list

    nav_step(handler, 1)
    handler.poll_lcd_updates()
    assert panel.sel_ref is panel._btn_setup


def test_restore_button_enables_when_a_drive_appears(v3_system: SystemFixture):
    """The user plugs the drive in while the welcome screen is up. Nothing reports a new
    mount, thus the panel polls, and NAV order stays Start, Restore, Setup."""
    handler = v3_system.handler

    _open_welcome(v3_system)
    panel = handler.lcd.pstack.find_panel_type(WelcomePanel)
    assert panel is not None
    assert panel._btn_restore not in panel.sel_list

    with _with_backup_drive(v3_system):
        panel._restore_checked_at = 0.0
        handler.poll_lcd_updates()

    assert panel.sel_list == [panel._btn_start, panel._btn_restore, panel._btn_setup]
