from __future__ import annotations

import pytest
from common.parameter import Parameter, PortInfo, Symbol
from modalapi.plugin import Plugin
from tests.types import SystemFixture
from uilib.parameterdialog import Parameterdialog


def _make_plugin(make_plugin, instance_id="fuzz", bypassed=False, binding=None) -> Plugin:
    gain_info: PortInfo = {"shortName": "Gain", "symbol": "gain", "ranges": {"minimum": 0.0, "maximum": 1.0}}
    gain_param = Parameter(gain_info, 0.5, binding, instance_id)
    plugin = make_plugin(instance_id, bypassed=bypassed, parameters={Symbol("gain"): gain_param})
    return plugin


def _install(v3_system: SystemFixture, make_plugin, instance_id="fuzz", binding=None) -> Plugin:
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current
    plugin = _make_plugin(make_plugin, instance_id, bypassed=False, binding=binding)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    return plugin


def test_parameterdialog_nav_turn_updates_value_and_sends_ws(v3_system: SystemFixture, make_plugin):
    """When a parameter is edited in Parameterdialog with NAV encoder, it updates value and queues param_set."""
    plugin = _install(v3_system, make_plugin)
    param = plugin.parameters[Symbol("gain")]
    dialog = v3_system.handler.lcd.draw_parameter_dialog(param)
    assert isinstance(dialog, Parameterdialog)
    assert param.value == 0.5

    # Turn NAV forward
    dialog.input_step(1, 1)
    new_val = param.value
    assert new_val > 0.5

    # Outbound queue should have param_set
    assert len(v3_system.ws_bridge.sent) > 0
    msg = v3_system.ws_bridge.sent[-1]
    assert msg.startswith("param_set /graph/fuzz/gain")


def test_parameterdialog_rollback_when_loading_is_active(v3_system: SystemFixture, make_plugin):
    """If _is_pedalboard_loading is True, sink returns False and parameter reverts to confirmed."""
    plugin = _install(v3_system, make_plugin)
    param = plugin.parameters[Symbol("gain")]
    dialog = v3_system.handler.lcd.draw_parameter_dialog(param)
    assert isinstance(dialog, Parameterdialog)
    assert param.value == 0.5

    # Simulate loading state stuck True
    v3_system.handler._is_pedalboard_loading = True

    dialog.input_step(1, 1)

    # Because loading is active, commit rolls back to 0.5
    assert param.value == 0.5
    assert dialog.last_param_value == 0.5


def test_midi_cc_bound_param_confirms_on_cc_emit(v3_system: SystemFixture, make_plugin):
    """For a MIDI CC-bound parameter, _publish_cc emits CC. Because mod-host emits no echo
    for CC, a successful CC emit MUST confirm the value so it does not stay unconfirmed."""
    hw = v3_system.hw
    enc1 = next(e for e in hw.encoders if e.id == 1)
    binding = f"{enc1.midi_channel}:{enc1.midi_CC}"
    hw.controllers[binding] = enc1

    plugin = _install(v3_system, make_plugin, binding=binding)
    param = plugin.parameters[Symbol("gain")]
    enc1.bind_to_parameter(param)
    dialog = v3_system.handler.lcd.draw_parameter_dialog(param)
    assert isinstance(dialog, Parameterdialog)

    # Initial state
    assert param.value == 0.5
    assert param._confirmed == 0.5

    # Turn encoder in dialog
    dialog.input_step(1, 1)
    new_val = param.value
    assert new_val > 0.5

    # Verify MIDI CC was emitted
    hw.midiout.send_message.assert_called()

    # The confirmed value should be updated because CC emit has no remote echo
    assert param._confirmed == pytest.approx(new_val, abs=1e-4)
