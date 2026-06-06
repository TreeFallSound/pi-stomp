"""Unit tests for pistomp.hardware.Hardware helpers."""

import logging

from modalapi.external_midi import ExternalMidiManager
from pistomp.hardware import Hardware


class _StubHardware(Hardware):
    """Concrete subclass so object.__new__ works (Hardware is abstract)."""

    def init_analog_controls(self): ...
    def init_encoders(self): ...
    def init_footswitches(self): ...
    def init_relays(self): ...
    def cleanup(self): ...
    def test(self): ...
    def add_encoder(self, *a, **k): ...


def _validate(hw, port_name):
    return hw._Hardware__validate_midi_port(port_name)


class TestValidateMidiPort:
    def test_unknown_port_logs_warning_not_error(self, caplog):
        """A config typo on midi_port is user error, not a system fault — warn, don't error."""
        hw = object.__new__(_StubHardware)
        hw.external_midi = ExternalMidiManager()  # empty port_configs

        with caplog.at_level(logging.WARNING):
            assert _validate(hw, "ghost") is None

        recs = [r for r in caplog.records if "ghost" in r.getMessage()]
        assert recs
        assert all(r.levelno == logging.WARNING for r in recs)

    def test_uninitialized_external_midi_logs_warning_not_error(self, caplog):
        hw = object.__new__(_StubHardware)
        hw.external_midi = None

        with caplog.at_level(logging.WARNING):
            assert _validate(hw, "dev") is None

        recs = [r for r in caplog.records if "dev" in r.getMessage()]
        assert recs
        assert all(r.levelno == logging.WARNING for r in recs)
