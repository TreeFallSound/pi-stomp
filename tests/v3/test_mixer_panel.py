"""Snapshot sagas for the Mixer Panel v2.

To regenerate:
    uv run pytest tests/v3/test_mixer_panel.py --snapshot-update
"""

from __future__ import annotations

from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.mixer.panel import MixerPanel
from plugins.pinned_params import MOD_MIXER_URI
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from common.parameter import BYPASS_SYMBOL, PortInfo, Symbol


class _FakeEnc(Controller):
    def __init__(self, id: int):
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id


def _param(symbol: str, value: float, minimum: float = 0.0, maximum: float = 1.0,
           default: float = 0.75, instance_id: str = "mixer") -> Parameter:
    info: PortInfo = {"shortName": symbol, "symbol": symbol,
                      "ranges": {"minimum": minimum, "maximum": maximum, "default": default}}
    return Parameter(info, value, None, instance_id)


def make_mixer_plugin(instance_id: str = "mixer") -> Plugin:
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter(
            {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1, "default": 0}},
            False, None, instance_id),
    }
    for i in range(4):
        n = i + 1
        params[Symbol(f"Volume{n}")] = _param(f"Volume{n}", 0.75, 0.0, 1.0, 0.75, instance_id)
        params[Symbol(f"Panning{n}")] = _param(f"Panning{n}", 0.0, -1.0, 1.0, 0.0, instance_id)
        params[Symbol(f"Solo{n}")] = _param(f"Solo{n}", 0.0, 0.0, 1.0, 0.0, instance_id)
        params[Symbol(f"Mute{n}")] = _param(f"Mute{n}", 0.0, 0.0, 1.0, 0.0, instance_id)
        params[Symbol(f"Alt{n}")] = _param(f"Alt{n}", 0.0, 0.0, 1.0, 0.0, instance_id)
    params[Symbol("MasterVolume")] = _param("MasterVolume", 0.75, 0.0, 1.0, 0.75, instance_id)
    params[Symbol("AltVolume")] = _param("AltVolume", 0.5, 0.0, 1.0, 0.5, instance_id)
    plugin = Plugin(instance_id, params, {}, "Mixer", uri=MOD_MIXER_URI)
    plugin.has_footswitch = False
    plugin.pedalboard_snapshot = {sym: float(p.value) if p.value is not None else 0.0
                                  for sym, p in params.items()}
    return plugin


def open_panel(v3_system: SystemFixture) -> Plugin:
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current
    plugin = make_mixer_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    handler.show_fullscreen_panel(plugin, MixerPanel)
    handler.poll_lcd_updates()
    return plugin


def nav(nav_handler, steps: int) -> None:
    direction = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        nav_handler(direction)


def tweak(handler, idx: int, rotations: int) -> bool:
    return handler.handle(EncoderEvent(controller=_FakeEnc(idx), rotations=rotations))


def short_press(handler) -> None:
    nav_click(handler)


def long_press(handler) -> None:
    nav_click(handler, long=True)
    nav_click(handler)


def test_mixer_initial_render(v3_system: SystemFixture, snapshot):
    open_panel(v3_system)
    snapshot("opened")


def test_mixer_nav_and_tweaks(v3_system: SystemFixture, nav_handler, snapshot):
    handler = v3_system.handler
    plugin = open_panel(v3_system)
    snapshot("ch1_vol")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("ch1_s")

    nav(nav_handler, 3)
    handler.poll_lcd_updates()
    snapshot("ch1_pan")

    nav(nav_handler, 16)
    handler.poll_lcd_updates()
    snapshot("master")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("alt")

    for _ in range(4):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("alt_up")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "AltVolume")
    assert len(sent) > 0 and sent[-1] > 0.5


def test_mixer_toggle_and_resets(v3_system: SystemFixture, nav_handler, snapshot):
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    nav(nav_handler, 2)  # Ch1_Vol → Ch1_M
    handler.poll_lcd_updates()
    snapshot("ch1_m_off")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("ch1_m_on")
    assert v3_system.ws_bridge.sent_values_for(plugin.instance_id, "Mute1")[-1] == 1.0

    nav(nav_handler, -2)  # back to Ch1_Vol
    for _ in range(4):
        tweak(handler, 1, -1)
    handler.poll_lcd_updates()
    snapshot("ch1_vol_down")

    nav_click(handler, long=True)
    handler.poll_lcd_updates()
    snapshot("ch1_vol_reset")
    assert plugin.parameters[Symbol("Volume1")].value == 0.75

    nav(nav_handler, 4)  # Ch1_Vol → Ch1_Pan
    for _ in range(4):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("ch1_pan_right")

    nav_click(handler, long=True)
    handler.poll_lcd_updates()
    snapshot("ch1_pan_reset")
    assert plugin.parameters[Symbol("Panning1")].value == 0.0


def test_mixer_chrome(v3_system: SystemFixture, nav_handler, snapshot):
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    for _ in range(4):
        tweak(handler, 1, -1)

    nav(nav_handler, 22)
    handler.poll_lcd_updates()
    snapshot("back")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("bypass")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("bypassed")
    assert plugin.is_bypassed()

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("re_enabled")
    assert not plugin.is_bypassed()

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("reset")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("after_reset")
    assert v3_system.ws_bridge.sent_values_for(plugin.instance_id, "Volume1")[-1] == 0.75
