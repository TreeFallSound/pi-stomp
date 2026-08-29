"""NAV-only (v2, no Tweak encoders) coverage for the a-comp compressor panel.

The arc column's proxy widgets (ArcSelectable) previously swallowed CLICK as a
no-op — this proves NAV can now reach the dialog for each selectable control.
"""

from __future__ import annotations

from uilib.parameterdialog import Parameterdialog

from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from tests.v3.test_acomp_panel import open_panel


def current_dialog(v2_system: SystemFixture) -> Parameterdialog | None:
    top = v2_system.handler.lcd.pstack.current
    return top if isinstance(top, Parameterdialog) else None


def test_acomp_nav_only_initial_render(v2_system: SystemFixture, snapshot):
    open_panel(v2_system)
    snapshot("opened")


def test_acomp_nav_only_edits_ratio(v2_system: SystemFixture, nav_handler, snapshot):
    """NAV to Ratio, CLICK opens its dialog, NAV rotates, CLICK closes."""
    handler = v2_system.handler
    plugin = open_panel(v2_system)

    nav_handler(1)  # Thresh -> Ratio
    handler.poll_lcd_updates()
    snapshot("ratio_focused")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is not None
    snapshot("ratio_dialog_open")

    nav_handler(6)
    handler.poll_lcd_updates()
    snapshot("ratio_dialog_edited")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is None
    snapshot("ratio_dialog_closed")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "rat")
    assert len(sent) > 0


def test_acomp_nav_only_longpress_resets(v2_system: SystemFixture, nav_handler, snapshot):
    handler = v2_system.handler
    plugin = open_panel(v2_system)

    nav_click(handler)  # focus is Thresh by default; open its dialog
    handler.poll_lcd_updates()
    nav_handler(6)
    handler.poll_lcd_updates()
    nav_click(handler)  # close, commit
    handler.poll_lcd_updates()
    snapshot("thr_edited")

    nav_click(handler, long=True)
    handler.poll_lcd_updates()
    snapshot("thr_reset")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "thr")
    assert sent[-1] == -18.0
