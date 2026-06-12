"""
Real-device loopback tests for external MIDI routing.
macOS-only for now: virtual ports need CoreMIDI. Linux/CI needs the ALSA sequencer (`sudo modprobe snd-seq-dummy snd-seq`).
"""

import sys
import time
import uuid
from unittest.mock import MagicMock
import pytest

from rtmidi.midiconstants import CONTROL_CHANGE
from modalapi.external_midi import ExternalMidiManager
from pistomp.controller import RoutingInfo
from pistomp.footswitch import Footswitch
from pistomp.encoder_controller import EncoderController
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.input.event import AnalogEvent, EncoderEvent, SwitchEvent, SwitchEventKind
import pistomp.switchstate as switchstate


class _FakeHardware:
    """Minimal hardware stub: just enough for _emit_midi to resolve routing."""

    def __init__(self, port_name: str):
        self._port_name = port_name
        self.midiout = MagicMock()
        self.external_routing: dict = {}

    def external_port_name(self, controller) -> str | None:
        info = self.external_routing.get(controller)
        return info.port_name if info is not None else None


class _LoopbackHandler:
    """Minimal InputSink that routes events → _emit_midi → ExternalMidiManager.

    Uses the real _handle_footswitch from pistomp.handler.Handler so the
    footswitch path exercises production code.
    """

    def __init__(self, hw: _FakeHardware, mgr: ExternalMidiManager):
        from pistomp.footswitch_chords import FootswitchChords
        self.hardware = hw
        self.external_midi = mgr
        self.chord_helper = FootswitchChords()

    def _emit_midi(self, controller, midi_value: int) -> None:
        if controller.midi_CC is None:
            return
        cc = [controller.midi_channel | CONTROL_CHANGE, controller.midi_CC, int(midi_value)]
        port_name = self.hardware.external_port_name(controller)
        if port_name is not None:
            if self.external_midi.send_raw(port_name, cc):
                return
        self.hardware.midiout.send_message(cc)

    def update_lcd_fs(self, footswitch=None, bypass_change=False):
        pass

    def get_callback(self, name):
        return None

    def handle(self, event) -> bool:
        if isinstance(event, SwitchEvent) and isinstance(event.controller, Footswitch):
            from pistomp.handler import Handler
            return Handler._handle_footswitch(self, event.controller, event.kind, event.timestamp)
        if isinstance(event, EncoderEvent):
            self._emit_midi(event.controller, event.new_midi_value)
            return True
        if isinstance(event, AnalogEvent):
            self._emit_midi(event.controller, event.midi_value)
            return True
        return False

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


def _manager_for(port_name):
    """Enabled manager; port_name is the exact ALSA client device name used as the key."""
    mgr = ExternalMidiManager()
    mgr.update_config({"enabled": True, "send_delay_ms": 0})
    return mgr


class TestRealLoopback:
    def test_send_raw_reaches_real_device(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.open_port(port_name)

        assert mgr.send_raw(port_name, [0xB0, 75, 42]) is True
        assert _wait_for(lambda: received == [[0xB0, 75, 42]])
        mgr.close()

    def test_send_messages_for_pedalboard_delivers_sequence(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.messages = {port_name: [[0xC0, 5], [0xB0, 7, 100]]}
        mgr.open_port(port_name)

        assert mgr.send_messages_for_pedalboard() is True

        assert _wait_for(lambda: received == [[0xC0, 5], [0xB0, 7, 100]])
        mgr.close()

    def test_absent_device_backs_off_no_per_send_reenumerate(self, loopback, monkeypatch):
        # End-to-end: an absent device must not re-enumerate on every send.
        _, _received = loopback
        mgr = _manager_for("no-such-pistomp-port")

        enumerations = []
        real_enumerate = mgr._get_available_ports

        def counting_enumerate():
            enumerations.append(1)
            return real_enumerate()

        monkeypatch.setattr(mgr, "_get_available_ports", counting_enumerate)

        assert mgr.send_raw("no-such-pistomp-port", [0xB0, 1, 1]) is False
        assert mgr.send_raw("no-such-pistomp-port", [0xB0, 1, 2]) is False  # within backoff window

        assert len(enumerations) == 1  # second send short-circuited on backoff
        mgr.close()


class TestControlRoutesToRealPort:
    """End-to-end: externally-routed controls emit framed CC bytes on the wire.

    Deferred — these need the full handler+sink pipeline so _emit_midi runs.
    Tracked in project_input_router_finish.
    """

    def test_footswitch_press_reaches_real_port(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.open_port(port_name)

        hw = _FakeHardware(port_name)
        handler = _LoopbackHandler(hw, mgr)

        fs = Footswitch(id=0, led_pin=None, pixel=None, midi_CC=75,
                        midi_channel=0xB0, refresh_callback=lambda **kw: None)
        hw.external_routing[fs] = RoutingInfo.external(port_name)
        fs.sink = handler

        fs._on_switch(switchstate.Value.RELEASED)

        assert _wait_for(lambda: received == [[0xB0 | CONTROL_CHANGE, 75, 127]])
        mgr.close()

    def test_tweak_encoder_rotation_reaches_real_port(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.open_port(port_name)

        hw = _FakeHardware(port_name)
        handler = _LoopbackHandler(hw, mgr)

        enc = EncoderController(d_pin=None, clk_pin=None, midi_channel=0xB0, midi_CC=7)
        hw.external_routing[enc] = RoutingInfo.external(port_name)
        enc.sink = handler

        enc.refresh(1)
        expected_value = enc.midi_value

        assert _wait_for(lambda: received == [[0xB0 | CONTROL_CHANGE, 7, expected_value]])
        mgr.close()

    def test_expression_movement_reaches_real_port(self, loopback):
        port_name, received = loopback
        mgr = _manager_for(port_name)
        mgr.open_port(port_name)

        hw = _FakeHardware(port_name)
        handler = _LoopbackHandler(hw, mgr)

        spi = MagicMock()
        spi.readChannel.return_value = 512
        expr = AnalogMidiControl(spi, adc_channel=0, tolerance=0,
                                 midi_CC=11, midi_channel=0xB0, type=None)
        hw.external_routing[expr] = RoutingInfo.external(port_name)
        expr.sink = handler

        expr._send_value(512)
        expected_value = expr.midi_value

        assert _wait_for(lambda: received == [[0xB0 | CONTROL_CHANGE, 11, expected_value]])
        mgr.close()
