"""Handler._handle_footswitch longpress dispatch: relay > longpress_midi_CC > chord group.

Uses the real _handle_footswitch from pistomp.handler.Handler with a mocked
Hardware, so the priority order between the three longpress behaviors is
exercised as production code, not re-implemented.
"""

from unittest.mock import MagicMock

from pistomp.footswitch import Footswitch
from pistomp.handler import Handler
from pistomp.input.event import SwitchEventKind


class _TestHandler(Handler):
    def __init__(self, hw):
        super().__init__()
        self.hardware = hw

    def update_lcd_fs(self, footswitch=None, bypass_change=False):
        pass

    def get_callback(self, callback_name):
        return None

    def handle(self, event):
        raise NotImplementedError


def _make_handler():
    hw = MagicMock()
    hw.external_port_name.return_value = None
    hw.external_midi = None
    return _TestHandler(hw), hw


def _make_footswitch(**kwargs):
    return Footswitch(
        id=kwargs.get("id", 1),
        led_pin=None,
        pixel=None,
        midi_CC=kwargs.get("midi_CC", 10),
        midi_channel=kwargs.get("midi_channel", 0),
        refresh_callback=lambda **kw: None,
    )


class TestLongpressMidiCC:
    def test_sends_longpress_cc_not_short_press_cc(self):
        handler, hw = _make_handler()
        fs = _make_footswitch(midi_CC=10)
        fs.longpress_midi_CC = 65

        handler._handle_footswitch(fs, SwitchEventKind.LONGPRESS, timestamp=1.0)

        hw.midiout.send_message.assert_called_once()
        message = hw.midiout.send_message.call_args[0][0]
        assert message[1] == 65
        assert message[2] == 127

    def test_relay_takes_priority_over_longpress_midi_cc(self):
        handler, hw = _make_handler()
        fs = _make_footswitch()
        fs.longpress_midi_CC = 65
        relay = MagicMock()
        relay.init_state.return_value = False
        fs.add_relay(relay)

        handler._handle_footswitch(fs, SwitchEventKind.LONGPRESS, timestamp=1.0)

        hw.midiout.send_message.assert_not_called()
        assert relay.enable.called or relay.disable.called

    def test_no_longpress_midi_cc_falls_through_to_chord(self):
        handler, hw = _make_handler()
        fs = _make_footswitch()
        fs.longpress_groups = ["toggle_bypass"]

        handler._handle_footswitch(fs, SwitchEventKind.LONGPRESS, timestamp=1.0)

        hw.midiout.send_message.assert_not_called()


class _StubBehavior:
    """Minimal behavior stub for momentary-press tests."""

    def __init__(self, momentary: bool) -> None:
        self.momentary = momentary

    def output_subscriptions(self):
        return ()

    def on_output(self, symbol: str, value: float) -> None:
        pass

    def led_color(self, beat):
        return None

    def led_style(self, beat):
        from modalapi.footswitch_behavior import LedDisplayStyle
        return LedDisplayStyle.SOLID


class TestMomentaryShortPress:
    """A footswitch whose behavior.momentary is True emits 127 every press
    (rising-edge trigger semantics) — no toggled flip. Otherwise the existing
    toggle behavior (127/0 alternating) is preserved."""

    def test_momentary_emits_127_every_press(self):
        handler, hw = _make_handler()
        fs = _make_footswitch(midi_CC=10)
        fs.behavior = _StubBehavior(momentary=True)

        for _ in range(3):
            handler._handle_footswitch(fs, SwitchEventKind.PRESS, timestamp=1.0)

        messages = [c.args[0] for c in hw.midiout.send_message.call_args_list]
        assert len(messages) == 3
        assert all(m[2] == 127 for m in messages)
        assert fs.toggled is False  # never flipped

    def test_non_momentary_toggles_as_before(self):
        handler, hw = _make_handler()
        fs = _make_footswitch(midi_CC=10)
        fs.behavior = _StubBehavior(momentary=False)

        handler._handle_footswitch(fs, SwitchEventKind.PRESS, timestamp=1.0)
        handler._handle_footswitch(fs, SwitchEventKind.PRESS, timestamp=2.0)

        messages = [c.args[0] for c in hw.midiout.send_message.call_args_list]
        assert len(messages) == 2
        assert messages[0][2] == 127  # first press → toggled True → 127
        assert messages[1][2] == 0    # second press → toggled False → 0
        assert fs.toggled is False

    def test_no_behavior_toggles_as_before(self):
        """Regression guard: a footswitch with behavior=None (e.g. a preset
        switch that never went through ControllerManager.bind) still toggles."""
        handler, hw = _make_handler()
        fs = _make_footswitch(midi_CC=10)
        fs.behavior = None

        handler._handle_footswitch(fs, SwitchEventKind.PRESS, timestamp=1.0)

        message = hw.midiout.send_message.call_args.args[0]
        assert message[2] == 127
        assert fs.toggled is True
