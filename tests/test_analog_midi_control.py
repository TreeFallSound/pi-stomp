"""Regression test for AnalogMidiControl sink dispatch.

Blend mode relies on the sink receiving an AnalogEvent from refresh()
when the ADC reading crosses the tolerance threshold. A merge once stripped
this dispatch while leaving the constructor parameter in place, silently
breaking expression-pedal blend. This guards against that regression.
"""

from unittest.mock import MagicMock

from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.input.event import AnalogEvent


def _make_control(spi, *, midi_CC=75, midi_channel=14, last_read=0):
    control = AnalogMidiControl(
        spi=spi,
        adc_channel=0,
        tolerance=16,
        midi_CC=midi_CC,
        midi_channel=midi_channel,
        type="EXPRESSION",
        id=0,
    )
    sink = MagicMock()
    control.sink = sink
    control.last_read = last_read
    return control, sink


def test_refresh_dispatches_analog_event_on_change():
    spi = MagicMock()
    adc_value = 800
    spi.xfer2.return_value = [0, (adc_value >> 8) & 0x03, adc_value & 0xFF]
    control, sink = _make_control(spi, last_read=0)

    control.refresh()

    sink.handle.assert_called_once()
    event = sink.handle.call_args[0][0]
    assert isinstance(event, AnalogEvent)
    assert event.raw_value == 800
    assert event.controller is control


def test_sink_observes_updated_last_read():
    """Slamming the pedal to a new position in one polling tick must let the
    sink observe the NEW position via get_normalized_value(). Blend mode
    re-reads the control inside handle_value_change; if last_read isn't updated
    before the callback fires, the final interpolation is computed at the
    *previous* position and the audio never reaches the new stop (even though
    a separate poller sees last_read update afterwards).
    """
    spi = MagicMock()
    spi.xfer2.return_value = [0, 0, 0]  # ADC reads 0 — heel slam
    control, sink = _make_control(spi, last_read=1023)

    observed = []

    def capture(event):
        observed.append(event.controller.get_normalized_value())

    sink.handle.side_effect = capture
    control.refresh()

    assert observed == [0.0]
