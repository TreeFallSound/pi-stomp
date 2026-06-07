"""
Tests for ExternalMidiManager and ExternalMidiOut.

These exercise the UX flows added on feat/external-midi:
  - configuring external MIDI ports via auto-detect / explicit index
  - sending pedalboard load messages with inter-message delay
  - per-pedalboard config overrides (incremental update_config)
  - ExternalMidiOut wrapper preferring external port, falling back to virtual
"""

from typing import cast
from unittest.mock import MagicMock

import pytest

from modalapi.external_midi import ExternalMidiManager, ExternalMidiOut


def _port(mgr: ExternalMidiManager, name: str) -> MagicMock:
    # Casting at the access site lets pyright resolve
    # the mock helpers (`assert_called_once_with`, `call_args_list`, etc).
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
        assert mgr.port_configs == {}
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

    def test_ports_merge_across_calls(self):
        """Pedalboard config can add/override individual ports without wiping defaults."""
        mgr = ExternalMidiManager()
        mgr.update_config({"ports": {"c4": {"auto_detect": ["*C4*"]}}})
        mgr.update_config({"ports": {"hx": {"auto_detect": ["*HX*"]}}})
        assert "c4" in mgr.port_configs
        assert "hx" in mgr.port_configs

    def test_messages_merge_per_port(self):
        """Per-pedalboard override updates only the named port, leaves others."""
        mgr = ExternalMidiManager()
        mgr.update_config({"messages": {"c4": [[0xC0, 0x00]], "hx": [[0xC0, 0x01]]}})
        mgr.update_config({"messages": {"c4": [[0xC0, 0x05]]}})
        assert mgr.messages["c4"] == [[0xC0, 0x05]]
        assert mgr.messages["hx"] == [[0xC0, 0x01]]

    def test_ports_deep_merge_preserves_defaults(self):
        """Pedalboard config overlay should merge fields, not replace the whole port dict."""
        mgr = ExternalMidiManager()
        mgr.update_config({"ports": {"c4": {"auto_detect": ["*C4*"], "port_index": 0}}})
        # Overlay only changes auto_detect — port_index should be preserved
        mgr.update_config({"ports": {"c4": {"auto_detect": ["*C4 Ultra*"]}}})
        assert mgr.port_configs["c4"].get("auto_detect") == ["*C4 Ultra*"]
        assert mgr.port_configs["c4"].get("port_index") == 0


class TestPortDiscovery:
    def test_auto_detect_glob_case_insensitive(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["Midi Through:0", "Source Audio C4 Synth", "HX Stomp"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "ports": {"c4": {"auto_detect": ["*c4*"]}},
                "messages": {"c4": [[0xC0, 0x05]]},
            }
        )
        assert mgr.send_messages_for_pedalboard() is True
        # Opened port 1 (the C4)
        _port(mgr, "c4").open_port.assert_called_once_with(1)

    def test_explicit_port_index_wins(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["A", "B", "C"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "ports": {"manual": {"port_index": 2, "auto_detect": ["*A*"]}},
                "messages": {"manual": [[0xC0, 0x00]]},
            }
        )
        mgr.send_messages_for_pedalboard()
        _port(mgr, "manual").open_port.assert_called_once_with(2)

    def test_no_match_skips_port(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["Midi Through"]
        mgr = ExternalMidiManager()
        mgr.update_config(
            {
                "enabled": True,
                "ports": {"c4": {"auto_detect": ["*C4*"]}},
                "messages": {"c4": [[0xC0, 0x05]]},
            }
        )
        # send_messages_for_pedalboard returns True (iteration ran), but no port opened
        mgr.send_messages_for_pedalboard()
        assert "c4" not in mgr.midi_ports or mgr.midi_ports.get("c4") is None


class TestSendMessagesForPedalboard:
    def test_disabled_short_circuits(self, fake_ports):
        mgr = ExternalMidiManager()
        mgr.update_config({"messages": {"c4": [[0xC0, 0]]}})
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
                "ports": {"dev": {"auto_detect": ["*dev*"]}},
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
                "ports": {"dev": {"auto_detect": ["dev"]}},
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
                "ports": {"dev": {"auto_detect": ["dev"]}},
                "messages": {"dev": [[0xC0, 1], [0xC0, 2], [0xC0, 3]]},
            }
        )
        midi_out = MagicMock()
        midi_out.send_message.side_effect = RuntimeError("device disconnected")
        # Pre-seed the cache so _init_port returns our failing mock
        mgr.midi_ports["dev"] = midi_out

        mgr.send_messages_for_pedalboard()
        # Stopped after first failure; port removed from cache so next call re-opens
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
        mgr.update_config({"enabled": True, "ports": {"dev": {"port_index": 0}}})

        assert mgr._init_port("dev") is None
        assert "dev" not in mgr.midi_ports


class TestOpenBackoff:
    def test_failed_open_backs_off_no_reenumerate(self, fake_ports):
        """A port whose device is absent must not re-enumerate on every poll tick."""
        available, created = fake_ports
        available[:] = ["something_else"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "ports": {"c4": {"auto_detect": ["*c4*"]}}})

        assert mgr._init_port("c4") is None
        n = len(created)
        assert mgr._init_port("c4") is None
        assert len(created) == n  # second attempt skipped enumeration

    def test_open_port_eager_returns_bool(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "ports": {"dev": {"port_index": 0}}})
        assert mgr.open_port("dev") is True
        assert "dev" in mgr.midi_ports


class TestSendRaw:
    def test_returns_false_when_disabled(self):
        mgr = ExternalMidiManager()
        mgr.update_config({"ports": {"dev": {"port_index": 0}}})
        assert mgr.send_raw("dev", [0xB0, 10, 64]) is False

    def test_unknown_port_returns_false(self):
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True})
        assert mgr.send_raw("ghost", [0xB0, 10, 64]) is False

    def test_sends_message_and_returns_true(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "ports": {"dev": {"port_index": 0}}})
        assert mgr.send_raw("dev", [0xB0, 80, 100]) is True
        _port(mgr, "dev").send_message.assert_called_once_with([0xB0, 80, 100])

    def test_sends_non_cc_message(self, fake_ports):
        available, _ = fake_ports
        available[:] = ["dev"]
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "ports": {"dev": {"port_index": 0}}})
        assert mgr.send_raw("dev", [0xC0, 5]) is True  # Program Change
        _port(mgr, "dev").send_message.assert_called_once_with([0xC0, 5])

    def test_returns_false_when_port_unavailable(self, fake_ports):
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "ports": {"dev": {"auto_detect": ["*nope*"]}}})
        available, _ = fake_ports
        available[:] = ["something_else"]
        assert mgr.send_raw("dev", [0xB0, 10, 64]) is False

    def test_send_failure_invalidates_port(self, fake_ports):
        mgr = ExternalMidiManager()
        mgr.update_config({"enabled": True, "ports": {"dev": {"port_index": 0}}})
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
                "ports": {"a": {"port_index": 0}, "b": {"port_index": 1}},
                "messages": {"a": [[0xC0, 0]], "b": [[0xC0, 0]]},
            }
        )
        mgr.send_messages_for_pedalboard()
        outs = [_port(mgr, "a"), _port(mgr, "b")]
        mgr.close()
        for o in outs:
            o.close_port.assert_called_once()
        assert mgr.midi_ports == {}


class TestExternalMidiOut:
    def test_delegates_to_send_raw(self):
        manager = MagicMock()
        manager.send_raw.return_value = True
        fallback = MagicMock()
        out = ExternalMidiOut(manager, "dev", fallback)
        out.send_message([0xB3, 80, 100])
        manager.send_raw.assert_called_once_with("dev", [0xB3, 80, 100])
        fallback.send_message.assert_not_called()

    def test_falls_back_when_send_raw_fails(self):
        manager = MagicMock()
        manager.send_raw.return_value = False
        fallback = MagicMock()
        out = ExternalMidiOut(manager, "dev", fallback)
        msg = [0xB0, 10, 64]
        out.send_message(msg)
        manager.send_raw.assert_called_once_with("dev", msg)
        fallback.send_message.assert_called_once_with(msg)

    def test_falls_back_when_send_raw_raises(self):
        """Exceptions from send_raw must not crash the poll loop."""
        manager = MagicMock()
        manager.send_raw.side_effect = RuntimeError("port not in config")
        fallback = MagicMock()
        out = ExternalMidiOut(manager, "dev", fallback)
        out.send_message([0xB0, 10, 64])
        fallback.send_message.assert_called_once_with([0xB0, 10, 64])

    def test_non_cc_message_routes_to_external(self):
        """Non-CC messages are sent to external port via send_raw like any other."""
        manager = MagicMock()
        manager.send_raw.return_value = True
        fallback = MagicMock()
        out = ExternalMidiOut(manager, "dev", fallback)
        msg = [0x92, 64, 100]  # Note On
        out.send_message(msg)
        manager.send_raw.assert_called_once_with("dev", msg)
        fallback.send_message.assert_not_called()

    def test_program_change_routes_to_external(self):
        """Even short messages go through send_raw."""
        manager = MagicMock()
        manager.send_raw.return_value = True
        fallback = MagicMock()
        out = ExternalMidiOut(manager, "dev", fallback)
        out.send_message([0xC0, 5])  # Program Change, 2 bytes
        manager.send_raw.assert_called_once_with("dev", [0xC0, 5])
        fallback.send_message.assert_not_called()
