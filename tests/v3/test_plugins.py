"""Controller binding, plugin bypass toggle, preset plugin update, and parameter editing."""

from unittest.mock import MagicMock

import pistomp.switchstate as switchstate
from pistomp.encodermidicontrol import EncoderMidiControl
import common.token as Token
from tests.types import SystemFixture


# ---------------------------------------------------------------------------
# Controller binding
# ---------------------------------------------------------------------------


def test_v3_bind_footswitch_to_plugin(v3_system: SystemFixture, make_plugin):
    """bind_current_pedalboard() links a footswitch to a plugin's :bypass param."""
    handler, hw, _, _, _ = v3_system

    fs0 = hw.footswitches[0]
    binding_key = next(k for k, v in hw.controllers.items() if v is fs0)

    plugin = make_plugin("fuzz")
    plugin.parameters[":bypass"].binding = binding_key

    assert handler.current
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    assert fs0.parameter is plugin.parameters[":bypass"]
    assert plugin.has_footswitch is True
    assert plugin in [p for p in handler.current.pedalboard.plugins if p.has_footswitch]


def test_v3_bind_encoder_midi_to_plugin(v3_system: SystemFixture, make_plugin):
    """bind_current_pedalboard() populates analog_controllers for EncoderMidiControl bindings."""
    handler, hw, _, _, _ = v3_system

    enc = next((v for v in hw.controllers.values() if isinstance(v, EncoderMidiControl)), None)
    if enc is None:
        import pytest

        pytest.skip("No EncoderMidiControl in default config")

    binding_key = next(k for k, v in hw.controllers.items() if v is enc)

    plugin = make_plugin("wah")
    plugin.parameters[":bypass"].binding = binding_key

    assert handler.current
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    assert any("wah" in k for k in handler.current.analog_controllers)


def test_v3_bind_volume_encoder_populates_analog_controllers(v3_system: SystemFixture):
    """The VOLUME-type encoder always appears in analog_controllers after binding."""
    handler, hw, _, _, _ = v3_system

    assert handler.current
    handler.current.pedalboard.plugins = []

    handler.bind_current_pedalboard()

    assert Token.VOLUME in handler.current.analog_controllers


# ---------------------------------------------------------------------------
# Plugin bypass
# ---------------------------------------------------------------------------


def test_v3_toggle_plugin_bypass_direct(v3_system: SystemFixture, make_plugin, snapshot, get_urls):
    """Non-footswitch plugin: toggle_plugin_bypass() sends pi_stomp_set POST and flips bypass."""
    handler, hw, _, _, mock_post = v3_system

    assert handler.current
    assert handler.lcd

    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # widget=MagicMock() because the real LCD widget is owned by the panel stack;
    # we test the handler logic here, not the widget rendering path
    handler.toggle_plugin_bypass(MagicMock(), plugin)

    assert any("pi_stomp_set" in u for u in get_urls(mock_post))
    assert plugin.is_bypassed()
    snapshot()


def test_v3_toggle_plugin_bypass_via_footswitch(v3_system: SystemFixture, make_plugin, get_urls):
    """Plugin with has_footswitch: toggle_plugin_bypass() routes through footswitch.pressed()."""
    handler, hw, _, _, mock_post = v3_system

    assert handler.current

    plugin = make_plugin("fuzz", has_footswitch=True)
    plugin.controllers = [hw.footswitches[0]]
    handler.current.pedalboard.plugins = [plugin]

    handler.toggle_plugin_bypass(None, plugin)

    assert not any("pi_stomp_set" in u for u in get_urls(mock_post))
    assert hw.footswitches[0].enabled is True


def test_v3_preset_change_plugin_update(v3_system: SystemFixture, make_plugin, snapshot):
    """preset_change_plugin_update() GETs bypass state for each plugin and refreshes LCD."""
    handler, hw, _, mock_get, _ = v3_system

    assert handler.current
    assert handler.lcd

    plugin = make_plugin("fuzz", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "true" if "pi_stomp_get" in url else "{}"
        return resp

    mock_get.side_effect = get_side_effect

    handler.preset_change_plugin_update()

    assert plugin.is_bypassed()
    snapshot()


# ---------------------------------------------------------------------------
# Parameter editing
# ---------------------------------------------------------------------------


def test_v3_parameter_edit(v3_system: SystemFixture, make_parameter, snapshot):
    """Full parameter-edit flow: navigate to plugin, open dialog, tweak, close."""
    handler, hw, _, _, mock_post = v3_system

    assert handler.current
    assert handler.lcd

    gain_param = make_parameter("Gain", "delay", value=0.5)
    from tests.integration.conftest import PROJECT_ROOT  # noqa: F401 — ensure import path works
    from modalapi.plugin import Plugin
    from modalapi.parameter import Parameter

    bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
    bp = Parameter(bypass_info, False, None, "delay")
    plugin = Plugin("delay", {"gain": gain_param, ":bypass": bp}, {}, "Delay")

    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # wrench → pedalboard → preset → plugin
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)

    handler.universal_encoder_sw(switchstate.Value.LONGPRESSED)
    snapshot("param_menu")

    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot("param_dialog")

    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    snapshot("param_tweaked")

    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    handler.poll_lcd_updates()
    snapshot("param_closed")


def test_v3_parameter_midi_change(v3_system: SystemFixture, make_parameter, snapshot):
    """parameter_midi_change() draws a parameter dialog and steps the value."""
    handler, _, _, _, _ = v3_system

    param = make_parameter("Gain", "delay", value=0.5)
    handler.parameter_midi_change(param, 1)
    snapshot()
