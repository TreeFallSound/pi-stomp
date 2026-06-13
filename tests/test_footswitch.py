"""
Tests for Footswitch — pure logic, no hardware required.
"""

from contextlib import contextmanager
import time
from unittest.mock import MagicMock, patch

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
    fs = Footswitch(**defaults)
    fs._set_led = MagicMock()
    yield fs
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

    def test_set_longpress_groups_none_clears_groups(self):
        with _make_footswitch() as fs:
            fs.set_longpress_groups(["next_snapshot"])
            fs.set_longpress_groups(None)
            assert fs.longpress_groups == []


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

    def test_preset_callback_without_arg(self):
        with _make_footswitch(midi_CC=None) as fs:
            cb = MagicMock()
            fs.add_preset(cb)

            fs.pressed(switchstate.Value.RELEASED)

            cb.assert_called_once_with()

    def test_taptempo_short_press_does_not_toggle(self):
        with _make_footswitch(midi_CC=42) as fs:
            taptempo = MagicMock()
            taptempo.is_enabled.return_value = True
            fs.taptempo = taptempo

            fs.pressed(switchstate.Value.RELEASED)

            taptempo.is_enabled.assert_called_once()
            assert fs.toggled is False
            fs.midiout.send_message.assert_not_called()
            fs.refresh_callback.assert_not_called()

    def test_unbound_footswitch_refresh_callback_on_press(self):
        """A footswitch with MIDI but no bound parameter still refreshes the LCD immediately."""
        with _make_footswitch(midi_CC=42) as fs:
            fs.pressed(switchstate.Value.RELEASED)

            assert fs.toggled is True
            fs.refresh_callback.assert_called_once_with(footswitch=fs)

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

    def test_relay_disable_on_second_longpress(self):
        with _make_footswitch(midi_CC=None) as fs:
            relay = MagicMock()
            relay.init_state.return_value = False
            fs.add_relay(relay)

            fs.pressed(switchstate.Value.LONGPRESSED)
            relay.enable.assert_called_once()
            relay.reset_mock()

            fs.pressed(switchstate.Value.LONGPRESSED)
            relay.disable.assert_called_once()

    def test_taptempo_short_press_does_not_toggle(self):
        with _make_footswitch(midi_CC=42) as fs:
            taptempo = MagicMock()
            taptempo.is_enabled.return_value = True
            fs.taptempo = taptempo

            fs.pressed(switchstate.Value.RELEASED)

            taptempo.is_enabled.assert_called_once()
            assert fs.toggled is False
            fs.midiout.send_message.assert_not_called()
            fs.refresh_callback.assert_not_called()


class TestSetValue:
    @staticmethod
    def _param(symbol, value, minimum=0, maximum=1):
        return MagicMock(symbol=symbol, value=value, minimum=minimum, maximum=maximum)

    def test_bypass_engaged_when_not_bypassed(self):
        with _make_footswitch() as fs:
            fs.parameter = self._param(":bypass", 0)
            fs.set_value(0)  # bypass off → effect active
            assert fs.toggled is True

    def test_bypass_off_when_bypassed(self):
        with _make_footswitch() as fs:
            fs.parameter = self._param(":bypass", 1)
            fs.set_value(1)  # bypassed → effect inactive
            assert fs.toggled is False

    def test_non_bypass_off_value_is_off(self):
        # Regression: an OFF toggle param (value 0) must not light the switch.
        with _make_footswitch() as fs:
            fs.parameter = self._param("solo", 0)
            fs.set_value(0)
            assert fs.toggled is False

    def test_non_bypass_on_value_is_on(self):
        with _make_footswitch() as fs:
            fs.parameter = self._param("solo", 1)
            fs.set_value(1)
            assert fs.toggled is True

    def test_non_bypass_handles_missing_range(self):
        with _make_footswitch() as fs:
            fs.parameter = self._param("gain", 1, minimum=None, maximum=None)
            fs.set_value(1)
            assert fs.toggled is True

    def test_set_value_drives_led_and_refresh(self):
        with _make_footswitch() as fs:
            fs.parameter = self._param(":bypass", 0)
            fs.set_value(0)
            fs._set_led.assert_any_call(True)
            fs.refresh_callback.assert_called_once_with(footswitch=fs)



class TestLongpressEventPolling:
    def test_simultaneous_longpress_calls_group_callback(self):
        Footswitch.init({"toggle_bypass": MagicMock()})
        Footswitch.all_longpress_groups["toggle_bypass"].number_in_group = 2
        try:
            with _make_footswitch(id=1, midi_CC=None) as fs1, _make_footswitch(id=2, midi_CC=None) as fs2:
                fs1.set_longpress_groups(["toggle_bypass"])
                fs2.set_longpress_groups(["toggle_bypass"])
                fs1.pressed(switchstate.Value.LONGPRESSED)
                fs2.pressed(switchstate.Value.LONGPRESSED)

                Footswitch.check_longpress_events()

                Footswitch.callbacks["toggle_bypass"].assert_called_once()
                assert len(Footswitch.all_longpress_groups["toggle_bypass"].timestamps) == 0
        finally:
            Footswitch.callbacks = {}
            Footswitch.all_longpress_groups = {}

    def test_single_longpress_expires_and_calls_callback(self):
        Footswitch.init({"toggle_bypass": MagicMock()})
        Footswitch.all_longpress_groups["toggle_bypass"].number_in_group = 1
        try:
            with _make_footswitch(id=1, midi_CC=None) as fs:
                fs.set_longpress_groups(["toggle_bypass"])
                fs.pressed(switchstate.Value.LONGPRESSED)

                with patch("pistomp.footswitch.time.monotonic", return_value=time.monotonic() + 1.0):
                    Footswitch.check_longpress_events()

                Footswitch.callbacks["toggle_bypass"].assert_called_once()
        finally:
            Footswitch.callbacks = {}
            Footswitch.all_longpress_groups = {}


class TestClearPedalboardInfo:
    def test_clears_state(self):
        with _make_footswitch() as fs:
            fs.toggled = True
            fs.display_label = "Reverb"
            pixel = MagicMock()
            fs.pixel = pixel
            fs.set_category("Reverb")
            fs.set_longpress_groups(["next_snapshot"])
            fs.add_relay(MagicMock())
            fs.add_preset(MagicMock())

            fs.clear_pedalboard_info()

            assert fs.toggled is False
            assert fs.disabled is False
            assert fs.display_label is None
            assert fs.category is None
            assert fs.preset_callback is None
            assert len(fs.relay_list) == 0
