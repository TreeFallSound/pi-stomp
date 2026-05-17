"""Controller binding, plugin bypass toggle, preset plugin update, and parameter editing."""

from unittest.mock import MagicMock

import pistomp.switchstate as switchstate
from pistomp.encoder_controller import EncoderController
import common.token as Token
from tests.types import SystemFixture


# ---------------------------------------------------------------------------
# Controller binding
# ---------------------------------------------------------------------------


def test_v3_bind_footswitch_to_plugin(v3_system: SystemFixture, make_plugin):
    """bind_current_pedalboard() links a footswitch to a plugin's :bypass param."""
    handler = v3_system.handler
    hw = v3_system.hw

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
    """bind_current_pedalboard() populates analog_controllers for EncoderController bindings."""
    handler = v3_system.handler
    hw = v3_system.hw

    enc = next((v for v in hw.controllers.values() if isinstance(v, EncoderController)), None)
    if enc is None:
        import pytest

        pytest.skip("No EncoderController in default config")

    binding_key = next(k for k, v in hw.controllers.items() if v is enc)

    plugin = make_plugin("wah")
    plugin.parameters[":bypass"].binding = binding_key

    assert handler.current
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    assert any("wah" in k for k in handler.current.analog_controllers)


def test_v3_bind_volume_encoder_populates_analog_controllers(v3_system: SystemFixture):
    """The VOLUME-type encoder always appears in analog_controllers after binding."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    handler.current.pedalboard.plugins = []

    handler.bind_current_pedalboard()

    assert Token.VOLUME in handler.current.analog_controllers


# ---------------------------------------------------------------------------
# Plugin bypass
# ---------------------------------------------------------------------------


def test_v3_toggle_plugin_bypass_via_footswitch_sends_midi_cc(v3_system: SystemFixture, make_plugin):
    """Footswitch-bound plugin: toggle_plugin_bypass() sends MIDI CC, not a WebSocket message.

    MOD-UI receives the bypass change via its MIDI input; ws_bridge is not involved.
    """
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    fs = hw.footswitches[0]
    assert fs.midi_CC is not None, "test requires a footswitch with a midi_CC binding"

    plugin = make_plugin("fuzz", has_footswitch=True)
    plugin.controllers = [fs]
    handler.current.pedalboard.plugins = [plugin]

    handler.toggle_plugin_bypass(None, plugin)

    fs.midiout.send_message.assert_called_once()
    sent_cc = fs.midiout.send_message.call_args[0][0]
    assert sent_cc[1] == fs.midi_CC
    assert ws_bridge.sent_values_for("fuzz", ":bypass") == []


def test_v3_toggle_plugin_bypass_no_footswitch_sends_websocket(v3_system: SystemFixture, make_plugin, snapshot):
    """Non-footswitch plugin: toggle_plugin_bypass() sends :bypass via WebSocket and flips state."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    assert handler.lcd

    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("active")

    widget = next(w for w in handler.lcd.w_plugins if w.object is plugin)
    handler.toggle_plugin_bypass(widget, plugin)

    assert ws_bridge.sent_values_for("fuzz", ":bypass") == [1.0]
    assert plugin.is_bypassed()
    snapshot("bypassed")


def test_v3_toggle_plugin_bypass_via_footswitch(v3_system: SystemFixture, make_plugin, get_urls):
    """Plugin with has_footswitch: toggle_plugin_bypass() routes through footswitch.pressed()."""
    handler = v3_system.handler
    hw = v3_system.hw
    mock_post = v3_system.mock_post

    assert handler.current

    plugin = make_plugin("fuzz", has_footswitch=True)
    plugin.controllers = [hw.footswitches[0]]
    handler.current.pedalboard.plugins = [plugin]

    handler.toggle_plugin_bypass(None, plugin)

    assert not any("pi_stomp_set" in u for u in get_urls(mock_post))
    assert hw.footswitches[0].toggled is True


def test_v3_preset_change_plugin_update(v3_system: SystemFixture, make_plugin, snapshot):
    """preset_change_plugin_update() GETs bypass state for each plugin and refreshes LCD."""
    handler = v3_system.handler
    hw = v3_system.hw
    mock_get = v3_system.mock_get

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
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

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

    # parameter_value_commit fires on every encoder step, so 3 steps → 3 messages
    sent = ws_bridge.sent_values_for("delay", "gain")
    assert len(sent) == 3
    assert sent[-1] == gain_param.value


def test_v3_parameter_midi_change(v3_system: SystemFixture, make_parameter, snapshot):
    """parameter_midi_change() draws a parameter dialog and steps the value."""
    handler = v3_system.handler

    param = make_parameter("Gain", "delay", value=0.5)
    handler.parameter_midi_change(param, 1)
    snapshot()


# ---------------------------------------------------------------------------
# Plugin bypass sync (inbound websocket events from mod-ui)
# ---------------------------------------------------------------------------


def test_v3_handle_bypass_event_updates_plugin(v3_system: SystemFixture, make_plugin, snapshot):
    """Inbound param_set :bypass from mod-ui updates plugin state and redraws LCD."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_modui_changes()

    assert plugin.is_bypassed()
    snapshot()


def test_v3_bypass_echo_is_idempotent(v3_system: SystemFixture, make_plugin, snapshot):
    """After toggle_plugin_bypass, the mod-ui echo doesn't corrupt state or LCD."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("before")

    widget = next(w for w in handler.lcd.w_plugins if w.object is plugin)
    handler.toggle_plugin_bypass(widget, plugin)
    assert plugin.is_bypassed()
    snapshot("after_toggle")

    ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_modui_changes()

    assert plugin.is_bypassed()
    snapshot("after_toggle")  # reuse the same baseline — echo must not change the LCD


def test_v3_bypass_event_unknown_plugin_is_ignored(v3_system: SystemFixture, make_plugin):
    """Bypass event for an unknown instance ID doesn't raise or corrupt state."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject("param_set /graph/not_a_real_plugin :bypass 1.0")
    handler.poll_modui_changes()

    assert not plugin.is_bypassed()
