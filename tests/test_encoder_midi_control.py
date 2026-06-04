"""Coverage for EncoderMidiControl.get_normalized_value().

Blend mode reads encoder position via this method; the / 127.0 math
must stay correct as encoders move alongside expression pedals as
valid blend inputs.
"""

from unittest.mock import MagicMock, patch


def _make_encoder():
    with patch("pistomp.encoder.Button"):
        from pistomp.encodermidicontrol import EncoderMidiControl
        return EncoderMidiControl(
            handler=MagicMock(),
            d_pin=1,
            clk_pin=2,
            callback=None,
            midi_CC=70,
            midi_channel=14,
            midiout=MagicMock(),
            type="ENCODER",
            id=0,
        )


def test_get_normalized_value_returns_midi_value_over_127():
    ec = _make_encoder()
    ec.midi_value = 0
    assert ec.get_normalized_value() == 0.0
    ec.midi_value = 127
    assert ec.get_normalized_value() == 1.0
    ec.midi_value = 64
    assert abs(ec.get_normalized_value() - 64 / 127.0) < 1e-9
