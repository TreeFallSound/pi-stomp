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
import RPi.GPIO as GPIO

import pistomp.controller as controller
import time
import queue

class GpioSwitch(controller.Controller):

    def __init__(self, fs_pin, midi_channel, midi_CC):
        super(GpioSwitch, self).__init__(midi_channel, midi_CC)
        self.fs_pin = fs_pin
        self.cur_tstamp = None
        self.events = queue.Queue()

        # Long press threshold in seconds
        self.long_press_threshold = 0.5

        GPIO.setup(fs_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(fs_pin, GPIO.FALLING, callback=self._gpio_down, bouncetime=250)

    def __del__(self):
        GPIO.remove_event_detect(self.fs_pin)

    def _gpio_down(self, gpio):
        # This is run from a separate thread, timestamp pressed and queue an event
        #
        # I considered using a dual edge callback and handle the timestamp here
        # to queue long/short press events, but in practice, I noticed dual edge
        # is rather unreliable with such a long debounce, we often don't get the
        # rising edge callback at all. So let's just timestamp and we'll handle
        # everything from the poller thread
        #
        self.events.put(time.monotonic())

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
            short = False
        elif GPIO.input(self.fs_pin):
            short = True
        else:
            return
        self.cur_tstamp = None

        logging.debug("Switch %d %s press" % (self.fs_pin, "short" if short else "long"))
        self.pressed(short)
