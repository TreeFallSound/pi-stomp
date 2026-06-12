"""Soundness checks for the emulator's mock controls.

These exercise the same superclass attributes the real hardware reads (toggled,
midi_CC, midi_value, value) so a field rename on Footswitch / Encoder /
AnalogControl fails here instead of silently in the emulator window."""

from unittest.mock import MagicMock

import pistomp.switchstate as switchstate
from pistomp.input.event import EncoderEvent, SwitchEvent, SwitchEventKind

from emulator.controls import (
    CONTROL_CHANGE,
    MockAnalogControl,
    MockEncoder,
    MockEncoderMidi,
    MockFootswitch,
)


def _make_sink():
    sink = MagicMock()
    sink.handle.return_value = True
    return sink


# ---------------------------------------------------------------------------
# MockFootswitch
# ---------------------------------------------------------------------------


def _make_fs(midi_CC: int | None = 60, midi_channel: int = 0):
    refresh = MagicMock()
    fs = MockFootswitch(id=1, midi_CC=midi_CC, midi_channel=midi_channel, refresh_callback=refresh)
    return fs, refresh


def test_footswitch_press_toggles_and_calls_refresh():
    fs, refresh = _make_fs(midi_CC=60, midi_channel=0)
    assert fs.toggled is False

    fs.press()

    assert fs.toggled is True
    refresh.assert_called_once_with(footswitch=fs)


def test_footswitch_press_twice_toggles_off():
    fs, _ = _make_fs(midi_CC=61, midi_channel=5)

    fs.press()
    fs.press()

    assert fs.toggled is False


def test_footswitch_without_midi_cc_still_toggles_and_calls_refresh():
    fs, refresh = _make_fs(midi_CC=None)

    fs.press()

    assert fs.toggled is True
    refresh.assert_called_once_with(footswitch=fs)


# ---------------------------------------------------------------------------
# MockEncoder (nav / volume — no MIDI)
# ---------------------------------------------------------------------------


def test_nav_encoder_step_dispatches_to_sink():
    enc = MockEncoder(type="NAV", id=0)
    sink = _make_sink()
    enc.sink = sink

    enc.step(1)
    enc.step(-1)

    assert sink.handle.call_count == 2
    calls = sink.handle.call_args_list
    assert isinstance(calls[0].args[0], EncoderEvent)
    assert calls[0].args[0].rotations == 1
    assert calls[1].args[0].rotations == -1


def test_nav_encoder_step_zero_is_a_noop():
    enc = MockEncoder()
    sink = _make_sink()
    enc.sink = sink

    enc.step(0)

    sink.handle.assert_not_called()


def test_nav_encoder_press_dispatches_switch_event():
    enc = MockEncoder(type="NAV", id=0)
    sink = _make_sink()
    enc.sink = sink

    enc.press(switchstate.Value.RELEASED)

    sink.handle.assert_called_once()
    event = sink.handle.call_args.args[0]
    assert isinstance(event, SwitchEvent)
    assert event.kind == SwitchEventKind.PRESS
    assert event.timestamp > 0.0


def test_nav_encoder_longpress_dispatches_longpress_event():
    enc = MockEncoder(type="NAV", id=0)
    sink = _make_sink()
    enc.sink = sink

    enc.press(switchstate.Value.LONGPRESSED)

    sink.handle.assert_called_once()
    event = sink.handle.call_args.args[0]
    assert isinstance(event, SwitchEvent)
    assert event.kind == SwitchEventKind.LONGPRESS
    assert event.timestamp > 0.0


# ---------------------------------------------------------------------------
# MockEncoderMidi (tweak encoders)
# ---------------------------------------------------------------------------


def _make_enc_midi(midi_CC=70, midi_channel=0):
    enc = MockEncoderMidi(
        midi_channel=midi_channel, midi_CC=midi_CC, type="TWEAK", id=1
    )
    enc.sink = _make_sink()
    return enc


def test_tweak_encoder_step_advances_midi_value():
    enc = _make_enc_midi(midi_CC=70, midi_channel=2)
    assert enc.midi_value == 64

    enc.step(3)

    assert enc.midi_value == 67


def test_tweak_encoder_clamps_to_midi_range():
    enc = _make_enc_midi()
    enc.set_value(125)

    enc.step(10)  # would go to 135 → clamped to 127
    assert enc.midi_value == 127

    enc.set_value(5)
    enc.step(-20)  # would go to -15 → clamped to 0
    assert enc.midi_value == 0


def test_tweak_encoder_set_value_seeds_midi_value():
    enc = _make_enc_midi()

    enc.set_value(100)
    assert enc.midi_value == 100

    enc.set_value(33.7)
    assert enc.midi_value == 34  # Encoder snaps to nearest step


def test_tweak_encoder_step_dispatches_to_sink():
    enc = _make_enc_midi(midi_CC=70, midi_channel=0)
    sink = _make_sink()
    enc.sink = sink

    enc.step(1)

    sink.handle.assert_called_once()
    event = sink.handle.call_args.args[0]
    assert isinstance(event, EncoderEvent)


# ---------------------------------------------------------------------------
# MockAnalogControl (expression pedal)
# ---------------------------------------------------------------------------


def test_analog_control_set_value():
    ctrl = MockAnalogControl(midi_CC=75, midi_channel=3)
    ctrl.set_value(42)

    assert ctrl.value == 42
