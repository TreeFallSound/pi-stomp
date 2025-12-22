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

import logging
from rtmidi.midiconstants import CONTROL_CHANGE


def is_control_change(byte: int) -> bool:
    return (byte & 0xF0) == CONTROL_CHANGE


class MidiOutHandler:
    """
    Wrapper around rtmidi.MidiOut that intercepts MIDI messages and forwards
    them to external MIDI devices via passthrough mapping.

    This allows hardware controls (encoders, expression pedals, etc.) to
    transparently send their MIDI messages to both the internal MIDI system
    (for MOD-UI plugins) and external MIDI devices (like the Source Audio C4).
    """

    def __init__(self, midiout, external_midi_manager=None):
        """
        Initialize the MIDI output handler.

        Args:
            midiout: The rtmidi.MidiOut object to wrap.
            external_midi_manager: Optional ExternalMidiManager instance for passthrough.
        """
        self.midiout = midiout
        self.external_midi = external_midi_manager

    def send_message(self, message: list[int]) -> None:
        """
        Send a MIDI message to the internal MIDI system and optionally to external devices.

        Args:
            message: MIDI message as list of integers (e.g., [0xB0, 0x01, 0x7F]).
        """
        self.midiout.send_message(message)

        byte = message[0]
        if self.external_midi and is_control_change(byte) and len(message) >= 3:
            channel = byte & 0x0F  # Extract channel (0-15)
            cc = message[1]
            value = message[2]

            try:
                self.external_midi.send_passthrough_cc(channel, cc, value)
            except Exception as e:
                logging.debug(f"External MIDI passthrough failed: {e}")

    def open_port(self, port: int) -> None:
        """Delegate to wrapped midiout."""
        self.midiout.open_port(port)

    def close_port(self) -> None:
        """Delegate to wrapped midiout."""
        self.midiout.close_port()

    def get_ports(self) -> list[str]:
        """Delegate to wrapped midiout."""
        return self.midiout.get_ports()

    def __getattr__(self, name):
        """Delegate any other method calls to the wrapped midiout."""
        return getattr(self.midiout, name)
