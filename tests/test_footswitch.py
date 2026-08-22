"""
Tests for Footswitch — pure dispatch + hardware methods, no hardware required.

After the input-router migration the Footswitch is a Controller that maps a
hardware state to a SwitchEvent and hands it to its sink. All toggle / relay /
MIDI / preset logic lives in the handler (see tests/input_router/).
"""

from contextlib import contextmanager
from typing import Optional
from unittest.mock import MagicMock

from common.parameter import BYPASS_SYMBOL, Parameter, PortInfo, Symbol
from pistomp.footswitch import Footswitch
from pistomp.input.event import SwitchEvent, SwitchEventKind
from pistomp.input.sink import InputSink
import pistomp.switchstate as switchstate


class RecordingSink(InputSink):
    def __init__(self):
        self.events: list = []

    def handle(self, event):
        self.events.append(event)
        return True


@contextmanager
def _make_footswitch(**kwargs):
    fs = Footswitch(
        id=kwargs.get("id", 1),
        led_pin=kwargs.get("led_pin"),
        pixel=kwargs.get("pixel"),
        midi_CC=kwargs.get("midi_CC", 10),
        midi_channel=kwargs.get("midi_channel", 0),
        refresh_callback=kwargs.get("refresh_callback", MagicMock()),
    )
    sink = RecordingSink()
    fs.sink = sink
    yield fs, sink


class TestOnSwitch:
    def test_short_press_dispatches_press_event(self):
        with _make_footswitch() as (fs, sink):
            fs._on_switch(switchstate.Value.RELEASED, timestamp=12.5)

            assert len(sink.events) == 1
            event = sink.events[0]
            assert isinstance(event, SwitchEvent)
            assert event.controller is fs
            assert event.kind == SwitchEventKind.PRESS
            assert event.timestamp == 12.5

    def test_longpress_dispatches_longpress_event(self):
        with _make_footswitch() as (fs, sink):
            fs._on_switch(switchstate.Value.LONGPRESSED, timestamp=3.0)

            event = sink.events[0]
            assert event.kind == SwitchEventKind.LONGPRESS
            assert event.timestamp == 3.0

    def test_disabled_footswitch_does_not_dispatch(self):
        with _make_footswitch() as (fs, sink):
            fs.disabled = True
            fs._on_switch(switchstate.Value.RELEASED)
            assert sink.events == []


class TestPressState:
    def test_no_detector_reads_released(self):
        with _make_footswitch() as (fs, _sink):
            assert fs.press_state is switchstate.Value.RELEASED

    def test_reads_the_adc_detector(self):
        with _make_footswitch() as (fs, _sink):
            fs.adc_switch = MagicMock(state=switchstate.Value.PRESSED)
            assert fs.press_state is switchstate.Value.PRESSED

    def test_reads_the_gpio_detector(self):
        with _make_footswitch() as (fs, _sink):
            fs.gpio_switch = MagicMock(state=switchstate.Value.LONGPRESSED)
            assert fs.press_state is switchstate.Value.LONGPRESSED

    def test_disabled_footswitch_reads_released(self):
        """A disabled switch stops being polled, so its detector state freezes.
        Frozen at PRESSED it would look like a chord partner forever."""
        with _make_footswitch() as (fs, _sink):
            fs.adc_switch = MagicMock(state=switchstate.Value.PRESSED)
            fs.disabled = True
            assert fs.press_state is switchstate.Value.RELEASED


class TestHardwareMethods:
    def test_toggle_relays(self):
        with _make_footswitch() as (fs, _sink):
            r1, r2 = MagicMock(), MagicMock()
            fs.relay_list = [r1, r2]

            fs.toggle_relays(True)
            r1.enable.assert_called_once()
            r2.enable.assert_called_once()

            fs.toggle_relays(False)
            r1.disable.assert_called_once()
            r2.disable.assert_called_once()

    def test_current_toggle_state(self):
        with _make_footswitch() as (fs, _sink):
            fs.toggled = True
            assert fs.current_toggle_state() is True


class TestSetValue:
    @staticmethod
    def _param(symbol: Symbol, value: float, minimum: Optional[float] = 0, maximum: Optional[float] = 1) -> Parameter:
        info: PortInfo = {"shortName": str(symbol), "symbol": str(symbol)}
        if minimum is not None and maximum is not None:
            info["ranges"] = {"minimum": minimum, "maximum": maximum}
        return Parameter(info, value, None, "plug")

    def test_bypass_engaged_when_not_bypassed(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param(BYPASS_SYMBOL, 0)
            fs.set_value(0)
            assert fs.toggled is True

    def test_bypass_off_when_bypassed(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param(BYPASS_SYMBOL, 1)
            fs.set_value(1)
            assert fs.toggled is False

    def test_non_bypass_off_value_is_off(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param(Symbol("solo"), 0)
            fs.set_value(0)
            assert fs.toggled is False

    def test_non_bypass_on_value_is_on(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param(Symbol("solo"), 1)
            fs.set_value(1)
            assert fs.toggled is True

    def test_non_bypass_handles_missing_range(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param(Symbol("gain"), 1, minimum=None, maximum=None)
            fs.set_value(1)
            assert fs.toggled is True

    def test_no_parameter_uses_bypass_logic(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = None
            fs.set_value(0)
            assert fs.toggled is True
            fs.set_value(1)
            assert fs.toggled is False
