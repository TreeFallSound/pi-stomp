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

from typing_extensions import override
from typing import Any

from rtmidi.midiconstants import CONTROL_CHANGE

import common.util as util
import pistomp.analogcontrol as analogcontrol

import logging


def as_midi_value(adc_value: int):
    """Convert a 10-bit ADC value (0-1023) to a MIDI value (0-127)."""
    return util.renormalize(adc_value, 0, 1023, 0, 127)


class AnalogMidiControl(analogcontrol.AnalogControl):
    def __init__(
        self,
        spi,
        adc_channel,
        tolerance,
        midi_CC,
        midi_channel,
        midiout,
        type,
        id=None,
        cfg={},
        autosync=False,
        value_change_callback=None,
    ):
        super(AnalogMidiControl, self).__init__(spi, adc_channel, tolerance)
        self.midi_CC = midi_CC
        self.midiout = midiout
        self.midi_channel = midi_channel
        self.autosync = autosync

        # Parent member overrides
        self.type = type
        self.id = id
        self.last_read = 0  # this keeps track of the last potentiometer value
        self.value = None
        self.cfg: dict[str, Any] = cfg
        self.value_change_callback = value_change_callback

    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.value = value

    def get_normalized_value(self) -> float:
        """Current ADC reading normalized to [0.0, 1.0]."""
        return self.last_read / 1023.0

    @override
    def initialize(self):
        if not self.autosync:
            return

        # read the analog pin
        value = self._clamp_endpoints(self.readChannel())
        set_volume = as_midi_value(value)

        cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, set_volume]
        logging.debug("AnalogControl force-sending CC event %s" % cc)
        self.midiout.send_message(cc)

        # save the reading to prevent duplicate sends on next poll
        self.last_read = value

    def _clamp_endpoints(self, value: int) -> int:
        """Clamp ADC values within tolerance of endpoints to exact endpoints.

        Creates a deadband at both extremes so the control always reaches
        exactly 0 and 1023, with natural hysteresis at the tolerance boundary.
        """
        if value <= self.tolerance:
            return 0
        if value >= 1023 - self.tolerance:
            return 1023
        return value

    @override
    def refresh(self):
        # read the analog pin
        value = self._clamp_endpoints(self.readChannel())

        # how much has it changed since the last read?
        pot_adjust = abs(value - self.last_read)
        value_changed = pot_adjust > self.tolerance

        if value_changed:
            set_volume = as_midi_value(value)

            cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, set_volume]
            logging.debug("AnalogControl Sending CC event %s" % cc)
            self.midiout.send_message(cc)

            self.last_read = value

            if self.value_change_callback:
                self.value_change_callback(value, self)
