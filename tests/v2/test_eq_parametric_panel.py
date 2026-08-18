"""NAV-only (v2, no Tweak encoders) coverage for the fil4 parametric EQ panel.

The compound MultiSelectable case: a band's gain/freq/Q aren't a single
symbol, so NAV LONGPRESS opens a ParameterWindow over gain/freq/Q (arc rings)
instead of one dialog directly — CLICK on the band itself stays a plain
toggle (enable). Each ring's dialog edits the right symbol; back returns to
the panel.
"""

from __future__ import annotations

from plugins.parameter_window import ParameterWindow
from uilib.parameterdialog import Parameterdialog

from plugins.fil4.panel import Fil4Panel
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from tests.v3.test_eq_panel import open_eq


def nav(nav_handler, steps: int) -> None:
    direction = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        nav_handler(direction)


def current(v2_system: SystemFixture):
    return v2_system.handler.lcd.pstack.current


def test_eq_parametric_nav_only_band_submenu(v2_system: SystemFixture, nav_handler, snapshot):
    """Nav to B1, enable it, longpress opens the gain/freq/Q ParameterWindow;
    each ring's dialog edits the right symbol; back returns to the panel."""
    handler = v2_system.handler
    plugin = open_eq(v2_system)

    nav(nav_handler, 2)  # HP -> LS -> B1
    handler.poll_lcd_updates()
    snapshot("b1_focused")

    nav_click(handler)  # CLICK: enable the band (plain toggle, not the editor)
    handler.poll_lcd_updates()
    assert isinstance(current(v2_system), Fil4Panel)
    snapshot("b1_enabled")

    nav_click(handler, long=True)  # LONGPRESS: open the gain/freq/Q window
    handler.poll_lcd_updates()
    assert isinstance(current(v2_system), ParameterWindow)
    snapshot("b1_submenu_open")

    # Gain ring is selected first; CLICK opens its dialog.
    nav_click(handler)
    handler.poll_lcd_updates()
    assert isinstance(current(v2_system), Parameterdialog)
    nav_handler(12)
    handler.poll_lcd_updates()
    nav_click(handler)  # close dialog, back to the window
    handler.poll_lcd_updates()
    assert isinstance(current(v2_system), ParameterWindow)

    nav(nav_handler, 1)  # Gain -> Freq
    nav_click(handler)
    handler.poll_lcd_updates()
    assert isinstance(current(v2_system), Parameterdialog)
    nav_handler(12)
    handler.poll_lcd_updates()
    nav_click(handler)
    handler.poll_lcd_updates()

    nav(nav_handler, 1)  # Freq -> Q
    nav_click(handler)
    handler.poll_lcd_updates()
    assert isinstance(current(v2_system), Parameterdialog)
    nav_handler(-8)
    handler.poll_lcd_updates()
    nav_click(handler)
    handler.poll_lcd_updates()
    snapshot("b1_submenu_all_edited")
    # Q is at index 2; Back follows at index 3.
    nav(nav_handler, 1)  # Q -> Back
    nav_click(handler)
    handler.poll_lcd_updates()
    assert isinstance(current(v2_system), Fil4Panel)
    snapshot("b1_submenu_closed")

    sent_gain = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "gain1")
    sent_freq = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "freq1")
    sent_q = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "q1")
    assert len(sent_gain) > 0 and sent_gain[-1] > 0
    assert len(sent_freq) > 0 and sent_freq[-1] > 0
    assert len(sent_q) > 0
