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

import common.util as util
import pistomp.analogcontrol as analogcontrol
import pistomp.controller as controller
from pistomp.controller import AnalogDisplayInfo
from pistomp.input.event import AnalogEvent


def as_midi_value(adc_value: int):
    """Convert a 10-bit ADC value (0-1023) to a MIDI value (0-127)."""
    return util.renormalize(adc_value, 0, 1023, 0, 127)


class AnalogMidiControl(analogcontrol.AnalogControl, controller.Controller):
    def __init__(self, spi, adc_channel, tolerance, midi_CC, midi_channel, type, id=None, cfg=None, autosync=False):
        super(AnalogMidiControl, self).__init__(spi, adc_channel, tolerance)
        controller.Controller.__init__(self, midi_channel, midi_CC)
        self.autosync = autosync

        self.type = type
        self.id = id
        self.last_read = 0
        self.value = None
        self.cfg: dict[str, Any] = cfg or {}

    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.value = value

    def _clamp_endpoints(self, value: int) -> int:
        if value <= self.tolerance:
            return 0
        if value >= 1023 - self.tolerance:
            return 1023
        return value

    def _send_value(self, value):
        midi_value = as_midi_value(value)
        self.midi_value = midi_value
        self.value = value
        self.last_read = value

        self.sink.handle(AnalogEvent(
            controller=self,
            raw_value=value,
            midi_value=midi_value,
        ))

    def send_current_value(self):
        """Force-send the current ADC value unconditionally. Used by sync_analog_controls()."""
        value = self._clamp_endpoints(self.readChannel())
        self._send_value(value)

    def refresh(self):
        value = self._clamp_endpoints(self.readChannel())
        if abs(value - self.last_read) > self.tolerance:
            self._send_value(value)

    def get_normalized_value(self) -> float:
        return self.last_read / 1023.0

    def get_display_info(self) -> AnalogDisplayInfo:
        return {'type': self.type, 'id': self.id, 'category': None}
