"""
Tests for ExternalMidiManager.

Config keys are ALSA client device names (e.g. 'Source Audio C4 Synth').
Matching is case-insensitive against the client-name prefix of each rtmidi port string.
"""

from typing import cast
from unittest.mock import MagicMock

import pytest

from modalapi.external_midi import ExternalMidiManager


def _port(mgr: ExternalMidiManager, name: str) -> MagicMock:
    return cast(MagicMock, mgr.midi_ports[name])


@pytest.fixture
def fake_ports(monkeypatch):
    """Patch rtmidi.MidiOut so MidiOut() returns a fresh MagicMock per call.

    Returns (available_ports_list, created_outs_list). Modify available_ports_list
    in place to control what get_ports() returns. created_outs_list collects each
    MagicMock instance constructed via rtmidi.MidiOut(), so tests can assert on
    open_port / send_message / close_port calls.
    """
    available_ports: list[str] = []
    created_outs: list[MagicMock] = []

    def _factory(*args, **kwargs):
        m = MagicMock()
        m.get_ports.return_value = list(available_ports)
        created_outs.append(m)
        return m

    monkeypatch.setattr("modalapi.external_midi.rtmidi.MidiOut", _factory)
    return available_ports, created_outs


class TestUpdateConfig:
    def test_disabled_by_default(self):
        mgr = ExternalMidiManager()
        assert mgr.enabled is False
        assert mgr.send_delay_ms == 10
        assert mgr.messages == {}

    def test_none_config_is_noop(self):
        mgr = ExternalMidiManager()
        mgr.update_config(None)
        assert mgr.enabled is False

    def test_enables_and_sets_delay(self):
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "send_delay_ms": 25})
        assert mgr.enabled is True
        assert mgr.send_delay_ms == 25

    def test_messages_merge_per_port(self):
        """Per-pedalboard override updates only the named port, leaves others."""
        mgr = ExternalMidiManager()
        mgr.update_config({"messages": {"Source Audio C4 Synth": [[0xC0, 0x00]], "HX Stomp": [[0xC0, 0x01]]}})
        mgr.update_config({"messages": {"Source Audio C4 Synth": [[0xC0, 0x05]]}})
        assert mgr.messages["Source Audio C4 Synth"] == [[0xC0, 0x05]]
        assert mgr.messages["HX Stomp"] == [[0xC0, 0x01]]


class TestPortDiscovery:
    def test_device_name_matches_by_client_name(self, fake_ports):
        available, _ = fake_ports
        available[:] = [
            "Midi Through:Midi Through Port-0 14:0",
            "Source Audio C4 Synth:Source Audio C4 Synth MIDI 1 20:0",
            "HX Stomp:HX Stomp MIDI 1 21:0",
        ]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "messages": {"Source Audio C4 Synth": [[0xC0, 0x05]]},
            }
        )
        assert mgr.send_messages_for_pedalboard() is True
        _port(mgr, "Source Audio C4 Synth").open_port.assert_called_once_with(1)

    def test_device_name_match_is_case_insensitive(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["Source Audio C4 Synth:Source Audio C4 Synth MIDI 1 20:0"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "messages": {"source audio c4 synth": [[0xC0, 0x05]]},
            }
        )
        assert mgr.send_messages_for_pedalboard() is True
        _port(mgr, "source audio c4 synth").open_port.assert_called_once_with(0)

    def test_no_match_skips_port(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["Midi Through:Midi Through Port-0 14:0"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "messages": {"Source Audio C4 Synth": [[0xC0, 0x05]]},
            }
        )
        mgr.send_messages_for_pedalboard()
        assert "Source Audio C4 Synth" not in mgr.midi_ports

    def test_port_name_without_colon_matches_exactly(self, fake_ports):
        """Port strings with no colon (short names) match the key directly."""
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "messages": {"dev": [[0xC0, 0x00]]}})
        assert mgr.send_messages_for_pedalboard() is True
        _port(mgr, "dev").open_port.assert_called_once_with(0)


class TestSendMessagesForPedalboard:
    def test_disabled_short_circuits(self, fake_ports):
        mgr = ExternalMidiManager()
        mgr.update_config({"messages": {"dev": [[0xC0, 0]]}})
        assert mgr.send_messages_for_pedalboard() is False

    def test_no_messages_returns_false(self):
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        assert mgr.send_messages_for_pedalboard() is False

    def test_delay_applied_between_messages(self, fake_ports, monkeypatch):
        available, _ = fake_ports
        available[:] = ["dev"]
        sleeps: list[float] = []
        monkeypatch.setattr("modalapi.external_midi.time.sleep", lambda s: sleeps.append(s))

        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "send_delay_ms": 25,
                "messages": {"dev": [[0xC0, 0], [0xC0, 1], [0xC0, 2]]},
            }
        )
        mgr.send_messages_for_pedalboard()
        # Delays between consecutive messages, but not after the last one
        assert sleeps == [0.025, 0.025]
        assert _port(mgr, "dev").send_message.call_count == 3

    def test_invalid_message_is_skipped_others_sent(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "send_delay_ms": 0,
                "messages": {
                    "dev": [
                        [0x00, 0x00],  # invalid status byte (< 0x80)
                        [0xC0, 0x05],  # valid
                        [0xB0, 0x80, 0x00],  # invalid data byte (> 0x7F)
                        [0xB0, 0x10, 0x40],  # valid
                    ]
                },
            }
        )
        mgr.send_messages_for_pedalboard()
        sent = [c.args[0] for c in _port(mgr, "dev").send_message.call_args_list]
        assert sent == [[0xC0, 0x05], [0xB0, 0x10, 0x40]]

    def test_failing_port_invalidated_and_stops(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "send_delay_ms": 0,
                "messages": {"dev": [[0xC0, 1], [0xC0, 2], [0xC0, 3]]},
            }
        )
        midi_out = MagicMock()
        midi_out.send_message.side_effect = RuntimeError("device disconnected")
        mgr.midi_ports["dev"] = midi_out

        mgr.send_messages_for_pedalboard()
        assert midi_out.send_message.call_count == 1
        assert "dev" not in mgr.midi_ports
        midi_out.close_port.assert_called_once()


class TestInitPort:
    def test_open_port_failure_returns_none_without_keyerror(self, monkeypatch):
        """A failing open_port must not KeyError when the port is absent from the cache."""
        failing = MagicMock()
        failing.open_port.side_effect = RuntimeError("cannot open")
        monkeypatch.setattr("modalapi.external_midi.rtmidi.MidiOut", lambda *a, **k: failing)

        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        # Bypass enumeration so we reach open_port directly
        monkeypatch.setattr(mgr, "_find_port_index", lambda name: 0)

        assert mgr._init_port("dev") is None
        assert "dev" not in mgr.midi_ports


class TestOpenBackoff:
    def test_failed_open_backs_off_no_reenumerate(self, fake_ports):
        """A port whose device is absent must not re-enumerate on every poll tick."""
        available, created = fake_ports
        available[:] = ["something_else"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})

        assert mgr._init_port("missing_device") is None
        n = len(created)
        assert mgr._init_port("missing_device") is None
        assert len(created) == n  # second attempt skipped enumeration

    def test_open_port_eager_returns_bool(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        assert mgr.open_port("dev") is True
        assert "dev" in mgr.midi_ports


class TestSendRaw:
    def test_returns_false_when_disabled(self):
        mgr = ExternalMidiManager()
        assert mgr.send_raw("dev", [0xB0, 10, 64]) is False

    def test_unknown_port_returns_false(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["something_else"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        assert mgr.send_raw("ghost", [0xB0, 10, 64]) is False

    def test_sends_message_and_returns_true(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        assert mgr.send_raw("dev", [0xB0, 80, 100]) is True
        _port(mgr, "dev").send_message.assert_called_once_with([0xB0, 80, 100])

    def test_sends_non_cc_message(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        assert mgr.send_raw("dev", [0xC0, 5]) is True  # Program Change
        _port(mgr, "dev").send_message.assert_called_once_with([0xC0, 5])

    def test_returns_false_when_port_unavailable(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["something_else"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        assert mgr.send_raw("dev", [0xB0, 10, 64]) is False

    def test_send_failure_invalidates_port(self, fake_ports):
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        midi_out = MagicMock()
        midi_out.send_message.side_effect = RuntimeError("broken")
        mgr.midi_ports["dev"] = midi_out
        assert mgr.send_raw("dev", [0xB0, 10, 64]) is False
        assert "dev" not in mgr.midi_ports


class TestClose:
    def test_close_closes_all_ports(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["a", "b"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "messages": {"a": [[0xC0, 0]], "b": [[0xC0, 0]]},
            }
        )
        mgr.send_messages_for_pedalboard()
        outs = [_port(mgr, "a"), _port(mgr, "b")]
        mgr.close()
        for o in outs:
            o.close_port.assert_called_once()
        assert mgr.midi_ports == {}
