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
from gpiozero import Button

import pistomp.controller as controller
import pistomp.switchstate as switchstate
import pistomp.taptempo as taptempo

import time
import queue

class GpioSwitch(controller.Controller):

    def __init__(self, gpio_input, midi_channel, midi_CC, callback, tap_tempo_callback=None,
                 longpress_callback=None):
        super(GpioSwitch, self).__init__(midi_channel, midi_CC)
        self.gpio_input = gpio_input
        self.callback = callback
        self.taptempo = taptempo.TapTempo(tap_tempo_callback) if tap_tempo_callback else None
        self.longpress_callback = longpress_callback

        # Long press threshold in seconds
        self.long_press_threshold = 0.5
        self.is_long = False

        self.button = Button(gpio_input, bounce_time=0.008, hold_time=self.long_press_threshold)
        self.button.when_pressed = self._gpio_down
        self.button.when_released = self._gpio_up
        self.button.when_held = self._longpress

    def __del__(self):
        self.button.close()

    def get_tap_tempo(self):
        return self.taptempo.get_tap_tempo() if self.taptempo else 0

    def _gpio_down(self, gpio):
        if self.taptempo:
            self.taptempo.stamp(time.monotonic())

    def _gpio_up(self):
        if not self.is_long:
            self.callback(switchstate.Value.RELEASED)
            logging.debug("Switch %d %s %s" % (self.gpio_input, switchstate.Value.RELEASED,
                                            self.callback))
        self.is_long = False

    def _longpress(self):
        self.is_long = True
        self.longpress_callback(switchstate.Value.LONGPRESSED)
        logging.debug("Switch %d %s %s" % (self.gpio_input, switchstate.Value.LONGPRESSED,
                                        self.longpress_callback))

    def poll(self):
        # Now that we're using gpiozero, gpioswitch doesn't need to be polled.
        pass