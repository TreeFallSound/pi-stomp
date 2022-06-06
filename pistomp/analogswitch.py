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

import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
from enum import Enum


import pistomp.analogcontrol as analogcontrol

class Value(Enum):
    DEFAULT = 0
    PRESSED = 1
    RELEASED = 2
    LONGPRESSED = 3
    CLICKED = 4
    DOUBLECLICKED = 5

LONGPRESS_THRESHOLD = 60  # TODO somewhat LAME.  It's dependent on the refresh frequency of the main loop

class AnalogSwitch(analogcontrol.AnalogControl):

    def __init__(self, spi, adc_channel, tolerance, callback):
        super(AnalogSwitch, self).__init__(spi, adc_channel, tolerance)
        self.value = None          # this keeps track of the last value
        self.trigger_count = 0
        self.callback = callback
        self.longpress_state = False

    # Override of base class method
    def refresh(self):
        # read the analog pin
        new_value = self.readChannel()

        # if last read is None, this is the first refresh so don't do anything yet
        if self.value is None:
            self.value = new_value
            return

        # how much has it changed since the last read?
        pot_adjust = abs(new_value - self.value)
        value_changed = (pot_adjust > self.tolerance)

        # Count the number of simultaneous refresh cycles had the switch Low (triggered)
        if not self.longpress_state and new_value < self.tolerance and self.value < self.tolerance:
            self.trigger_count += 1
            if self.trigger_count > LONGPRESS_THRESHOLD:
                value_changed = True
                self.longpress_state = True

        if value_changed:

            # save the potentiometer reading for the next loop
            self.value = new_value

            if self.trigger_count > LONGPRESS_THRESHOLD:
                new_value = Value.LONGPRESSED
            elif new_value < self.tolerance:
                new_value = Value.PRESSED
            elif new_value >= self.tolerance:
                if self.longpress_state:
                    self.longpress_state = False
                    self.trigger_count = 0
                    return
                else:
                    new_value = Value.RELEASED
            self.trigger_count = 0

            self.callback(new_value)
