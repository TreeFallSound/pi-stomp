"""GpioSwitch press detection and hold state.

Covers the state machine chord resolution reads through Footswitch.press_state,
and the callback dispatch it shares with AnalogSwitch. gpiozero is a MagicMock
under test, so the Button is replaced with a fake whose is_pressed we drive.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest

import pistomp.gpioswitch as gpioswitch
import pistomp.switchstate as switchstate

RELEASED = switchstate.Value.RELEASED
PRESSED = switchstate.Value.PRESSED
LONGPRESSED = switchstate.Value.LONGPRESSED

GPIO_PIN = 17


class _FakeButton:
    def __init__(self):
        self.is_pressed = False
        self.when_pressed = None

    def close(self):
        pass


@pytest.fixture
def clock(monkeypatch):
    now = SimpleNamespace(t=100.0)
    monkeypatch.setattr("pistomp.gpioswitch.time.monotonic", lambda: now.t)
    return now


@pytest.fixture
def switch(clock):
    short: list = []
    long: list = []
    sw = gpioswitch.GpioSwitch(
        GPIO_PIN,
        lambda state, ts: short.append((state, ts)),
        longpress_callback=lambda state, ts: long.append((state, ts)),
    )
    button = _FakeButton()
    sw.button = cast(Any, button)
    return SimpleNamespace(sw=sw, button=button, short=short, long=long, clock=clock)


def _stomp(f):
    """Physical press: the gpiozero thread timestamps and queues it."""
    f.button.is_pressed = True
    f.sw._gpio_down(GPIO_PIN)


class TestHoldState:
    def test_starts_released(self, switch):
        assert switch.sw.state is RELEASED

    def test_held_below_threshold_reads_pressed(self, switch):
        _stomp(switch)
        switch.clock.t = 100.01
        switch.sw.poll()
        assert switch.sw.state is PRESSED
        assert switch.short == [] and switch.long == []

    def test_matured_hold_reads_longpressed(self, switch):
        _stomp(switch)
        switch.clock.t = 100.01
        switch.sw.poll()
        switch.clock.t = 100.6
        switch.sw.poll()
        assert switch.sw.state is LONGPRESSED
        assert switch.long == [(LONGPRESSED, 100.0)]

    def test_still_held_after_longpress_stays_longpressed(self, switch):
        """A parked foot must keep reading LONGPRESSED — that's what stops it
        forming a chord with a later stomp."""
        _stomp(switch)
        switch.clock.t = 100.6
        switch.sw.poll()
        switch.clock.t = 100.7
        switch.sw.poll()
        assert switch.sw.state is LONGPRESSED
        assert len(switch.long) == 1  # delivered once, not per poll

    def test_release_after_longpress_clears_state(self, switch):
        """Nothing is left being tracked once a longpress is delivered, so the
        release has to be picked up off the button itself."""
        _stomp(switch)
        switch.clock.t = 100.6
        switch.sw.poll()
        switch.button.is_pressed = False
        switch.clock.t = 100.8
        switch.sw.poll()
        assert switch.sw.state is RELEASED

    def test_short_press_dispatches_and_clears(self, switch):
        _stomp(switch)
        switch.clock.t = 100.05
        switch.sw.poll()
        assert switch.sw.state is PRESSED

        switch.button.is_pressed = False
        switch.clock.t = 100.2
        switch.sw.poll()
        assert switch.sw.state is RELEASED
        assert switch.short == [(RELEASED, 100.0)]
        assert switch.long == []

    def test_second_stomp_after_release_tracks_again(self, switch):
        _stomp(switch)
        switch.clock.t = 100.6
        switch.sw.poll()
        switch.button.is_pressed = False
        switch.clock.t = 100.8
        switch.sw.poll()

        switch.clock.t = 200.0
        _stomp(switch)
        switch.clock.t = 200.01
        switch.sw.poll()
        assert switch.sw.state is PRESSED
        switch.clock.t = 200.6
        switch.sw.poll()
        assert switch.sw.state is LONGPRESSED
        assert switch.long == [(LONGPRESSED, 100.0), (LONGPRESSED, 200.0)]
