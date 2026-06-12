# pyright: reportAttributeAccessIssue=false
"""SwitchEvent dispatch from Footswitch and EncoderController buttons.

Both controllers are pure event sources after the input-router migration:
they map a hardware state to a SwitchEvent (PRESS / LONGPRESS, with the
hardware-detection timestamp) and hand it to their sink. All side effects
live in the handler, so these tests assert only on the emitted events.
"""

from unittest.mock import MagicMock

import pistomp.switchstate as switchstate
from pistomp.encoder_controller import EncoderController
from pistomp.footswitch import Footswitch
from pistomp.input.event import SwitchEvent, SwitchEventKind
from pistomp.input.sink import InputSink


class RecordingSink(InputSink):
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)
        return True


def _footswitch():
    fs = Footswitch(
        id=1,
        led_pin=None,
        pixel=None,
        midi_CC=10,
        midi_channel=0,
        refresh_callback=MagicMock(),
    )
    fs.sink = RecordingSink()
    return fs


def _encoder():
    enc = EncoderController(d_pin=None, clk_pin=None, midi_CC=70, midi_channel=0, id=2)
    enc.sink = RecordingSink()
    return enc


class TestFootswitchDispatch:
    def test_short_press_emits_press_with_timestamp(self):
        fs = _footswitch()
        fs._on_switch(switchstate.Value.RELEASED, timestamp=7.5)

        (event,) = fs.sink.events
        assert isinstance(event, SwitchEvent)
        assert event.controller is fs
        assert event.kind == SwitchEventKind.PRESS
        assert event.timestamp == 7.5

    def test_longpress_emits_longpress(self):
        fs = _footswitch()
        fs._on_switch(switchstate.Value.LONGPRESSED, timestamp=2.0)

        (event,) = fs.sink.events
        assert event.kind == SwitchEventKind.LONGPRESS
        assert event.timestamp == 2.0

    def test_disabled_footswitch_emits_nothing(self):
        fs = _footswitch()
        fs.disabled = True
        fs._on_switch(switchstate.Value.RELEASED, timestamp=1.0)
        assert fs.sink.events == []


class TestEncoderButtonDispatch:
    def test_button_release_emits_press(self):
        enc = _encoder()
        enc._on_button(switchstate.Value.RELEASED, timestamp=3.0)

        (event,) = enc.sink.events
        assert isinstance(event, SwitchEvent)
        assert event.controller is enc
        assert event.kind == SwitchEventKind.PRESS
        assert event.timestamp == 3.0

    def test_button_longpressed_state_does_not_emit_on_short_path(self):
        # _on_button is the short-press callback; a LONGPRESSED state must not
        # be reported as a short press (the longpress path handles that).
        enc = _encoder()
        enc._on_button(switchstate.Value.LONGPRESSED, timestamp=3.0)
        assert enc.sink.events == []

    def test_button_longpress_emits_longpress(self):
        enc = _encoder()
        enc._on_button_longpress(switchstate.Value.LONGPRESSED, timestamp=9.0)

        (event,) = enc.sink.events
        assert event.kind == SwitchEventKind.LONGPRESS
        assert event.timestamp == 9.0
