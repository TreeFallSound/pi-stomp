"""ControllerManager.bind() — controller→parameter binding, version-flagged."""

from unittest.mock import MagicMock

import common.token as Token
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.controller_manager import ControllerManager
from pistomp.current import Current


def _make_current() -> Current:
    """A Current with an empty (truthy) pedalboard — no plugin bindings."""
    current = Current(MagicMock())
    current.pedalboard.plugins = []
    return current


class _Ctl:
    """Minimal internally-routed controller — v1 config supplies no VOLUME control
    to use directly."""

    def __init__(self, type):
        self.type = type
        self.parameter = "bound"
        self.midi_CC = None


def test_bind_preserves_volume_binding_clears_others():
    """Controller.type is a class-level default, so the volume guard is type-safe:
    bind() clears every controller's parameter except the VOLUME control's."""
    vol = _Ctl(Token.VOLUME)
    knob = _Ctl(Token.KNOB)
    hw = MagicMock()
    hw.controllers = {"0:7": vol, "0:8": knob}
    hw.encoders = []
    hw.is_external.return_value = False

    current = _make_current()
    ControllerManager(hw).bind(current)

    assert vol.parameter == "bound"
    assert knob.parameter is None


def _external_analog(midi_cc=75, midi_channel=0, ctrl_id=3):
    return AnalogMidiControl(MagicMock(), 0, 16, midi_cc, midi_channel, Token.KNOB, id=ctrl_id, cfg={})


def test_external_controller_bound_and_displayed():
    """An externally-routed control isn't bound to any plugin parameter, so the
    plugin loop skips it. The external block binds a synthetic parameter and adds
    an "External" display entry — otherwise it'd be invisible on the LCD. Routing
    is read from the hardware registry, not the control."""
    ctrl = _external_analog()
    hw = MagicMock()
    hw.controllers = {"0:75": ctrl}
    hw.encoders = []
    hw.is_external.return_value = True
    hw.external_port_name.return_value = "c4"
    hw.create_external_parameter.return_value = "SYNTH_PARAM"

    current = _make_current()
    ControllerManager(hw).bind(current)

    assert ctrl.parameter == "SYNTH_PARAM"
    entry = current.analog_controllers["0:75"]
    assert entry.get("category") == "External"
    assert entry.get("port_name") == "c4"
    assert entry.get("midi_cc") == 75
