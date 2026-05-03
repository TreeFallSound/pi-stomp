"""
Tests for Footswitch — pure logic, no hardware required.
"""

from contextlib import contextmanager
import time
from unittest.mock import MagicMock

from pistomp.footswitch import Footswitch
import pistomp.switchstate as switchstate


@contextmanager
def _make_footswitch(**kwargs):
    Footswitch.init(
        {
            "next_snapshot": MagicMock(),
            "previous_snapshot": MagicMock(),
            "toggle_bypass": MagicMock(),
            "set_mod_tap_tempo": MagicMock(),
            "toggle_tap_tempo_enable": MagicMock(),
        }
    )
    defaults = dict(
        id=1,
        led_pin=None,
        pixel=None,
        midi_CC=10,
        midi_channel=0,
        midiout=MagicMock(),
        refresh_callback=MagicMock(),
    )
    defaults.update(kwargs)
    yield Footswitch(**defaults)
    Footswitch.callbacks = {}
    Footswitch.all_longpress_groups = {}


class TestLongpressGroups:
    def test_init_creates_expected_groups(self):
        callbacks = {"next_snapshot": MagicMock()}
        Footswitch.init(callbacks)
        assert "next_snapshot" in Footswitch.all_longpress_groups
        assert "toggle_bypass" in Footswitch.all_longpress_groups

    def test_set_longpress_groups_increments_count(self):
        with _make_footswitch() as fs:
            group = "next_snapshot"
            info = Footswitch.all_longpress_groups[group]
            info.number_in_group = 0

            fs.set_longpress_groups([group])

            assert info.number_in_group == 1

    def test_set_longpress_groups_accepts_space_separated_string(self):
        with _make_footswitch() as fs:
            for info in Footswitch.all_longpress_groups.values():
                info.number_in_group = 0

            fs.set_longpress_groups("next_snapshot toggle_bypass")

            assert Footswitch.all_longpress_groups["next_snapshot"].number_in_group == 1
            assert Footswitch.all_longpress_groups["toggle_bypass"].number_in_group == 1

    def test_set_longpress_groups_ignores_unknown_group(self):
        with _make_footswitch() as fs:
            # should not raise
            fs.set_longpress_groups(["not_a_real_group"])
            assert fs.longpress_groups == ["not_a_real_group"]


class TestPressed:
    def test_short_press_toggles_enabled_and_sends_midi(self):
        midiout = MagicMock()
        with _make_footswitch(midi_CC=42, midi_channel=0, midiout=midiout) as fs:
            assert fs.toggled is False

            fs.pressed(switchstate.Value.RELEASED)

            assert fs.toggled is True
            midiout.send_message.assert_called_once()
            cc_msg = midiout.send_message.call_args[0][0]
            assert cc_msg[1] == 42
            assert cc_msg[2] == 127  # enabled → 127

    def test_short_press_twice_toggles_back(self):
        midiout = MagicMock()
        with _make_footswitch(midi_CC=5, midiout=midiout) as fs:
            fs.pressed(switchstate.Value.RELEASED)
            fs.pressed(switchstate.Value.RELEASED)

            assert fs.toggled is False
            assert midiout.send_message.call_count == 2

    def test_preset_callback_called_on_press(self):
        with _make_footswitch(midi_CC=None) as fs:
            cb = MagicMock()
            fs.add_preset(cb, callback_arg="bank_a")

            fs.pressed(switchstate.Value.RELEASED)

            cb.assert_called_once_with("bank_a")
            assert fs.toggled is False  # preset press does not toggle enabled

    def test_longpress_logs_timestamp(self):
        with _make_footswitch() as fs:
            fs.set_longpress_groups(["toggle_bypass"])
            before = time.monotonic()

            fs.pressed(switchstate.Value.LONGPRESSED)

            info = Footswitch.all_longpress_groups["toggle_bypass"]
            assert fs.id in info.timestamps
            assert info.timestamps[fs.id] >= before

    def test_relay_toggle_on_longpress(self):
        with _make_footswitch(midi_CC=None) as fs:
            relay = MagicMock()
            relay.init_state.return_value = False
            fs.add_relay(relay)

            fs.pressed(switchstate.Value.LONGPRESSED)

            relay.enable.assert_called_once()


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
