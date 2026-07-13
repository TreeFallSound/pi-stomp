"""NAV-only (v2, no Tweak encoders) coverage for the multiband menu family
(exercised via caps_noisegate, the one subclass with a snapshot suite).

Single, generic (no-role) SelectionEditEffect on enc1: CLICK opens the
dialog for whichever slot is focused directly, no submenu.
"""

from __future__ import annotations

from uilib.parameterdialog import Parameterdialog

from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from tests.v3.test_caps_noisegate_menu import open_menu


def current_dialog(v2_system: SystemFixture) -> Parameterdialog | None:
    top = v2_system.handler.lcd.pstack.current
    return top if isinstance(top, Parameterdialog) else None


def test_noisegate_nav_only_initial_render(v2_system: SystemFixture, snapshot):
    open_menu(v2_system)
    snapshot("opened")


def test_noisegate_nav_only_edits_open(v2_system: SystemFixture, nav_handler, snapshot):
    """First slot (Open) is focused at open; CLICK opens its dialog directly."""
    handler = v2_system.handler
    plugin = open_menu(v2_system)

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is not None
    snapshot("open_dialog_open")

    nav_handler(8)
    handler.poll_lcd_updates()
    snapshot("open_dialog_edited")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is None
    snapshot("open_dialog_closed")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "open")
    assert len(sent) > 0


def test_noisegate_nav_only_longpress_resets(v2_system: SystemFixture, nav_handler, snapshot):
    handler = v2_system.handler
    plugin = open_menu(v2_system)

    nav_click(handler)
    handler.poll_lcd_updates()
    nav_handler(8)
    handler.poll_lcd_updates()
    nav_click(handler)
    handler.poll_lcd_updates()
    snapshot("open_edited")

    nav_click(handler, long=True)
    handler.poll_lcd_updates()
    snapshot("open_reset")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "open")
    assert sent[-1] == -45.0
