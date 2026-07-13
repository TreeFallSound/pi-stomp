"""NAV-only (v2, no Tweak encoders) coverage for the GxCabinet full-screen panel.

Drives the panel via NAV rotation/click alone: select a knob, CLICK opens the
generic Parameterdialog for its symbol, NAV rotation edits the value, CLICK
closes it. Mirrors tests/v3/test_gx_cabinet_panel.py's sagas but proves the
same panel is fully operable with no Tweak1/2/3 hardware at all (charter
Requirement 1).
"""

from __future__ import annotations

from uilib.parameterdialog import Parameterdialog

from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from tests.v3.test_gx_cabinet_panel import open_panel


def nav(nav_handler, steps: int) -> None:
    direction = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        nav_handler(direction)


def current_dialog(v2_system: SystemFixture) -> Parameterdialog | None:
    top = v2_system.handler.lcd.pstack.current
    return top if isinstance(top, Parameterdialog) else None


def test_gx_cabinet_nav_only_initial_render(v2_system: SystemFixture, snapshot):
    """Panel opens identically on v2 — no Tweak badges assumed."""
    open_panel(v2_system)
    snapshot("opened")


def test_gx_cabinet_nav_only_edits_bass(v2_system: SystemFixture, nav_handler, snapshot):
    """NAV to Bass, CLICK opens its dialog, NAV rotates the value, CLICK closes."""
    handler = v2_system.handler
    plugin = open_panel(v2_system)

    # Nav: Model(0) -> Level(1) -> Bass(2)
    nav(nav_handler, 2)
    handler.poll_lcd_updates()
    snapshot("bass_focused")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is not None
    snapshot("bass_dialog_open")

    nav_handler(8)
    handler.poll_lcd_updates()
    snapshot("bass_dialog_edited")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is None
    snapshot("bass_dialog_closed")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "CBass")
    assert len(sent) > 0
    assert sent[-1] > 0.0

    # The panel's own arc knob must reflect the edit once the dialog closes —
    # not just the plugin's parameter store. Regression: the generic
    # Parameterdialog commits straight to plugin.parameters and never calls
    # back into the panel's apply_state()/snapshot_state() resync.
    panel = v2_system.handler.lcd.pstack.current
    from plugins.gx_cabinet.panel import GxCabinetPanel

    assert isinstance(panel, GxCabinetPanel)
    assert panel._knob_bass.value == sent[-1]


def test_gx_cabinet_nav_only_edits_model(v2_system: SystemFixture, nav_handler, snapshot):
    """Model is an enumeration: CLICK opens a selection menu, not a slider."""
    handler = v2_system.handler
    open_panel(v2_system)
    snapshot("model_focused")

    lcd = v2_system.handler.lcd
    panel_before = lcd.pstack.current

    nav_click(handler)
    handler.poll_lcd_updates()
    # Enumeration params open a selection menu (not a Parameterdialog) —
    # draw_parameter_dialog's own type-based dispatch, reused as-is.
    assert current_dialog(v2_system) is None
    assert lcd.pstack.current is not panel_before
    snapshot("model_menu_open")


def test_gx_cabinet_nav_only_longpress_resets(v2_system: SystemFixture, nav_handler, snapshot):
    """LONGPRESS still resets the focused knob to its lv2:default."""
    handler = v2_system.handler
    plugin = open_panel(v2_system)

    nav(nav_handler, 2)  # focus Bass
    nav_click(handler)
    handler.poll_lcd_updates()
    nav_handler(8)
    handler.poll_lcd_updates()
    nav_click(handler)  # close dialog, commit the edit
    handler.poll_lcd_updates()
    snapshot("bass_edited")

    nav_click(handler, long=True)
    handler.poll_lcd_updates()
    snapshot("bass_reset")

    sent = v2_system.ws_bridge.sent_values_for(plugin.instance_id, "CBass")
    assert sent[-1] == 0.0
