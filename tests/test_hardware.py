"""Unit tests for pistomp.hardware.Hardware helpers."""

import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest

import common.token as Token
from modalapi.external_midi import ExternalMidiManager, ExternalMidiOut
from pistomp.hardware import Hardware


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
    """A Hardware with one encoder, analog control, and footswitch, and a 'c4' external port."""
    mock_out = MagicMock()
    mock_out.get_ports.return_value = ["My MIDI Device"]
    monkeypatch.setattr("modalapi.external_midi.rtmidi.MidiOut", lambda *a, **k: mock_out)

    hw = object.__new__(_StubHardware)
    hw.midiout = MagicMock(name="virtual")
    hw.external_midi = ExternalMidiManager()
    hw.external_midi.update_config({"enabled": True})

    hw.encoders = [SimpleNamespace(id=1, midi_CC=70, midi_channel=13, midiout=hw.midiout)]
    hw.analog_controls = cast(list, [SimpleNamespace(id=2, midi_CC=75, midiout=hw.midiout)])
    hw.footswitches = cast(list, [SimpleNamespace(id=0, midiout=hw.midiout)])
    return hw


def _route(hw, cfg):
    hw._Hardware__apply_midi_routing(cfg)


class TestApplyMidiRouting:
    def test_footswitch_routed_to_external_port(self, routed_hw):
        """A footswitch with midi_port routes to its external port."""
        cfg = {Token.HARDWARE: {Token.FOOTSWITCHES: [{Token.ID: 0, "midi_port": "My MIDI Device"}]}}
        _route(routed_hw, cfg)
        fs = routed_hw.footswitches[0]
        assert isinstance(fs.midiout, ExternalMidiOut)
        assert fs.midiout.port_name == "My MIDI Device"

    def test_encoder_and_analog_routed_to_external_port(self, routed_hw):
        cfg = {
            Token.HARDWARE: {
                Token.ENCODERS: [{Token.ID: 1, "midi_port": "My MIDI Device"}],
                Token.ANALOG_CONTROLLERS: [{Token.ID: 2, "midi_port": "My MIDI Device"}],
            }
        }
        _route(routed_hw, cfg)
        assert isinstance(routed_hw.encoders[0].midiout, ExternalMidiOut)
        assert isinstance(routed_hw.analog_controls[0].midiout, ExternalMidiOut)

    def test_encoder_midi_cc_override(self, routed_hw):
        cfg = {Token.HARDWARE: {Token.ENCODERS: [{Token.ID: 1, Token.MIDI_CC: 99}]}}
        _route(routed_hw, cfg)
        assert routed_hw.encoders[0].midi_CC == 99

    def test_encoder_midi_channel_override(self, routed_hw):
        """External device may be on a different channel than the hardware default."""
        cfg = {Token.HARDWARE: {Token.ENCODERS: [{Token.ID: 1, "midi_channel": 0}]}}
        _route(routed_hw, cfg)
        assert routed_hw.encoders[0].midi_channel == 0

    def test_no_midi_port_falls_back_to_virtual(self, routed_hw):
        cfg = {Token.HARDWARE: {Token.FOOTSWITCHES: [{Token.ID: 0}]}}
        _route(routed_hw, cfg)
        assert routed_hw.footswitches[0].midiout is routed_hw.midiout

    def test_external_port_opened_eagerly(self, routed_hw):
        """The external port is opened at routing time, not lazily inside the poll loop."""
        cfg = {Token.HARDWARE: {Token.FOOTSWITCHES: [{Token.ID: 0, "midi_port": "My MIDI Device"}]}}
        _route(routed_hw, cfg)
        assert "My MIDI Device" in routed_hw.external_midi.midi_ports


class TestReinitDefaultRouting:
    def test_reinit_applies_routing_for_default_cfg(self, monkeypatch):
        """Routing is applied for the default config, not only for pedalboard cfg."""
        hw = object.__new__(_StubHardware)
        hw.default_cfg = {Token.HARDWARE: {}}
        hw.handler = MagicMock()

        for name in (
            "_Hardware__init_midi_default",
            "_Hardware__init_footswitches",
            "_Hardware__init_encoders",
            "_Hardware__init_external_midi",
        ):
            setattr(hw, name, lambda *a, **k: None)
        routed = []
        setattr(hw, "_Hardware__apply_midi_routing", lambda cfg: routed.append(cfg))
        monkeypatch.setattr("pistomp.footswitch.Footswitch.init", staticmethod(lambda cb: None))

        hw.reinit(None)

        assert routed == [hw.cfg]
