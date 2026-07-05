# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import logging

import rtmidi

from pistomp.midi_input_control import MidiInputControl

# MIDI status nibbles
_CONTROL_CHANGE = 0xB0


def _client_name_of(port: str) -> str:
    """ALSA client name prefix of an rtmidi port string ('Client:Port N:M')."""
    return port.split(":")[0].strip()


class MidiInputManager:
    """Opens rtmidi input ports for wireless/USB expression pedals and routes
    incoming CC messages to the MidiInputControl bound to that port.

    One rtmidi.MidiIn is opened per unique ALSA client name and dispatches
    straight to whichever control claimed that device — the incoming CC
    number is not matched against anything; a pedal advertises whatever CC
    its manufacturer picked (e.g. a Roland EV-1-WL sends CC 11) and that's
    accepted as-is. The incoming channel is likewise ignored. `midi_CC` on
    the control is purely the *output* CC used when the value is re-emitted
    downstream (see Handler._emit_midi) — it plays no part in input
    matching. Message delivery is via rtmidi's callback thread, but the
    callback only stores into the control (see MidiInputControl.feed_midi)
    — no dispatch happens off the poll thread.
    """

    def __init__(self):
        self.ports: dict[str, rtmidi.MidiIn] = {}          # client name -> open port
        self.controls: dict[str, MidiInputControl] = {}    # client name -> bound control

    def rebuild(self, controls: list[MidiInputControl]) -> None:
        """(Re)bind each control to its device port. Called on every reinit()
        since a fresh MidiInputControl is created per pedalboard load.
        Ports persist across rebuilds; only the binding is refreshed."""
        for c in controls:
            if c.device_candidates:
                # FIXME: ports only (re)open here, i.e. on pedalboard switch. A BLE device
                # that connects after boot won't be usable until the next reinit — add a
                # periodic reopen.
                self._ensure_open(c)

    def _ensure_open(self, control: MidiInputControl) -> bool:
        """Bind control to the first candidate device with an open (or newly
        opened) ALSA port."""
        for name in control.device_candidates:
            if name in self.ports:
                self.controls[name] = control
                return True
            if self._open(name, control):
                return True
        logging.warning("No MIDI input port found for any of: %s", control.device_candidates)
        return False

    def _open(self, device_name: str, control: MidiInputControl) -> bool:
        try:
            probe = rtmidi.MidiIn()
            ports = probe.get_ports()
            del probe
        except Exception as e:
            logging.error(f"Failed to enumerate MIDI input ports: {e}")
            return False

        for idx, port in enumerate(ports):
            if _client_name_of(port).lower() != device_name.lower():
                continue
            try:
                midi_in = rtmidi.MidiIn()
                midi_in.open_port(idx)
                # rtmidi ignores sysex/timing/active-sense by default; we only act on CC anyway
                midi_in.set_callback(self._on_message, device_name)
                self.ports[device_name] = midi_in
                self.controls[device_name] = control
                logging.info(f"Opened MIDI input port: {port}")
                return True
            except Exception as e:
                logging.error(f"Failed to open MIDI input port {device_name} (index {idx}): {e}")
                return False
        return False

    def _on_message(self, event, data: str | None = None) -> None:
        """rtmidi callback thread. `data` is the device name bound at set_callback
        time; feed whatever control currently claims that port. Any CC is accepted."""
        message, _delta = event
        if len(message) < 3:
            return
        if (message[0] & 0xF0) != _CONTROL_CHANGE:  # channel nibble ignored
            return
        control = self.controls.get(data) if data is not None else None
        if control is not None:
            control.feed_midi(message[2])

    def close(self) -> None:
        for name, midi_in in self.ports.items():
            try:
                midi_in.close_port()
                logging.debug(f"Closed MIDI input port: {name}")
            except Exception as e:
                logging.warning(f"Error closing MIDI input port {name}: {e}")
        self.ports.clear()
        self.controls = {}
        logging.info("MIDI input manager closed")
