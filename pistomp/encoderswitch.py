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

from enum import Enum

import pistomp.gpioswitch as gpioswitch
import time

class Value(Enum):
    DEFAULT = 0
    PRESSED = 1
    RELEASED = 2
    LONGPRESSED = 3
    CLICKED = 4
    DOUBLECLICKED = 5


class EncoderSwitch(gpioswitch.GpioSwitch):

    def __init__(self, gpio, callback):
        super(EncoderSwitch, self).__init__(gpio, None, None)
        self.last_read = None          # this keeps track of the last value
        self.trigger_count = 0
        self.callback = callback
        self.longpress_state = False
        self.gpio = gpio

    # Override of base class method
    def pressed(self, short):
        self.callback(Value.RELEASED if short else Value.LONGPRESSED)
