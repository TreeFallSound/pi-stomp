"""
Tests for Footswitch — pure dispatch + hardware methods, no hardware required.

After the input-router migration the Footswitch is a Controller that maps a
hardware state to a SwitchEvent and hands it to its sink. All toggle / relay /
MIDI / preset logic lives in the handler (see tests/input_router/).
"""

from contextlib import contextmanager
from typing import Optional, cast
from unittest.mock import MagicMock

from common.parameter import Parameter
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


class TestLongpressGroups:
    def test_set_longpress_groups_stores_list(self):
        with _make_footswitch() as (fs, _sink):
            fs.set_longpress_groups(["next_snapshot"])
            assert fs.longpress_groups == ["next_snapshot"]

    def test_set_longpress_groups_accepts_space_separated_string(self):
        with _make_footswitch() as (fs, _sink):
            fs.set_longpress_groups("next_snapshot toggle_bypass")
            assert fs.longpress_groups == ["next_snapshot", "toggle_bypass"]

    def test_set_longpress_groups_none_clears(self):
        with _make_footswitch() as (fs, _sink):
            fs.set_longpress_groups(["toggle_bypass"])
            fs.set_longpress_groups(None)
            assert fs.longpress_groups == []


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
    def _param(symbol: str, value: float, minimum: Optional[float] = 0, maximum: Optional[float] = 1) -> Parameter:
        return cast(Parameter, MagicMock(symbol=symbol, value=value, minimum=minimum, maximum=maximum))

    def test_bypass_engaged_when_not_bypassed(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param(":bypass", 0)
            fs.set_value(0)
            assert fs.toggled is True

    def test_bypass_off_when_bypassed(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param(":bypass", 1)
            fs.set_value(1)
            assert fs.toggled is False

    def test_non_bypass_off_value_is_off(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param("solo", 0)
            fs.set_value(0)
            assert fs.toggled is False

    def test_non_bypass_on_value_is_on(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param("solo", 1)
            fs.set_value(1)
            assert fs.toggled is True

    def test_non_bypass_handles_missing_range(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = self._param("gain", 1, minimum=None, maximum=None)
            fs.set_value(1)
            assert fs.toggled is True

    def test_no_parameter_uses_bypass_logic(self):
        with _make_footswitch() as (fs, _sink):
            fs.parameter = None
            fs.set_value(0)
            assert fs.toggled is True
            fs.set_value(1)
            assert fs.toggled is False


class TestClearPedalboardInfo:
    def test_clears_state(self):
        with _make_footswitch() as (fs, _sink):
            fs.toggled = True
            fs.display_label = "Reverb"
            pixel = MagicMock()
            fs.pixel = pixel

            fs.clear_pedalboard_info()

            assert fs.toggled is False
            assert fs.display_label is None
            assert fs.preset_callback is None
