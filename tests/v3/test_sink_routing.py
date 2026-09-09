from __future__ import annotations

import pytest

from common.parameter import Parameter, PortInfo, Symbol
from pistomp.controller import RoutingInfo
from pistomp.input.event import SwitchEvent, SwitchEventKind
from rtmidi.midiconstants import CONTROL_CHANGE


def _plugin_with_bound_param(handler, make_plugin, binding: str):
    info: PortInfo = {"shortName": "Gain", "symbol": "gain", "ranges": {"minimum": 0.0, "maximum": 1.0}}
    param = Parameter(info, 0.5, binding, "/Amp")
    plugin = make_plugin("/Amp", parameters={Symbol("gain"): param})
    pb = handler.pedalboards["/path/to/rig.pedalboard"]
    pb.plugins = [plugin]
    handler.set_current_pedalboard(pb)
    return plugin, param


@pytest.mark.parametrize("kind", ["footswitch", "encoder"])
def test_external_control_never_carries_a_plugin_param(v3_system, make_plugin, kind):
    """An external control keeps its own CC, so the binder refuses the plugin
    binding. The sink must refuse it too, or the commit leaves by the external
    port instead of the WebSocket."""
    handler = v3_system.handler
    hw = v3_system.hw
    pool = hw.footswitches if kind == "footswitch" else hw.encoders
    control = next(c for c in pool if c.midi_CC is not None)
    binding = f"{control.midi_channel}:{control.midi_CC}"
    _, param = _plugin_with_bound_param(handler, make_plugin, binding)

    # The load reinits hardware, clearing routing. Route after it, as a board
    # declaring midi_port on this control would.
    hw.external_routing[control] = RoutingInfo.external("My MIDI Device")
    handler.bind_current_pedalboard()

    assert hw.controllers[binding] is control
    assert control.parameter is not param
    assert handler._sink_for(param) == handler._publish_plugin_param


def test_param_bound_to_encoder_leaves_as_midi_cc(v3_system, make_plugin):
    """A turn on a bound knob goes out as MIDI CC, not over the WebSocket."""
    handler, hw = v3_system.handler, v3_system.hw
    enc = next(e for e in hw.encoders if e.midi_CC is not None and e.parameter is None)
    _, param = _plugin_with_bound_param(handler, make_plugin, f"{enc.midi_channel}:{enc.midi_CC}")

    assert enc.parameter is param
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    hw.midiout.send_message.reset_mock()

    enc.refresh(1)

    sent = hw.midiout.send_message.call_args[0][0]
    assert sent[0] == enc.midi_channel | CONTROL_CHANGE
    assert sent[1] == enc.midi_CC


def _learn_footswitch_to_gain(v3_system, make_plugin, make_parameter, binding_range):
    """mod-ui's "advanced" MIDI-learn menu: a footswitch CC on a continuous
    param, with the user's own min/max as the two ends it toggles between."""
    handler, hw = v3_system.handler, v3_system.hw
    fs = hw.footswitches[0]
    gain = make_parameter("Gain", "amp", value=binding_range[0], minimum=0.0, maximum=10.0)
    gain.binding = f"{hw.midi_channel}:{fs.midi_CC}"
    plugin = make_plugin("amp")
    plugin.parameters[gain.symbol] = gain
    handler.current.pedalboard.plugins = [plugin]
    gain.set_binding_range(binding_range)
    handler.bind_current_pedalboard()
    return handler, hw, fs, gain


def test_footswitch_press_toggles_between_the_advanced_endpoints(v3_system, make_plugin, make_parameter):
    handler, hw, fs, gain = _learn_footswitch_to_gain(v3_system, make_plugin, make_parameter, (2.0, 8.0))

    handler.handle(SwitchEvent(controller=fs, kind=SwitchEventKind.PRESS, timestamp=1.0))
    assert gain.value == 8.0
    assert hw.midiout.send_message.call_args[0][0][2] == 127

    handler.handle(SwitchEvent(controller=fs, kind=SwitchEventKind.PRESS, timestamp=2.0))
    assert gain.value == 2.0
    assert hw.midiout.send_message.call_args[0][0][2] == 0


def test_switch_sink_midrange_value_uses_websocket(v3_system, make_plugin, make_parameter):
    """A footswitch CC has only endpoint codes, so a mid-range sink value uses WebSocket."""
    handler, hw, fs, gain = _learn_footswitch_to_gain(v3_system, make_plugin, make_parameter, (2.0, 8.0))
    hw.midiout.send_message.reset_mock()

    handler.parameter_value_commit(gain, 5.0)

    hw.midiout.send_message.assert_not_called()
    assert v3_system.ws_bridge.sent_values_for("amp", gain.symbol) == [5.0]


def test_switch_sink_endpoint_value_uses_cc(v3_system, make_plugin, make_parameter):
    handler, hw, fs, gain = _learn_footswitch_to_gain(v3_system, make_plugin, make_parameter, (2.0, 8.0))
    hw.midiout.send_message.reset_mock()

    handler.parameter_value_commit(gain, 8.0)

    assert hw.midiout.send_message.call_args[0][0][2] == 127
    assert v3_system.ws_bridge.sent_values_for("amp", gain.symbol) == []


@pytest.mark.parametrize("value", [5.0, 8.0])
def test_loading_window_refuses_switch_sink_publishes(v3_system, make_plugin, make_parameter, value):
    """A load window refuses switch transport sends and keeps the confirmed value."""
    handler, hw, fs, gain = _learn_footswitch_to_gain(v3_system, make_plugin, make_parameter, (2.0, 8.0))
    handler._is_pedalboard_loading = True
    hw.midiout.send_message.reset_mock()

    handler.parameter_value_commit(gain, value)

    hw.midiout.send_message.assert_not_called()
    assert gain.value == 2.0  # rolled back, _confirmed un-advanced
    assert gain._confirmed == 2.0


def test_loading_window_refuses_encoder_cc_publishes(v3_system, make_plugin):
    handler, hw = v3_system.handler, v3_system.hw
    enc = next(e for e in hw.encoders if e.midi_CC is not None and e.parameter is None)
    _, param = _plugin_with_bound_param(handler, make_plugin, f"{enc.midi_channel}:{enc.midi_CC}")
    handler._is_pedalboard_loading = True
    hw.midiout.send_message.reset_mock()

    handler.parameter_value_commit(param, 0.75)

    hw.midiout.send_message.assert_not_called()
    assert param.value == 0.5


def test_physical_encoder_bound_param_rides_cc(v3_system, make_plugin):
    """A physical encoder edit uses MIDI CC, not the WebSocket transport."""
    handler, hw = v3_system.handler, v3_system.hw
    enc = next(e for e in hw.encoders if e.midi_CC is not None and e.parameter is None)
    _, param = _plugin_with_bound_param(handler, make_plugin, f"{enc.midi_channel}:{enc.midi_CC}")
    hw.midiout.send_message.reset_mock()

    handler.parameter_value_commit(param, 0.75)

    assert hw.midiout.send_message.call_args[0][0][1] == enc.midi_CC
    assert v3_system.ws_bridge.sent_values_for("Amp", param.symbol) == []
