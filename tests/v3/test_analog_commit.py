# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""A bound (non-external) analog control commits its parameter like a bound
encoder does — one store, the echo only reconciles."""

import pytest

from common.parameter import Symbol
from emulator.controls import MockAnalogControl
from pistomp.controller import RoutingInfo
from pistomp.input.event import AnalogEvent
from rtmidi.midiconstants import CONTROL_CHANGE
from tests.types import SystemFixture


def _add_pedal(v3_system: SystemFixture, *, external: bool) -> MockAnalogControl:
    handler = v3_system.handler
    pedal = MockAnalogControl(midi_CC=75, midi_channel=0, control_type="EXPRESSION", id=0, midiout=None)
    hw = v3_system.hw
    hw.analog_controls.append(pedal)
    if external:
        hw.external_routing[pedal] = RoutingInfo.external("My MIDI Device")
    hw.register_controller(pedal)
    hw.register_sink(handler)
    return pedal


def test_bound_pedal_move_commits_param(v3_system: SystemFixture, make_plugin, make_parameter):
    handler, hw = v3_system.handler, v3_system.hw
    pedal = _add_pedal(v3_system, external=False)
    gain = make_parameter("Gain", "amp", value=0.0, minimum=0.0, maximum=1.0)
    gain.binding = "0:75"
    plugin = make_plugin("amp")
    plugin.parameters[Symbol("gain")] = gain
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()
    hw.midiout.send_message.reset_mock()
    committed: list[float] = []
    gain.on_commit(lambda p: committed.append(p.value))

    pedal.sink.handle(AnalogEvent(controller=pedal, raw_value=512, midi_value=64))

    assert committed  # committed, not echo-pending
    assert gain._confirmed == gain.value
    sent = hw.midiout.send_message.call_args[0][0]
    assert sent == [pedal.midi_channel | CONTROL_CHANGE, 75, 64]


def test_external_pedal_param_gets_no_sink(v3_system: SystemFixture):
    """An externally-routed pedal keeps its own CC: the commit sink stays None
    and the raw CC emit stays — the external port is the only transport."""
    handler = v3_system.handler
    hw = v3_system.hw
    pedal = _add_pedal(v3_system, external=True)
    handler.bind_current_pedalboard()

    param = pedal.parameter
    assert param is not None
    assert handler._sink_for(param) is None

    hw.midiout.send_message.reset_mock()
    pedal.sink.handle(AnalogEvent(controller=pedal, raw_value=512, midi_value=64))
    assert hw.midiout.send_message.call_args[0][0] == [pedal.midi_channel | CONTROL_CHANGE, 75, 64]
    assert param.value == pedal.midi_value  # untouched: no synthetic echo


def test_bound_pedal_bar_projects_param(v3_system: SystemFixture, make_plugin, make_parameter):
    """The LCD bar tracks the parameter (the owner), not the raw ADC."""
    handler, hw = v3_system.handler, v3_system.hw
    pedal = _add_pedal(v3_system, external=False)
    gain = make_parameter("Gain", "amp", value=0.25, minimum=0.0, maximum=1.0)
    gain.binding = "0:75"
    plugin = make_plugin("amp")
    plugin.parameters[Symbol("gain")] = gain
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    pedal.last_read = 1023  # raw ADC at the ceiling...
    gain.reconcile(0.25)  # ...while the param sits low

    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    handler.poll_lcd_updates()

    icon = next(i for i in handler.lcd.w_controls if i.object is pedal)
    assert icon.progress == pytest.approx(pedal.bar_midi_value() / 127.0)


def test_unbound_pedal_bar_projects_raw_adc(v3_system: SystemFixture):
    """Unbound: the ADC reading is the only fact, so the bar keeps it."""
    handler, hw = v3_system.handler, v3_system.hw
    pedal = _add_pedal(v3_system, external=False)
    pedal.last_read = 300
    from pistomp.analogmidicontrol import as_midi_value

    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    handler.poll_lcd_updates()

    icon = next(i for i in handler.lcd.w_controls if i.object is pedal)
    assert icon.progress == pytest.approx(as_midi_value(300) / 127.0)


def test_board_load_syncs_analog_after_loading_window_closes(v3_system, monkeypatch):
    handler = v3_system.handler
    pedalboard = handler.pedalboards["/path/to/rig.pedalboard"]
    observed_loading: list[bool] = []

    def sync_analog_controls() -> None:
        observed_loading.append(handler._is_pedalboard_loading)

    monkeypatch.setattr(handler.hardware, "sync_analog_controls", sync_analog_controls)
    handler._is_pedalboard_loading = True

    handler.set_current_pedalboard(pedalboard)

    assert observed_loading == [False]
