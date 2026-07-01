"""Snapshot sagas for the CAPS Noisegate custom-layout menu widget.

Long-press the Noisegate plugin tile to open the arc-ring window with the
4 arc-ring slots (Open, Close, Attack, Mains). Tweak1 adjusts the selected
slot; navigation cycles slots via Nav.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_caps_noisegate_menu.py --snapshot-update
"""

from __future__ import annotations

import pistomp.switchstate as switchstate
from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.customization import lookup
from uilib.misc import InputEvent
from tests.types import SystemFixture


CAPS_NOISEGATE_URI = "http://moddevices.com/plugins/caps/Noisegate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEnc(Controller):
    def __init__(self, id: int):
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id


def _param(symbol: str, value: float, minimum: float, maximum: float, instance_id: str = "Gate") -> Parameter:
    info = {"shortName": symbol, "symbol": symbol, "ranges": {"minimum": minimum, "maximum": maximum}}
    return Parameter(info, value, None, instance_id)


def make_noisegate_plugin(instance_id: str = "Gate") -> Plugin:
    params: dict[str, Parameter] = {
        ":bypass": Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, instance_id),
        "open": _param("open", -45.0, -60.0, 0.0, instance_id),
        "attack": _param("attack", 0.0, 0.0, 5.0, instance_id),
        "close": _param("close", -67.5, -80.0, 0.0, instance_id),
        "mains": _param("mains", 50.0, 0.0, 100.0, instance_id),
    }
    plugin = Plugin(instance_id, params, {}, "Dynamics", uri=CAPS_NOISEGATE_URI, customization=lookup(CAPS_NOISEGATE_URI))
    plugin.has_footswitch = True
    plugin.pedalboard_snapshot = {
        sym: float(p.value) if p.value is not None else 0.0
        for sym, p in params.items()
    }
    return plugin


def open_menu(v3_system: SystemFixture) -> Plugin:
    """Install a Noisegate plugin and open its custom layout menu. Returns the plugin."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    plugin = make_noisegate_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # Long-press the plugin tile to open the custom layout menu
    lcd = handler.lcd
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()
    return plugin


def tweak(handler, idx: int, rotations: int) -> bool:
    event = EncoderEvent(controller=_FakeEnc(idx), rotations=rotations, new_value=0.0, new_midi_value=0)
    return handler.handle(event)


def long_press(handler) -> None:
    handler.universal_encoder_sw(switchstate.Value.LONGPRESSED)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)


# ---------------------------------------------------------------------------
# Sagas
# ---------------------------------------------------------------------------


def test_noisegate_menu_initial_render(v3_system: SystemFixture, snapshot):
    """Menu opens with 4 arc rings: Open, Close, Attack, Mains."""
    open_menu(v3_system)
    snapshot()


def test_noisegate_menu_tweak_open(v3_system: SystemFixture, nav_handler, snapshot):
    """Tweak1 raises the Open threshold toward 0 dB."""
    handler = v3_system.handler
    open_menu(v3_system)
    for _ in range(8):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot()


def test_noisegate_menu_nav_to_mains(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav cycles to the Mains slot (4th)."""
    handler = v3_system.handler
    open_menu(v3_system)
    for _ in range(3):
        nav_handler(1)
        handler.poll_lcd_updates()
    snapshot()