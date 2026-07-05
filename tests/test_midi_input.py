"""MidiInputControl / MidiInputManager: wireless & USB expression pedals.

Covers the value pipeline (callback stores, poll thread emits), dispatch-by-port
that ignores the incoming channel *and* CC number (a pedal sends whatever CC its
manufacturer picked; `midi_CC` on the control is only the *output* CC used when
re-emitting downstream), and the lifecycle across a pedalboard switch: the same
control instance persists across reinit(), so a per-pedalboard midi_CC override
must not disturb its binding to the device port.
"""

from typing import cast
from unittest.mock import MagicMock

import common.token as Token
from pistomp.input.event import AnalogEvent
from pistomp.input.sink import InputSink
from pistomp.midi_input_control import MidiInputControl
from pistomp.midi_input_manager import MidiInputManager
from tests.test_hardware import _StubHardware

CC = 0xB0
NOTE_ON = 0x90


class RecordingSink(InputSink):
    def __init__(self):
        self.events: list = []

    def handle(self, event) -> bool:
        self.events.append(event)
        return True


# ── MidiInputControl ────────────────────────────────────────────────


class TestMidiInputControl:
    def test_refresh_emits_analog_event_on_change(self):
        c = MidiInputControl(0, 75, Token.EXPRESSION, id=1)
        sink = RecordingSink()
        c.sink = sink

        c.feed_midi(64)
        c.refresh()
        assert len(sink.events) == 1
        e = sink.events[0]
        assert isinstance(e, AnalogEvent)
        assert e.controller is c
        assert e.midi_value == 64 and e.raw_value == 64

    def test_no_emit_without_new_value(self):
        c = MidiInputControl(0, 75, Token.EXPRESSION)
        sink = RecordingSink()
        c.sink = sink

        c.refresh()  # nothing fed
        assert sink.events == []

        c.feed_midi(64)
        c.refresh()
        c.refresh()  # value unchanged since last emit
        c.feed_midi(64)
        c.refresh()  # duplicate value
        assert len(sink.events) == 1

        c.feed_midi(0)
        c.refresh()
        assert len(sink.events) == 2

    def test_normalized_and_display(self):
        c = MidiInputControl(0, 75, Token.EXPRESSION, id=2)
        c.sink = RecordingSink()
        c.feed_midi(127)
        c.refresh()
        assert c.get_normalized_value() == 1.0
        assert c.get_display_info() == {"type": Token.EXPRESSION, "id": 2, "category": None}

    def test_send_current_value_is_noop(self):
        # autosync doesn't apply to MIDI input; must not raise and must not need a sink
        MidiInputControl(0, 75, Token.EXPRESSION).send_current_value()


# ── MidiInputManager dispatch ───────────────────────────────────────


class TestMidiInputManagerDispatch:
    def test_dispatch_by_port_ignores_channel_and_cc(self):
        # No port scan involved here — bind the control to a device name directly
        # and prove any incoming CC number (e.g. 11, as a Roland EV-1-WL sends) reaches it.
        mgr = MidiInputManager()
        c = MidiInputControl(0, 75, Token.EXPRESSION)  # midi_CC 75 is the *output* CC only
        mgr.controls["ev-1-wl"] = c

        mgr._on_message(([CC | 9, 11, 100], 0.0), "ev-1-wl")  # channel 9, CC 11
        assert c._pending == 100

    def test_non_cc_and_unbound_device_ignored(self):
        mgr = MidiInputManager()
        c = MidiInputControl(0, 75, Token.EXPRESSION)
        mgr.controls["ev-1-wl"] = c

        mgr._on_message(([NOTE_ON, 11, 60], 0.0), "ev-1-wl")  # not a CC
        mgr._on_message(([CC, 11, 20], 0.0), "some-other-device")  # unbound device
        mgr._on_message(([CC, 11], 0.0), "ev-1-wl")  # truncated
        assert c._pending is None

    def test_control_without_device_candidates_skipped(self):
        mgr = MidiInputManager()
        mgr.rebuild([MidiInputControl(0, 75, Token.EXPRESSION)])
        assert mgr.controls == {}


# ── MidiInputManager port opening ───────────────────────────────────


def _fake_rtmidi(monkeypatch, ports):
    created: list[MagicMock] = []

    def factory():
        m = MagicMock()
        m.get_ports.return_value = ports
        created.append(m)
        return m

    monkeypatch.setattr("pistomp.midi_input_manager.rtmidi.MidiIn", factory)
    return created


# Real ALSA client names observed on-device for a Roland EV-1-WL: the BLE GATT
# bridge and the USB class-compliant interface enumerate under different names.
_BT_PORT = "EV-1-WL:EV-1-WL Bluetooth 133:0"
_USB_PORT = "EV-1-WL USB-MIDI:EV-1-WL USB-MIDI MIDI 1 20:0"


class TestMidiInputManagerPorts:
    def test_opens_matching_client_case_insensitive(self, monkeypatch):
        _fake_rtmidi(monkeypatch, ["Other:in 12:0", _BT_PORT])
        mgr = MidiInputManager()
        mgr.rebuild([MidiInputControl(0, 75, Token.EXPRESSION, device_candidates=["ev-1-wl"])])

        assert "ev-1-wl" in mgr.ports
        opened = cast(MagicMock, mgr.ports["ev-1-wl"])
        opened.open_port.assert_called_once_with(1)
        assert opened.set_callback.called

    def test_candidate_priority_falls_back(self, monkeypatch):
        _fake_rtmidi(monkeypatch, [_USB_PORT])
        mgr = MidiInputManager()
        # BLE client name absent → falls back to the USB client name
        mgr.rebuild([MidiInputControl(0, 75, Token.EXPRESSION,
                                       device_candidates=["EV-1-WL", "EV-1-WL USB-MIDI"])])
        assert "EV-1-WL USB-MIDI" in mgr.ports and "EV-1-WL" not in mgr.ports

    def test_no_match_leaves_ports_and_controls_empty(self, monkeypatch):
        _fake_rtmidi(monkeypatch, ["Something Else:0 20:0"])
        mgr = MidiInputManager()
        mgr.rebuild([MidiInputControl(0, 75, Token.EXPRESSION, device_candidates=["Missing"])])
        assert mgr.ports == {}
        assert mgr.controls == {}
        # rebuild() runs again on every reinit(), so a device that appears later
        # (e.g. BLE reconnect) still gets bound on a subsequent pedalboard switch.

    def test_close(self, monkeypatch):
        _fake_rtmidi(monkeypatch, [_USB_PORT])
        mgr = MidiInputManager()
        mgr.rebuild([MidiInputControl(0, 75, Token.EXPRESSION, device_candidates=["EV-1-WL USB-MIDI"])])
        port = cast(MagicMock, mgr.ports["EV-1-WL USB-MIDI"])
        mgr.close()
        port.close_port.assert_called_once()
        assert mgr.ports == {} and mgr.controls == {}


# ── Lifecycle across a pedalboard switch ────────────────────────────


class TestPedalboardSwitchLifecycle:
    def _hw(self, monkeypatch, ports=None):
        _fake_rtmidi(monkeypatch, ports if ports is not None else [])
        default_cfg = {
            Token.HARDWARE: {
                Token.VERSION: 3.0,
                Token.MIDI: {Token.CHANNEL: 1},
                Token.ANALOG_CONTROLLERS: [
                    {
                        Token.ID: 1,
                        Token.MIDI_CC: 75,
                        Token.TYPE: Token.EXPRESSION,
                        Token.INPUT: {Token.ALSA: ["EV-1-WL", "EV-1-WL USB-MIDI"]},
                    }
                ],
            }
        }
        hw = _StubHardware(default_cfg, MagicMock(), MagicMock(name="midiout"), lambda *a, **k: None)
        hw.midi_input_manager = MidiInputManager()
        hw.create_analog_controls(default_cfg)
        control = hw.analog_controls[0]
        assert isinstance(control, MidiInputControl)
        sink = RecordingSink()
        control.sink = sink
        hw.midi_input_manager.rebuild([control])
        return hw, control, sink

    def test_midi_cc_override_does_not_disturb_input_binding(self, monkeypatch):
        # Only the USB name is present (no BLE bond yet), so the manager falls back to
        # it. The device sends CC 11 (a Roland EV-1-WL's default); dispatch is by port,
        # regardless of what midi_CC the pedalboard configures for output.
        hw, control, sink = self._hw(monkeypatch, ports=[_USB_PORT])
        mgr = hw.midi_input_manager
        assert mgr is not None
        assert mgr.controls["EV-1-WL USB-MIDI"] is control

        # Pedalboard A remaps this pedal's *output* CC 75 → 77; input dispatch is unaffected.
        pb_a = {Token.HARDWARE: {Token.ANALOG_CONTROLLERS: [{Token.ID: 1, Token.MIDI_CC: 77}]}}
        hw.reinit(pb_a)
        assert control.midi_CC == 77
        assert mgr.controls["EV-1-WL USB-MIDI"] is control

        mgr._on_message(([CC | 3, 11, 100], 0.0), "EV-1-WL USB-MIDI")  # any channel, device's own CC 11
        control.refresh()
        assert sink.events[-1].midi_value == 100

        # Pedalboard B has no analog override → output CC reverts, binding still holds.
        hw.reinit({Token.HARDWARE: {}})
        assert control.midi_CC == 75
        assert mgr.controls["EV-1-WL USB-MIDI"] is control

        mgr._on_message(([CC, 11, 40], 0.0), "EV-1-WL USB-MIDI")
        control.refresh()
        assert sink.events[-1].midi_value == 40

    def test_ports_persist_across_switches(self, monkeypatch):
        # A matching port opens once and is reused, not reopened, on each reinit.
        created = _fake_rtmidi(monkeypatch, [_USB_PORT])
        default_cfg = {
            Token.HARDWARE: {
                Token.VERSION: 3.0,
                Token.MIDI: {Token.CHANNEL: 1},
                Token.ANALOG_CONTROLLERS: [
                    {Token.ID: 1, Token.MIDI_CC: 75, Token.TYPE: Token.EXPRESSION,
                     Token.INPUT: {Token.ALSA: "EV-1-WL USB-MIDI"}},
                ],
            }
        }
        hw = _StubHardware(default_cfg, MagicMock(), MagicMock(), lambda *a, **k: None)
        hw.midi_input_manager = MidiInputManager()
        hw.create_analog_controls(default_cfg)
        hw.analog_controls[0].sink = RecordingSink()

        hw.reinit({Token.HARDWARE: {}})
        port_after_first = hw.midi_input_manager.ports["EV-1-WL USB-MIDI"]
        opens_after_first = sum(m.open_port.call_count for m in created)

        hw.reinit({Token.HARDWARE: {}})
        assert hw.midi_input_manager.ports["EV-1-WL USB-MIDI"] is port_after_first
        assert sum(m.open_port.call_count for m in created) == opens_after_first
