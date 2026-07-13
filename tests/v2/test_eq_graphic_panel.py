"""NAV-only (v2, no Tweak encoders) coverage for the caps-Eq10 graphic EQ panel.

Single-symbol case (only gain is live per band): CLICK opens the dialog
directly, no submenu. LONGPRESS still resets that band's gain to 0 dB.
"""

from __future__ import annotations

from uilib.parameterdialog import Parameterdialog

from plugins.capseq10.band_spec import BAND_SPECS
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from tests.v3.test_graphic_eq_panel import open_eq


def current_dialog(v2_system: SystemFixture) -> Parameterdialog | None:
    top = v2_system.handler.lcd.pstack.current
    return top if isinstance(top, Parameterdialog) else None


def test_graphic_eq_nav_only_initial_render(v2_system: SystemFixture, snapshot):
    open_eq(v2_system)
    snapshot("opened")


def test_graphic_eq_nav_only_edits_band_gain(v2_system: SystemFixture, nav_handler, snapshot):
    """First band is focused at open; CLICK opens its gain dialog directly."""
    handler = v2_system.handler
    plugin = open_eq(v2_system)
    band = BAND_SPECS[0]

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is not None
    snapshot("band0_dialog_open")

    nav_handler(12)
    handler.poll_lcd_updates()
    snapshot("band0_dialog_edited")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is None
    snapshot("band0_dialog_closed")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, band.gain_sym)
    assert len(sent) > 0 and sent[-1] > 0


def test_graphic_eq_nav_only_longpress_resets(v2_system: SystemFixture, nav_handler, snapshot):
    handler = v2_system.handler
    plugin = open_eq(v2_system)
    band = BAND_SPECS[0]

    nav_click(handler)
    handler.poll_lcd_updates()
    nav_handler(12)
    handler.poll_lcd_updates()
    nav_click(handler)
    handler.poll_lcd_updates()
    snapshot("band0_edited")

    nav_click(handler, long=True)
    handler.poll_lcd_updates()
    snapshot("band0_reset")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, band.gain_sym)
    assert sent[-1] == 0.0
