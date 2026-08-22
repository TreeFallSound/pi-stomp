"""Unit tests for pistomp.hardware.Hardware helpers."""

import logging
from unittest.mock import MagicMock

import pytest

from pistomp.config.model import ControlType
from modalapi.external_midi import ExternalMidiManager
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.encoder_controller import EncoderController
from pistomp.footswitch import Footswitch
from pistomp.hardware import Hardware
from pistomp.config.adapt_v1 import adapt
from pistomp.config.schema_v1 import merge, parse


class _Ctl:
    """Hashable double; SimpleNamespace can't key the registry (defines __eq__)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class _StubHardware(Hardware):
    """Concrete subclass so object.__new__ works (Hardware is abstract)."""

    def init_analog_controls(self): ...
    def init_encoders(self): ...
    def init_footswitches(self): ...
    def init_relays(self): ...
    def cleanup(self): ...
    def test(self): ...
    def add_encoder(self, *a, **k):
        raise NotImplementedError


def _validate(hw, port_name):
    return hw._Hardware__validate_midi_port(port_name)


class TestValidateMidiPort:
    def test_known_port_returned(self):
        """A valid device name passes through unchanged."""
        hw = object.__new__(_StubHardware)
        hw.external_midi = ExternalMidiManager()
        assert _validate(hw, "Source Audio C4 Synth") == "Source Audio C4 Synth"

    def test_uninitialized_external_midi_logs_warning_not_error(self, caplog):
        hw = object.__new__(_StubHardware)
        hw.external_midi = None

        with caplog.at_level(logging.WARNING):
            assert _validate(hw, "dev") is None

        recs = [r for r in caplog.records if "dev" in r.getMessage()]
        assert recs
        assert all(r.levelno == logging.WARNING for r in recs)


@pytest.fixture
def routed_hw(monkeypatch):
    """A Hardware with one encoder, analog control, and footswitch, and a 'My MIDI Device' external port."""
    mock_out = MagicMock()
    mock_out.get_ports.return_value = ["My MIDI Device"]
    monkeypatch.setattr("modalapi.external_midi.rtmidi.MidiOut", lambda *a, **k: mock_out)

    hw = object.__new__(_StubHardware)
    hw.midiout = MagicMock(name="virtual")
    hw.external_midi = ExternalMidiManager()
    hw.external_midi.update_config({"enabled": True})
    hw.handler = MagicMock()
    hw.relay = None

    hw.encoders = [EncoderController(d_pin=None, clk_pin=None, midi_CC=70, midi_channel=13, id=1)]
    hw.analog_controls = [AnalogMidiControl(None, 0, 16, 75, 13, ControlType.KNOB, id=2)]
    hw.footswitches = [Footswitch(0, None, None, 60, 13, refresh_callback=lambda **k: None)]
    hw.controllers = {}
    hw.external_routing = {}
    return hw


DEFAULT_CFG = {
    "hardware": {
        "version": 3.0,
        "midi": {"channel": 14},
        "footswitches": [{"id": 0, "adc_input": 0, "midi_CC": 60}],
        "encoders": [{"id": 1, "midi_CC": 70}],
        "analog_controllers": [{"id": 2, "adc_input": 5, "midi_CC": 75}],
    }
}


def _resolved(pedalboard_cfg=None):
    overlay = parse(pedalboard_cfg, "<test>") if pedalboard_cfg is not None else None
    return adapt(merge(parse(DEFAULT_CFG, "<test>"), overlay))


def _route(hw, cfg):
    hw.reinit(_resolved(cfg))


class TestApplyMidiRouting:
    def test_footswitch_routed_to_external_port(self, routed_hw):
        """A footswitch with midi_port routes to its external port."""
        cfg = {"hardware": {"footswitches": [{"id": 0, "midi_port": "My MIDI Device", "midi_channel": 3}]}}
        _route(routed_hw, cfg)
        fs = routed_hw.footswitches[0]
        assert routed_hw.is_external(fs)
        assert routed_hw.external_port_name(fs) == "My MIDI Device"
        assert routed_hw.external_routing[fs].port_name == "My MIDI Device"

    def test_unrouted_control_is_internal(self, routed_hw):
        """No midi_port → internal: absent from the registry, sends to virtual."""
        _route(routed_hw, {"hardware": {"footswitches": [{"id": 0}]}})
        fs = routed_hw.footswitches[0]
        assert not routed_hw.is_external(fs)
        assert routed_hw.external_port_name(fs) is None
        assert fs not in routed_hw.external_routing

    def test_routing_overlay_clears_external(self, routed_hw):
        """A later pedalboard with no midi_port removes a prior external routing."""
        _route(routed_hw, {"hardware": {"footswitches": [{"id": 0, "midi_port": "My MIDI Device", "midi_channel": 3}]}})
        fs = routed_hw.footswitches[0]
        assert routed_hw.is_external(fs)
        _route(routed_hw, {"hardware": {"footswitches": [{"id": 0}]}})
        assert not routed_hw.is_external(fs)

    def test_encoder_and_analog_routed_to_external_port(self, routed_hw):
        cfg = {
            "hardware": {
                "encoders": [{"id": 1, "midi_port": "My MIDI Device", "midi_channel": 3}],
                "analog_controllers": [{"id": 2, "midi_port": "My MIDI Device", "midi_channel": 3}],
            }
        }
        _route(routed_hw, cfg)
        assert routed_hw.is_external(routed_hw.encoders[0])
        assert routed_hw.is_external(routed_hw.analog_controls[0])
        assert routed_hw.external_port_name(routed_hw.encoders[0]) == "My MIDI Device"
        assert routed_hw.external_port_name(routed_hw.analog_controls[0]) == "My MIDI Device"

    def test_encoder_midi_cc_override(self, routed_hw):
        _route(routed_hw, {"hardware": {"encoders": [{"id": 1, "midi_CC": 99}]}})
        assert routed_hw.encoders[0].midi_CC == 99

    def test_encoder_midi_channel_override(self, routed_hw):
        """External device may be on a different channel than the hardware default."""
        _route(routed_hw, {"hardware": {"encoders": [{"id": 1, "midi_channel": 0}]}})
        assert routed_hw.encoders[0].midi_channel == 0

    def test_external_port_opened_eagerly(self, routed_hw):
        """The external port is opened at routing time, not lazily inside the poll loop."""
        _route(routed_hw, {"hardware": {"footswitches": [{"id": 0, "midi_port": "My MIDI Device", "midi_channel": 3}]}})
        assert "My MIDI Device" in routed_hw.external_midi.midi_ports

    def test_default_config_routing_applies_without_a_pedalboard(self, routed_hw):
        """Routing comes from default_config.yml too, not only a pedalboard overlay."""
        default = {
            "hardware": {
                **DEFAULT_CFG["hardware"],
                "footswitches": [
                    {"id": 0, "adc_input": 0, "midi_CC": 60,
                     "midi_port": "My MIDI Device", "midi_channel": 3}
                ],
            }
        }
        routed_hw.reinit(adapt(merge(parse(default, "<test>"))))
        assert routed_hw.is_external(routed_hw.footswitches[0])


def test_analog_disable_removes_controller(routed_hw):
    analog = routed_hw.analog_controls[0]
    cfg = {"hardware": {"analog_controllers": [{"id": 2, "disable": True}]}}

    _route(routed_hw, cfg)

    assert all(controller is not analog for controller in routed_hw.controllers.values())
