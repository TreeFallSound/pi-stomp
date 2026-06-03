"""Soundness checks for the emulator's mock controls.

These exercise the same superclass attributes the real hardware reads (toggled,
midi_CC, midi_value, value) so a field rename on Footswitch / Encoder /
AnalogControl fails here instead of silently in the emulator window."""

from unittest.mock import MagicMock

import pytest

from emulator.controls import (
    CONTROL_CHANGE,
    MockAnalogControl,
    MockEncoder,
    MockEncoderMidi,
    MockFootswitch,
)


# ---------------------------------------------------------------------------
# MockFootswitch
# ---------------------------------------------------------------------------


def _make_fs(midi_CC: int | None = 60, midi_channel: int = 0):
    midiout = MagicMock()
    refresh = MagicMock()
    fs = MockFootswitch(id=1, midi_CC=midi_CC, midi_channel=midi_channel, midiout=midiout, refresh_callback=refresh)
    return fs, midiout, refresh


def test_footswitch_press_toggles_and_emits_on():
    fs, midiout, refresh = _make_fs(midi_CC=60, midi_channel=0)
    assert fs.toggled is False

    fs.press()

    assert fs.toggled is True
    midiout.send_message.assert_called_once_with([CONTROL_CHANGE | 0, 60, 127])
    refresh.assert_called_once_with(footswitch=fs)


def test_footswitch_press_twice_emits_off_with_channel_masking():
    fs, midiout, _ = _make_fs(midi_CC=61, midi_channel=5)

    fs.press()
    fs.press()

    assert fs.toggled is False
    assert midiout.send_message.call_args_list[-1].args[0] == [CONTROL_CHANGE | 5, 61, 0]


def test_footswitch_without_midi_cc_still_toggles_and_calls_refresh():
    fs, midiout, refresh = _make_fs(midi_CC=None)

    fs.press()

    assert fs.toggled is True
    midiout.send_message.assert_not_called()
    refresh.assert_called_once_with(footswitch=fs)


# ---------------------------------------------------------------------------
# MockEncoder (nav / volume — no MIDI)
# ---------------------------------------------------------------------------


def test_nav_encoder_step_invokes_callback_with_direction():
    cb = MagicMock()
    enc = MockEncoder(callback=cb, type="NAV", id="nav")

    enc.step(1)
    enc.step(-1)

    assert [c.args for c in cb.call_args_list] == [(1,), (-1,)]


def test_nav_encoder_step_zero_is_a_noop():
    cb = MagicMock()
    enc = MockEncoder(callback=cb)

    enc.step(0)

    cb.assert_not_called()


# ---------------------------------------------------------------------------
# MockEncoderMidi (tweak encoders)
# ---------------------------------------------------------------------------


def _make_enc_midi(midi_CC=70, midi_channel=0):
    midiout = MagicMock()
    handler = MagicMock()
    cb = MagicMock()
    enc = MockEncoderMidi(
        handler=handler, callback=cb, midi_channel=midi_channel, midi_CC=midi_CC, midiout=midiout, type="TWEAK", id=1
    )
    return enc, midiout, cb


def test_tweak_encoder_step_emits_midi_and_invokes_callback():
    enc, midiout, cb = _make_enc_midi(midi_CC=70, midi_channel=2)
    assert enc.midi_value == 64

    enc.step(3)

    assert enc.midi_value == 67
    midiout.send_message.assert_called_once_with([CONTROL_CHANGE | 2, 70, 67])
    cb.assert_called_once_with(3)


def test_tweak_encoder_clamps_to_midi_range():
    enc, midiout, _ = _make_enc_midi()
    enc.set_value(125)

    enc.step(10)  # would go to 135 → clamped to 127
    assert enc.midi_value == 127

    enc.set_value(5)
    enc.step(-20)  # would go to -15 → clamped to 0
    assert enc.midi_value == 0

    # both emissions used the clamped value
    sent_values = [call.args[0][2] for call in midiout.send_message.call_args_list]
    assert sent_values == [127, 0]


def test_tweak_encoder_set_value_seeds_midi_value():
    enc, _, _ = _make_enc_midi()

    enc.set_value(100)
    assert enc.midi_value == 100

    enc.set_value(33.7)
    assert enc.midi_value == 33  # int() truncates


# ---------------------------------------------------------------------------
# Press callback gating (shared between MockEncoder and MockEncoderMidi)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        lambda: MockEncoder(callback=MagicMock()),
        lambda: MockEncoderMidi(
            handler=MagicMock(), callback=MagicMock(), midi_channel=0, midi_CC=70, midiout=MagicMock()
        ),
    ],
)
def test_encoder_press_without_callback_is_silent(factory):
    enc = factory()
    assert enc.press_callback is None
    enc.press(value=1)  # must not raise

    pc = MagicMock()
    enc.press_callback = pc
    enc.press(value=2)
    pc.assert_called_once_with(2)


# ---------------------------------------------------------------------------
# MockAnalogControl (expression pedal)
# ---------------------------------------------------------------------------


def test_analog_control_send_midi_emits_with_channel_masking():
    midiout = MagicMock()
    ctrl = MockAnalogControl(midi_CC=75, midi_channel=3, midiout=midiout)
    ctrl.set_value(42)

    assert ctrl.value == 42
    ctrl.send_midi(42)
    midiout.send_message.assert_called_once_with([CONTROL_CHANGE | 3, 75, 42])
