"""Regression test for AnalogMidiControl.value_change_callback wiring.

Blend mode relies on `value_change_callback` being invoked from `refresh()`
when the ADC reading crosses the tolerance threshold. A merge once stripped
this invocation while leaving the constructor parameter in place, silently
breaking expression-pedal blend. This guards against that regression.
"""

from unittest.mock import MagicMock

from pistomp.analogmidicontrol import AnalogMidiControl


def test_refresh_invokes_value_change_callback_on_change():
    spi = MagicMock()
    adc_value = 800
    spi.xfer2.return_value = [0, (adc_value >> 8) & 0x03, adc_value & 0xFF]
    callback = MagicMock()
    control = AnalogMidiControl(
        spi=spi,
        adc_channel=0,
        tolerance=16,
        midi_CC=75,
        midi_channel=14,
        midiout=MagicMock(),
        type="EXPRESSION",
        id=0,
        value_change_callback=callback,
    )
    control.last_read = 0

    control.refresh()

    callback.assert_called_once()
    value_arg, control_arg = callback.call_args[0]
    assert value_arg == 800
    assert control_arg is control


def test_callback_observes_updated_normalized_value():
    """Slamming the pedal to a new position in one polling tick must let the
    callback observe the NEW position via get_normalized_value(). Blend mode
    re-reads the control inside handle_value_change; if last_read isn't updated
    before the callback fires, the final interpolation is computed at the
    *previous* position and the audio never reaches the new stop (even though
    a separate poller sees last_read update afterwards).
    """
    spi = MagicMock()
    spi.xfer2.return_value = [0, 0, 0]  # ADC reads 0 — heel slam
    observed: list[float] = []

    def callback(_value, control):
        observed.append(control.get_normalized_value())

    control = AnalogMidiControl(
        spi=spi,
        adc_channel=0,
        tolerance=16,
        midi_CC=75,
        midi_channel=14,
        midiout=MagicMock(),
        type="EXPRESSION",
        id=0,
        value_change_callback=callback,
    )
    control.last_read = 1023  # pedal was at toe

    control.refresh()

    assert observed == [0.0]
