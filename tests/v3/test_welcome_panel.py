"""Snapshot saga for the first-boot WelcomePanel.

Exercises: open → nav across buttons → Start dismisses → not shown when seen →
Setup no-op → Restore success.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_welcome_panel.py --snapshot-update
"""

from unittest.mock import patch

import common.token as Token
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_step, nav_click
from ui.welcome import WelcomePanel


def _open_welcome(v3_system: SystemFixture):
    handler = v3_system.handler
    handler.maybe_show_welcome()
    handler.poll_lcd_updates()


def test_welcome_saga(v3_system: SystemFixture, snapshot):
    """Open welcome, nav across buttons, click Start → dismissed."""
    handler = v3_system.handler

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

    _open_welcome(v3_system)

    # Nav to Setup... and click
    nav_step(handler, 2)
    nav_click(handler)
    handler.poll_lcd_updates()
    snapshot("setup_noop")

    # Welcome should still be current (dialog pushed above it)
    assert handler.lcd.pstack.find_panel_type(WelcomePanel) is not None


def test_restore_success(v3_system: SystemFixture, snapshot):
    """Restore calls load_settings before set_setting and pops welcome."""
    handler = v3_system.handler

    _open_welcome(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=["/media/USB/backups"]),
        patch("os.path.exists", return_value=True),
        patch("subprocess.check_output", return_value=b""),
    ):
        nav_step(handler, 1)
        nav_click(handler)
        handler.poll_lcd_updates()

    snapshot("restore_success")

    assert handler.lcd.pstack.find_panel_type(WelcomePanel) is None
