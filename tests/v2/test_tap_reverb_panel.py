"""NAV-only (v2, no Tweak encoders) coverage for the TapReverb full-screen panel.

Mirrors tests/v2/test_gx_cabinet_panel.py's shape — same three-row panel
family (fixed enc2/enc3, SelectionEditEffect enc1), same NAV-only proof.
"""

from __future__ import annotations

from uilib.parameterdialog import Parameterdialog

from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from tests.v3.test_tap_reverb_panel import open_panel


def nav(nav_handler, steps: int) -> None:
    direction = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        nav_handler(direction)


def current_dialog(v2_system: SystemFixture) -> Parameterdialog | None:
    top = v2_system.handler.lcd.pstack.current
    return top if isinstance(top, Parameterdialog) else None


def test_tap_reverb_nav_only_initial_render(v2_system: SystemFixture, snapshot):
    open_panel(v2_system)
    snapshot("opened")


def test_tap_reverb_nav_only_edits_decay(v2_system: SystemFixture, nav_handler, snapshot):
    """NAV to Decay, CLICK opens its dialog, NAV rotates the value, CLICK closes."""
    handler = v2_system.handler
    plugin = open_panel(v2_system)

    nav(nav_handler, 1)  # Mode(0) -> Decay(1)
    handler.poll_lcd_updates()
    snapshot("decay_focused")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is not None
    snapshot("decay_dialog_open")

    nav_handler(8)
    handler.poll_lcd_updates()
    snapshot("decay_dialog_edited")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is None
    snapshot("decay_dialog_closed")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "decay")
    assert len(sent) > 0


def test_tap_reverb_nav_only_longpress_resets(v2_system: SystemFixture, nav_handler, snapshot):
    handler = v2_system.handler
    plugin = open_panel(v2_system)

    nav(nav_handler, 1)  # focus Decay
    nav_click(handler)
    handler.poll_lcd_updates()
    nav_handler(8)
    handler.poll_lcd_updates()
    nav_click(handler)  # close, commit
    handler.poll_lcd_updates()
    snapshot("decay_edited")

    nav_click(handler, long=True)
    handler.poll_lcd_updates()
    snapshot("decay_reset")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "decay")
    assert sent[-1] == 2800.0
