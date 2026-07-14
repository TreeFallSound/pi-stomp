"""A plugin whose only control port is hidden.

GxDenoiser2 is real: one control port, named BYPASS, designated `enabled`.
Hiding it leaves the parameter window with nothing to paint but its own chrome,
so the ring/row layout must survive a zero count.
"""

from __future__ import annotations

from common.parameter import BYPASS_SYMBOL, Parameter, PortInfo, Symbol
from modalapi.plugin import Plugin
from plugins.parameter_window import ParameterWindow
from uilib.misc import InputEvent

from tests.types import SystemFixture

GX_DENOISER_URI = "http://guitarix.sourceforge.net/plugins/gx_denoiser2_#_denoiser2_"


def _make_plugin(instance_id: str = "Denoiser") -> Plugin:
    bypass: PortInfo = {"shortName": "bypass", "symbol": BYPASS_SYMBOL, "ranges": {"minimum": 0, "maximum": 1}}
    enabled: PortInfo = {
        "shortName": "BYPASS",
        "symbol": "BYPASS",
        "ranges": {"minimum": 0, "maximum": 1},
        "designation": "http://lv2plug.in/ns/lv2core#enabled",
    }
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter(bypass, 0.0, None, instance_id),
        Symbol("BYPASS"): Parameter(enabled, 1.0, None, instance_id),
    }
    plugin = Plugin(instance_id, params, {}, "Utility", uri=GX_DENOISER_URI)
    plugin.pedalboard_snapshot = {sym: float(p.value) for sym, p in params.items()}
    return plugin


def _open(v3_system: SystemFixture) -> Plugin:
    handler = v3_system.handler
    assert handler.current
    plugin = _make_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, v3_system.hw.footswitches)
    handler.lcd.draw_main_panel()

    lcd = handler.lcd
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()
    return plugin


def test_only_port_is_hidden(v3_system: SystemFixture):
    plugin = _open(v3_system)
    assert set(plugin.visible_parameters) == {BYPASS_SYMBOL}


def test_window_renders_with_no_params(v3_system: SystemFixture, snapshot):
    """No rings, no rows — just Back/Bypass/Reset. Must not divide by zero."""
    _open(v3_system)
    panel = v3_system.handler.lcd.pstack.current
    assert isinstance(panel, ParameterWindow)
    assert panel.slots == []
    assert panel._list_rows == []
    snapshot("empty")
