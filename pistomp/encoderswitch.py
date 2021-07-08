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
import RPi.GPIO as GPIO

import time

class Value(Enum):
    DEFAULT = 0
    PRESSED = 1
    RELEASED = 2
    LONGPRESSED = 3
    CLICKED = 4
    DOUBLECLICKED = 5


class EncoderSwitch:

    def __init__(self, gpio, callback):
        #super(AnalogSwitch, self).__init__(spi, adc_channel, tolerance)
        self.last_read = None          # this keeps track of the last value
        self.trigger_count = 0
        self.callback = callback
        self.longpress_state = False
        self.gpio = gpio

        self.poll_interval = 0.26
        self.poll_intervals = 2

        GPIO.setup(gpio, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(gpio, GPIO.FALLING, callback=self.pressed, bouncetime=250)


    # Override of base class method
    def pressed(self, foo):
        value = Value.RELEASED
        short = False
        for i in range(self.poll_intervals):
            time.sleep(self.poll_interval)
            if GPIO.input(self.gpio):
                # Pin went high before timed polling was complete (short press)
                short = True
                break
        if short is False:
            # Pin kept low (long press)
            value = Value.LONGPRESSED

        self.callback(value)
