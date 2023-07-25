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

import RPi.GPIO as GPIO
import threading

from functools import partial


class Encoder:

    def _process_gpios(self):
        # This decode/debouce algorithm adapted from
        # https://www.best-microcontroller-projects.com/rotary-encoder.html

        self.prevNextCode <<= 2
        if GPIO.input(self.clk_pin):
            self.prevNextCode |= 0x02
        if GPIO.input(self.d_pin):
            self.prevNextCode |= 0x01
        self.prevNextCode &= 0x0f

        direction = 0
        # Check for valid code
        if self.rot_enc_table[self.prevNextCode]:
            self.store <<= 4
            self.store |= self.prevNextCode
            # Check last two codes (end of detent transition)
            if (self.store & 0xff) == 0x2b:  # code 2 followed by code 11 (full sequence is 13,4,2,11)
                direction = -1  # Counter Clockwise
            if (self.store & 0xff) == 0x17:  # code 1 followed by code 7 (full sequence is 14,8,1,7)
                direction = 1  # Clockwise
        if direction != 0:
            self.store = self.prevNextCode
        return direction

    def _gpio_callback(self, channel):
        d = self._process_gpios()
        if d != 0:
            with self._lock:
                self.direction += d

    def __init__(self, d_pin, clk_pin, callback, use_interrupt = True, **kw):

        self.d_pin = d_pin
        self.clk_pin = clk_pin
        self.callback = callback
        self.use_interrupt = use_interrupt

        GPIO.setup(self.d_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.clk_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        if self.use_interrupt:
            GPIO.add_event_detect(self.d_pin, GPIO.BOTH, callback=self._gpio_callback)
            GPIO.add_event_detect(self.clk_pin, GPIO.BOTH, callback=self._gpio_callback)
            # It works fine without a lock since this is just dumb UI, but let's be correct..
            self._lock = threading.Lock()

        self.prevNextCode = 0
        self.store = 0
        self.direction = 0

        # 16 possible grey codes.  1=Valid, 0=Invalid (bounce)
        self.rot_enc_table = [0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0]

        super(Encoder, self).__init__(**kw)

    def __del__(self):
        GPIO.remove_event_detect(self._gpio_callback)

    def get_data(self):
        return GPIO.input(self.d_pin)

    def get_clk(self):
        return GPIO.input(self.clk_pin)

    def read_rotary(self):
        d = 0
        if self.use_interrupt:
            if self.direction != 0:
                with self._lock:
                    if self.direction > 0:
                        d = 1
                    elif self.direction < 0:
                        d = -1
                    self.direction -= d
        else:
            d = self._process_gpios()
        if d != 0:
            self.callback(d)
