"""External controllers must be bound + displayed on v1 (mod.py), as on v3.

An externally-routed control isn't bound to any plugin parameter, so the plugin
loop skips it. Without the dedicated external block it stays invisible: no
synthetic parameter, no entry in analog_controllers for the LCD.
"""

from unittest.mock import MagicMock

import common.token as Token
from modalapi.external_midi import ExternalMidiOut
from modalapi.mod import Mod
from pistomp.analogmidicontrol import AnalogMidiControl


def _external_analog(midi_cc=75, midi_channel=0, ctrl_id=3):
    ext_out = ExternalMidiOut(MagicMock(), "c4", MagicMock())
    return AnalogMidiControl(MagicMock(), 0, 16, midi_cc, midi_channel, ext_out, Token.KNOB, id=ctrl_id, cfg={})


def test_external_controller_bound_and_displayed():
    h = object.__new__(Mod)
    h.wifi_manager = None
    h.ws_bridge = None
    ctrl = _external_analog()
    h.hardware = MagicMock()
    h.hardware.controllers = {"0:75": ctrl}
    h.hardware.create_external_parameter.return_value = "SYNTH_PARAM"
    h.current = MagicMock()
    h.current.pedalboard.plugins = []

    h.bind_current_pedalboard()

    assert ctrl.parameter == "SYNTH_PARAM"
    entry = h.current.analog_controllers["0:75"]
    assert entry["category"] == "External"
    assert entry["port_name"] == "c4"
