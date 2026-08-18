"""ControllerManager.bind() — controller→parameter binding, version-flagged."""

from typing import cast
from unittest.mock import MagicMock

import common.token as Token
from common.contexts import ControlClass, EventKind, MidiCcEffect, ShadowState
from common.parameter import Parameter, PortInfo, Symbol
from modalapi.plugin import Plugin
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
        self._unsub_param = None

    def unbind_from_parameter(self) -> None:
        self.parameter = None


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
    manager = ControllerManager(hw)
    manager.bind(current)

    assert ctrl.parameter == "SYNTH_PARAM"
    entry = current.analog_controllers["0:75"]
    assert entry.get("category") == "External"
    assert entry.get("port_name") == "c4"
    assert entry.get("midi_cc") == 75

    rows = manager.effective_table.layers[0].rows.get((ControlClass.ANALOG, EventKind.ROTATE), [])
    cc_rows = [r for r in rows if any(isinstance(e, MidiCcEffect) for e in r.effects)]
    assert len(cc_rows) == 1
    assert cc_rows[0].control.id == "0:75"

    rows = manager.effective_table.layers[0].rows.get((ControlClass.ANALOG, EventKind.ROTATE), [])
    cc_rows = [r for r in rows if any(isinstance(e, MidiCcEffect) for e in r.effects)]
    assert len(cc_rows) == 1
    assert cc_rows[0].control.id == "0:75"


def test_orphaned_ttl_binding_recorded_in_effective_table():
    """A TTL param.binding with no matching physical controller is dropped
    silently by the legacy path but must surface as an ORPHANED table row."""
    info: PortInfo = {"shortName": "gain", "symbol": "gain", "ranges": {"minimum": 0, "maximum": 1}}
    param = Parameter(info, 0.5, "0:99", "dist")
    plugin = Plugin("dist", {Symbol("gain"): param}, {}, "Distortion")

    hw = MagicMock()
    hw.controllers = {}
    hw.encoders = []
    hw.is_external.return_value = False

    current = _make_current()
    current.pedalboard.plugins = cast(list[Plugin], [plugin])
    manager = ControllerManager(hw)
    manager.bind(current)

    rows = manager.effective_table.layers[0].rows[(ControlClass.ANALOG, EventKind.ROTATE)]
    orphaned = [r for r in rows if r.control.id == "0:99"]
    assert len(orphaned) == 1
    assert orphaned[0].shadow_state == ShadowState.ORPHANED


def test_encoder_longpress_builds_callback_effect_row():
    """An encoder with a configured longpress produces a CallbackEffect
    LONGPRESS row in the PEDALBOARD layer."""
    from common.contexts import CallbackEffect
    from pistomp.encoder_controller import EncoderController

    enc = MagicMock(spec=EncoderController)
    enc.midi_channel = 0
    enc.midi_CC = 70
    enc.longpress = "next_snapshot"

    vol = MagicMock(spec=EncoderController)
    vol.midi_channel = 0
    vol.midi_CC = None  # volume encoder has no midi_CC
    vol.longpress = None

    hw = MagicMock()
    hw.controllers = {}
    hw.encoders = [enc, vol]
    hw.is_external.return_value = False

    current = _make_current()
    manager = ControllerManager(hw)
    manager.bind(current)

    rows = manager.effective_table.layers[0].rows.get((ControlClass.ANALOG, EventKind.LONGPRESS), [])
    assert len(rows) == 1
    assert rows[0].control.id == "0:70"
    effects = [e for e in rows[0].effects if isinstance(e, CallbackEffect)]
    assert len(effects) == 1
    assert effects[0].name == "next_snapshot"
