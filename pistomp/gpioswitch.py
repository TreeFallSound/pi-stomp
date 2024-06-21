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

    def __init__(self, gpio_input, midi_channel, midi_CC, callback, longpress_callback=None, taptempo=None):
        super(GpioSwitch, self).__init__(midi_channel, midi_CC)
        self.gpio_input = gpio_input
        self.cur_tstamp = None
        self.events = queue.Queue()
        self.callback = callback
        self.longpress_callback = longpress_callback
        self.taptempo = taptempo

        # Long press threshold in seconds
        self.long_press_threshold = 0.5

        # TODO with the move to gpiozero.button, we could take advantage of its methods for detecting release,
        # hold, etc. (when_released, when_held).  But experiments with those async events caused issues with
        # the LCD refresh timing.  So for now, we'll just poll like we did before when using RPi.GPIO
        self.button = Button(gpio_input, bounce_time=0.008)
        self.button.when_pressed = self._gpio_down

    def __del__(self):
        self.button.close()

    def _gpio_down(self, gpio):
        # This is run from a separate thread, timestamp pressed and queue an event
        #
        # I considered using a dual edge callback and handle the timestamp here
        # to queue long/short press events, but in practice, I noticed dual edge
        # is rather unreliable with such a long debounce, we often don't get the
        # rising edge callback at all. So let's just timestamp and we'll handle
        # everything from the poller thread
        #
        t = time.monotonic()
        self.events.put(t)
        if self.taptempo:
            self.taptempo.stamp(t)

    def poll(self):
        # Grab press event if any
        if not self.events.empty():
            new_tstamp = self.events.get_nowait()
        else:
            new_tstamp = None

        # If we were a already pressed and waiting for a release, drop it, it's easier
        # that way and we should be polling fast enough for this not to matter.
        # Otherwise record it
        if self.cur_tstamp is None:
            self.cur_tstamp = new_tstamp

        # Are we waiting for release ?
        if self.cur_tstamp is None:
            return

        time_pressed = time.monotonic() - self.cur_tstamp

        # If it's a long press, process as soon as we reach the threshold, otherwise
        # check the GPIO input
        if time_pressed > self.long_press_threshold:
            state = switchstate.Value.LONGPRESSED
        elif not self.button.is_pressed:
            state = switchstate.Value.RELEASED
        else:
            return
        self.cur_tstamp = None

        if state == switchstate.Value.LONGPRESSED and self.longpress_callback is not None:
            logging.debug("GPIO Switch %d %s %s" % (self.gpio_input, state, self.longpress_callback))
            self.longpress_callback(state)
        else:
            logging.debug("GPIO Switch %d %s %s" % (self.gpio_input, state, self.callback))
            self.callback(state)