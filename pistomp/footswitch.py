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
from rtmidi.midiconstants import CONTROL_CHANGE

import pistomp.controller as controller
import time
import queue

class Footswitch(controller.Controller):

    def __init__(self, id, fs_pin, led_pin, midi_CC, midi_channel, midiout, refresh_callback):
        super(Footswitch, self).__init__(midi_channel, midi_CC)
        self.id = id
        self.display_label = None
        self.enabled = False
        self.fs_pin = fs_pin
        self.led_pin = led_pin
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.relay_list = []
        self.preset_callback = None
        self.lcd_color = None
        self.cur_tstamp = None
        self.events = queue.Queue()

        # this value (in seconds) chosen to be just greater than the event_detect bouncetime (in milliseconds)
        self.relay_poll_interval = 0.26
        self.relay_poll_intervals = 2

        # Long press threshold in seconds
        self.long_press_threshold = 0.5

        GPIO.setup(fs_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(fs_pin, GPIO.FALLING, callback=self._pressed, bouncetime=250)

        if led_pin is not None:
            GPIO.setup(led_pin, GPIO.OUT)
            self._set_led(GPIO.LOW)

    def __del__(self):
        GPIO.remove_event_detect(self.fs_pin)

    def set_midi_CC(self, midi_CC):
        self.midi_CC = midi_CC

    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.enabled = (value < 1)
        self._set_led(self.enabled)

    def _set_led(self, enabled):
        if self.led_pin is not None:
            GPIO.output(self.led_pin, enabled)

    def set_lcd_color(self, color):
        self.lcd_color = color

    def _pressed(self, gpio):
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

        logging.debug("Footswitch %d %s press" % (self.fs_pin, "short" if short else "long"))

        # If a footswitch can be mapped to control a relay, preset, MIDI or all 3
        #
        # The footswitch will only "toggle" if it's associated with a relay
        # (in which case it will toggle with the relay) or with a Midi message
        #
        new_enabled = not self.enabled

        # Update Relay (if relay is associated with this footswitch)
        if len(self.relay_list) > 0:
            if short is False:
                # Pin kept low (long press)
                # toggle the relay and LED, exit this method
                self.enabled = new_enabled
                for r in self.relay_list:
                    if self.enabled:
                        r.enable()
                    else:
                        r.disable()
                self._set_led(self.enabled)
                self.refresh_callback(True)  # True means this is a bypass change only
                return

        # If mapped to preset change
        if self.preset_callback is not None:
            # Change the preset and exit this method. Don't flip "enabled" since
            # there is no "toggle" action associated with a preset
            self.preset_callback()
            return

        # Send midi
        if self.midi_CC is not None:
            self.enabled = new_enabled
            # Update LED
            self._set_led(self.enabled)
            cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, 127 if self.enabled else 0]
            logging.debug("Sending CC event: %d %s" % (self.midi_CC, self.fs_pin))
            self.midiout.send_message(cc)

        # Update plugin parameter if any
        if self.parameter is not None:
            self.parameter.value = not self.enabled  # TODO assumes mapped parameter is :bypass

        # Update LCD
        self.refresh_callback()

    def set_display_label(self, label):
        self.display_label = label

    def clear_display_label(self):
        self.display_label = None

    def add_relay(self, relay):
        self.relay_list.append(relay)
        self.set_value(not relay.init_state())

    def clear_relays(self):
        self.relay_list.clear()

    def add_preset(self, callback):
        self.preset_callback = callback

    def clear_preset(self):
        self.preset_callback = None
