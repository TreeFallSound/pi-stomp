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
import logging
from adafruit_mcp3xxx.analog_in import AnalogIn


class AnalogControl:

    def __init__(self, spi, adc_channel, tolerance):

        self.spi = spi
        self.adc_channel = adc_channel
        self.last_read = 0          # this keeps track of the last potentiometer value
        self.tolerance = tolerance  # to keep from being jittery we'll only change the
                                    # value when the control has moved a significant amount

    def readChannel(self):
        adc = self.spi.xfer2([1, (8 + self.adc_channel) << 4, 0])
        data = ((adc[1] & 3) << 8) + adc[2]
        return data

    def refresh(self):
        logging.error("AnalogControl subclass hasn't overriden the refresh method")
