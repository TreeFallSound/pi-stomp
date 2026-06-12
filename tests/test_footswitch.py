"""
Tests for Footswitch — pure dispatch + hardware methods, no hardware required.

After the input-router migration the Footswitch is a Controller that maps a
hardware state to a SwitchEvent and hands it to its sink. All toggle / relay /
MIDI / preset logic lives in the handler (see tests/input_router/).
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

from pistomp.footswitch import Footswitch
from pistomp.input.event import SwitchEvent, SwitchEventKind
import pistomp.switchstate as switchstate


class RecordingSink:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)
        return True


@contextmanager
def _make_footswitch(**kwargs):
    defaults = dict(
        id=1,
        led_pin=None,
        pixel=None,
        midi_CC=10,
        midi_channel=0,
        refresh_callback=MagicMock(),
    )
    defaults.update(kwargs)
    fs = Footswitch(**defaults)
    fs.sink = RecordingSink()
    yield fs


class TestLongpressGroups:
    def test_set_longpress_groups_stores_list(self):
        with _make_footswitch() as fs:
            fs.set_longpress_groups(["next_snapshot"])
            assert fs.longpress_groups == ["next_snapshot"]

    def test_set_longpress_groups_accepts_space_separated_string(self):
        with _make_footswitch() as fs:
            fs.set_longpress_groups("next_snapshot toggle_bypass")
            assert fs.longpress_groups == ["next_snapshot", "toggle_bypass"]

    def test_set_longpress_groups_none_clears(self):
        with _make_footswitch() as fs:
            fs.set_longpress_groups(["toggle_bypass"])
            fs.set_longpress_groups(None)
            assert fs.longpress_groups == []


class TestOnSwitch:
    def test_short_press_dispatches_press_event(self):
        with _make_footswitch() as fs:
            fs._on_switch(switchstate.Value.RELEASED, timestamp=12.5)

            assert len(fs.sink.events) == 1
            event = fs.sink.events[0]
            assert isinstance(event, SwitchEvent)
            assert event.controller is fs
            assert event.kind == SwitchEventKind.PRESS
            assert event.timestamp == 12.5

    def test_longpress_dispatches_longpress_event(self):
        with _make_footswitch() as fs:
            fs._on_switch(switchstate.Value.LONGPRESSED, timestamp=3.0)

            event = fs.sink.events[0]
            assert event.kind == SwitchEventKind.LONGPRESS
            assert event.timestamp == 3.0

    def test_disabled_footswitch_does_not_dispatch(self):
        with _make_footswitch() as fs:
            fs.disabled = True
            fs._on_switch(switchstate.Value.RELEASED)
            assert fs.sink.events == []


class TestHardwareMethods:
    def test_toggle_relays(self):
        with _make_footswitch() as fs:
            r1, r2 = MagicMock(), MagicMock()
            fs.relay_list = [r1, r2]

            fs.toggle_relays(True)
            r1.enable.assert_called_once()
            r2.enable.assert_called_once()

            fs.toggle_relays(False)
            r1.disable.assert_called_once()
            r2.disable.assert_called_once()

    def test_current_toggle_state(self):
        with _make_footswitch() as fs:
            fs.toggled = True
            assert fs.current_toggle_state() is True


class TestClearPedalboardInfo:
    def test_clears_state(self):
        with _make_footswitch() as fs:
            fs.toggled = True
            fs.display_label = "Reverb"
            pixel = MagicMock()
            fs.pixel = pixel

            fs.clear_pedalboard_info()

            assert fs.toggled is False
            assert fs.display_label is None
            assert fs.preset_callback is None
