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

from typing import Any

import pistomp.controller as controller
from pistomp.controller import AnalogDisplayInfo
from pistomp.input.event import AnalogEvent


class MidiInputControl(controller.Controller):
    """An expression pedal (or knob) whose value arrives as MIDI CC from an
    external device (USB or BLE) rather than a physical ADC channel.

    MidiInputManager receives the CC on the rtmidi callback thread and calls
    feed_midi(), which only stores the value. The value is emitted as an
    AnalogEvent on the poll thread in refresh() (called from
    Hardware.poll_controls, same as AnalogMidiControl), keeping all dispatch —
    and thus every LCD/blend touch — on the 10ms critical path."""

    def __init__(self, midi_channel: int, midi_CC: int | None, type: str | None,
                 id: int | None = None, device_candidates: list[str] | None = None,
                 cfg: dict[str, Any] | None = None):
        controller.Controller.__init__(self, midi_channel, midi_CC)
        self.type = type
        self.id = id
        # ordered device names to try (bluetooth first, then usb); first match wins
        self.device_candidates: list[str] = device_candidates or []
        self.cfg: dict[str, Any] = cfg or {}
        self.last_read: int = 0
        self._pending: int | None = None  # written by rtmidi callback thread, read by poll thread

    def set_midi_channel(self, midi_channel: int) -> None:
        self.midi_channel = midi_channel

    def feed_midi(self, cc_value: int) -> None:
        """Store the latest CC (rtmidi callback thread). A single int assignment
        is atomic under the GIL; refresh() drains it on the poll thread."""
        self._pending = cc_value

    def refresh(self) -> None:
        """Poll thread: emit an AnalogEvent if a new value has arrived.
        Latest-wins, matching AnalogMidiControl's per-tick ADC read."""
        pending = self._pending
        if pending is None or pending == self.last_read:
            return
        self.last_read = pending
        self.midi_value = pending
        self.sink.handle(AnalogEvent(controller=self, raw_value=pending, midi_value=pending))

    def send_current_value(self) -> None:
        """No-op: a MIDI input has no queryable position, so autosync doesn't apply."""

    def get_normalized_value(self) -> float:
        return self.last_read / 127.0

    def get_display_info(self) -> AnalogDisplayInfo:
        return {'type': self.type, 'id': self.id, 'category': None}
