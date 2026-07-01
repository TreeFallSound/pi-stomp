"""Snapshot sagas for the DISTRHO a-comp compressor panel.

Long-press the compressor tile to open the full-screen panel: a staggered left
column of arc-ring controls (Thresh/Ratio/Knee/Makeup) and a square reticule
transfer-curve plot on the right. Tweak1 adjusts the selected control (Tweak2
threshold, Tweak3 ratio); Nav cycles them.

The fake plugin has no instance_number, so the JACK GR-meter subprocess is not
spawned (the curve renders; the crosshair parks at the threshold knee).

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_acomp_panel.py --snapshot-update
"""

from __future__ import annotations

from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.acomp import ACOMP_URI
from plugins.customization import lookup
from uilib.misc import InputEvent
from tests.types import SystemFixture


class _FakeEnc(Controller):
    def __init__(self, id: int):
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id


def _param(symbol: str, value: float, minimum: float, maximum: float, instance_id: str = "Comp") -> Parameter:
    info = {"shortName": symbol, "symbol": symbol, "ranges": {"minimum": minimum, "maximum": maximum}}
    return Parameter(info, value, None, instance_id)


def make_acomp_plugin(instance_id: str = "Comp") -> Plugin:
    params: dict[str, Parameter] = {
        ":bypass": Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, instance_id),
        "thr": _param("thr", -18.0, -60.0, 0.0, instance_id),
        "rat": _param("rat", 4.0, 1.0, 20.0, instance_id),
        "kn": _param("kn", 2.0, 0.0, 8.0, instance_id),
        "mak": _param("mak", 6.0, 0.0, 30.0, instance_id),
    }
    plugin = Plugin(instance_id, params, {}, "Dynamics", uri=ACOMP_URI, customization=lookup(ACOMP_URI))
    plugin.has_footswitch = True
    plugin.pedalboard_snapshot = {
        sym: float(p.value) if p.value is not None else 0.0 for sym, p in params.items()
    }
    return plugin


def open_panel(v3_system: SystemFixture) -> Plugin:
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current
    plugin = make_acomp_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    lcd = handler.lcd
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()
    return plugin


def tweak(handler, idx: int, rotations: int) -> bool:
    event = EncoderEvent(controller=_FakeEnc(idx), rotations=rotations, new_value=0.0, new_midi_value=0)
    return handler.handle(event)


def test_acomp_initial_render(v3_system: SystemFixture, snapshot):
    """Window opens: arc column + transfer curve, GR bar idle."""
    open_panel(v3_system)
    snapshot()


def test_acomp_tweak_ratio(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Ratio, then Tweak1 lowers the ratio — the curve's slope changes."""
    handler = v3_system.handler
    open_panel(v3_system)
    nav_handler(1)  # thr -> rat
    for _ in range(6):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot()


def test_acomp_external_bypass_dims_visuals(v3_system: SystemFixture, snapshot):
    """An external bypass (footswitch / mod-UI echo) must dim the column and curve.

    Regression: the panel's tick() did not poll is_bypassed(), so the in-window
    Bypass button and the arc/curve visuals stayed live while the plugin was
    actually bypassed elsewhere.
    """
    plugin = open_panel(v3_system)
    plugin.set_bypass(True)
    v3_system.handler.poll_lcd_updates()
    snapshot("bypassed")
    plugin.set_bypass(False)
    v3_system.handler.poll_lcd_updates()
    snapshot("unbypassed")
