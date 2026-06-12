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
import queue
import time

import pistomp.switchstate as switchstate


class GpioSwitch:
    """Raw GPIO press detector.

    Hardware paths:
      - Footswitches on ALL versions (v1/v2/v3) when wired to GPIO pins.
      - Encoder buttons on v2 (Pistompcore) and v3 (Pistomptre) tweak encoders.

    The owning object (Footswitch or EncoderController) is responsible for any
    MIDI / event-dispatch behavior.  This class is polled via ``poll()`` from
    the main loop (it does NOT implement ``refresh()``)."""

    def __init__(self, gpio_input, callback, longpress_callback=None):
        self.gpio_input = gpio_input
        self.cur_tstamp = None
        self.events = queue.Queue()
        self.callback = callback
        self.longpress_callback = longpress_callback

        # Long press threshold in seconds
        self.long_press_threshold = 0.5

        # TODO with the move to gpiozero.button, we could take advantage of its methods for detecting release,
        # hold, etc. (when_released, when_held).  But experiments with those async events caused issues with
        # the LCD refresh timing.  So for now, we'll just poll like we did before when using RPi.GPIO
        from gpiozero import Button  # pyright: ignore[reportMissingImports]

        self.button = Button(gpio_input, bounce_time=0.008)
        self.button.when_pressed = self._gpio_down

    def __del__(self):
        try:
            self.button.close()
        except Exception:
            pass

    def _gpio_down(self, gpio):
        # Runs from a gpiozero thread: just timestamp + queue. Dual-edge
        # callbacks are unreliable with our long debounce, so we poll the
        # release from the main loop.
        t = time.monotonic()
        self.events.put(t)

    def poll(self):
        if not self.events.empty():
            new_tstamp = self.events.get_nowait()
        else:
            new_tstamp = None

        # If we were already pressed and waiting for release, drop the new
        # press event — easier and the poll rate makes it irrelevant.
        if self.cur_tstamp is None:
            self.cur_tstamp = new_tstamp

        if self.cur_tstamp is None:
            return

        time_pressed = time.monotonic() - self.cur_tstamp

        if time_pressed > self.long_press_threshold:
            state = switchstate.Value.LONGPRESSED
        elif not self.button.is_pressed:
            state = switchstate.Value.RELEASED
        else:
            return
        press_tstamp = self.cur_tstamp
        self.cur_tstamp = None

        if state == switchstate.Value.LONGPRESSED and self.longpress_callback is not None:
            logging.debug("GPIO Switch %d %s %s" % (self.gpio_input, state, self.longpress_callback))
            self.longpress_callback(state, press_tstamp)
        else:
            logging.debug("GPIO Switch %d %s %s" % (self.gpio_input, state, self.callback))
            self.callback(state, press_tstamp)
