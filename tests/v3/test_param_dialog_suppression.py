"""Outbound suppression that outlives its load reads on the LCD as a parameter
dialog that opens but will not move: ``Parameter.commit`` rolls back when the
send does not leave."""

from __future__ import annotations

from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from common.parameter import BYPASS_SYMBOL, Symbol
from uilib.misc import InputEvent
from uilib.parameterdialog import Parameterdialog
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click, nav_step
from tests.v3.test_caps_noisegate_menu import _param


def _open_dialog(v3_system: SystemFixture) -> Plugin:
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current

    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter(
            {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, "many"
        ),
    }
    for i in range(6):
        sym = Symbol(f"param_{i:02d}")
        params[sym] = _param(sym, 0.5, 0.0, 1.0, "many", unit="dB")
    plugin = Plugin("many", params, {}, "Dynamics")
    plugin.pedalboard_snapshot = {sym: 0.5 for sym in params}

    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    lcd = handler.lcd
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()

    nav_click(handler)
    handler.poll_lcd_updates()
    assert isinstance(lcd.pstack.current, Parameterdialog)
    return plugin


def test_nav_edits_dialog_after_bundleless_load(v3_system: SystemFixture):
    """A load that names no new bundle must not leave outbound sends
    suppressed: NAV in the dialog still edits the parameter."""
    handler = v3_system.handler

    v3_system.ws_bridge.inject("loading_start 0")
    v3_system.ws_bridge.inject("loading_end 1")
    handler.poll_ws_messages()

    plugin = _open_dialog(v3_system)
    for _ in range(8):
        nav_step(handler, 1)
    handler.poll_lcd_updates()

    assert plugin.parameters[Symbol("param_00")].value > 0.5
    assert v3_system.ws_bridge.sent_values_for(plugin.instance_id, "param_00")
