"""
Real-device loopback tests for external MIDI routing.
macOS-only for now: virtual ports need CoreMIDI. Linux/CI needs the ALSA sequencer (`sudo modprobe snd-seq-dummy snd-seq`).
"""

import sys
import time
import uuid
from unittest.mock import MagicMock

import pytest

import common.token as Token
import pistomp.switchstate as switchstate
from modalapi.external_midi import ExternalMidiManager, ExternalMidiOut
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.encodermidicontrol import EncoderMidiControl
from pistomp.footswitch import Footswitch

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="virtual MIDI ports require CoreMIDI (macOS); Linux/CI needs ALSA seq modules",
)


def _wait_for(predicate, timeout=1.0):
    """Poll predicate until true or timeout — MIDI delivery is asynchronous."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _port_is_visible(port_name, timeout=1.0):
    """Block until CoreMIDI publishes the virtual port to enumeration."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        import rtmidi
        temp = rtmidi.MidiOut()
        ports = temp.get_ports()
        del temp
        if any(port_name in p for p in ports):
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def loopback():
    """Open a real virtual MIDI-in port; yield (port_name, received_messages).

    Each test gets a uniquely-named port so async callbacks can't cross-talk.
    The fixture blocks until CoreMIDI has published the port to enumeration,
    eliminating the race between port creation and port discovery.
    """
    import rtmidi

    port_name = f"pistomp-loopback-{uuid.uuid4().hex[:8]}"
    midi_in = rtmidi.MidiIn()
    midi_in.open_virtual_port(port_name)
    received: list[list[int]] = []

    def _on_message(event, data):
        message, _delta = event
        received.append(message)

    midi_in.set_callback(_on_message)

    assert _port_is_visible(port_name), f"Virtual port {port_name!r} never became visible"

    try:
        yield port_name, received
    finally:
        midi_in.close_port()
        del midi_in


def _manager_for(port_name, glob=None):
    """Enabled manager with one port auto-detected by name glob."""
    mgr = ExternalMidiManager()
    mgr.update_config(
        {
            "enabled": True,
            "send_delay_ms": 0,
            "ports": {"dev": {"auto_detect": [glob or f"*{port_name}*"]}},
        }
    )
    return mgr


class TestRealLoopback:
    def test_send_raw_reaches_real_device(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.open_port("dev")

        assert mgr.send_raw("dev", [0xB0, 75, 42]) is True
        assert _wait_for(lambda: received == [[0xB0, 75, 42]])
        mgr.close()

    def test_external_midi_out_prefers_real_port_over_fallback(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.open_port("dev")
        fallback = MagicMock()
        out = ExternalMidiOut(mgr, "dev", fallback)

        out.send_message([0xB0, 70, 7])

        assert _wait_for(lambda: received == [[0xB0, 70, 7]])
        fallback.send_message.assert_not_called()
        mgr.close()

    def test_external_midi_out_falls_back_when_device_absent(self, loopback):
        # Glob matches nothing → real enumeration finds no port → fallback used.
        _, received = loopback
        mgr = _manager_for("unused", glob="*no-such-pistomp-port*")
        fallback = MagicMock()
        out = ExternalMidiOut(mgr, "dev", fallback)

        out.send_message([0xB0, 70, 7])

        fallback.send_message.assert_called_once_with([0xB0, 70, 7])
        assert received == []
        mgr.close()

    def test_send_messages_for_pedalboard_delivers_sequence(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.messages = {"dev": [[0xC0, 5], [0xB0, 7, 100]]}
        mgr.open_port("dev")

        assert mgr.send_messages_for_pedalboard() is True

        assert _wait_for(lambda: received == [[0xC0, 5], [0xB0, 7, 100]])
        mgr.close()

    def test_absent_device_backs_off_no_per_send_reenumerate(self, loopback, monkeypatch):
        # End-to-end: an absent device must not re-enumerate on every send.
        _, _received = loopback
        mgr = _manager_for("unused", glob="*no-such-pistomp-port*")

        enumerations = []
        real_enumerate = mgr._get_available_ports

        def counting_enumerate():
            enumerations.append(1)
            return real_enumerate()

        monkeypatch.setattr(mgr, "_get_available_ports", counting_enumerate)

        assert mgr.send_raw("dev", [0xB0, 1, 1]) is False
        assert mgr.send_raw("dev", [0xB0, 1, 2]) is False  # within backoff window

        assert len(enumerations) == 1  # second send short-circuited on backoff
        mgr.close()


class TestControlRoutesToRealPort:
    """End-to-end: a real control routed via ExternalMidiOut emits framed CC bytes on the wire.

    Each builds the actual control with its midiout set to an external wrapper (as
    __apply_midi_routing does), drives the action method directly, and asserts the
    bytes land on the virtual port. Covers every externally-routable control:
    footswitch press, tweak-encoder rotation, expression/knob movement.
    """

    def _routed(self, port_name):
        mgr = _manager_for(port_name)
        fallback = MagicMock()
        out = ExternalMidiOut(mgr, "dev", fallback)
        # Eagerly open the port so the first send doesn't race enumeration.
        mgr.open_port("dev")
        return mgr, out, fallback

    def test_footswitch_press_reaches_real_port(self, loopback):
        port_name, received = loopback
        mgr, out, fallback = self._routed(port_name)
        fs = Footswitch(1, None, None, midi_CC=61, midi_channel=0, midiout=out, refresh_callback=MagicMock())

        fs.pressed(switchstate.Value.RELEASED)  # short press → CC 127 (toggled on)

        assert _wait_for(lambda: received == [[0xB0, 61, 127]])
        fallback.send_message.assert_not_called()
        mgr.close()

    def test_tweak_encoder_rotation_reaches_real_port(self, loopback):
        port_name, received = loopback
        mgr, out, fallback = self._routed(port_name)
        enc = EncoderMidiControl(
            MagicMock(),
            d_pin=None,
            clk_pin=None,
            callback=None,
            midi_CC=70,
            midi_channel=0,
            midiout=out,
            type=Token.KNOB,
            id=1,
        )

        enc.refresh(1)  # one detent clockwise → midi_value 0 + per_click(8)

        assert _wait_for(lambda: received == [[0xB0, 70, 8]])
        fallback.send_message.assert_not_called()
        mgr.close()

    def test_expression_movement_reaches_real_port(self, loopback):
        port_name, received = loopback
        mgr, out, fallback = self._routed(port_name)
        exp = AnalogMidiControl(
            MagicMock(), 0, 16, midi_CC=75, midi_channel=0, midiout=out, type=Token.EXPRESSION, id=4
        )

        exp._send_value(1023)  # full travel → MIDI 127

        assert _wait_for(lambda: received == [[0xB0, 75, 127]])
        fallback.send_message.assert_not_called()
        mgr.close()
