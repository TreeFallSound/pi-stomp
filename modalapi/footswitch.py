#!/usr/bin/env python3

import logging
import RPi.GPIO as GPIO
from rtmidi.midiconstants import CONTROL_CHANGE

import modalapi.controller as controller


class Footswitch(controller.Controller):

    def __init__(self, id, fs_pin, led_pin, midi_CC, midi_channel, midiout, refresh_callback):
        super(Footswitch, self).__init__(midi_channel, midi_CC)
        self.id = id
        self.enabled = False
        self.fs_pin = fs_pin
        self.led_pin = led_pin
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.relay_list = []
        self.preset_callback = None
        GPIO.setup(fs_pin, GPIO.IN)
        GPIO.add_event_detect(fs_pin, GPIO.FALLING, callback=self.toggle, bouncetime=250)

        GPIO.setup(led_pin, GPIO.OUT)
        GPIO.output(led_pin, GPIO.LOW)

    def set_midi_CC(self, midi_CC):
        self.midi_CC = midi_CC

    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.enabled = (value < 1)
        GPIO.output(self.led_pin, self.enabled)

    def toggle(self, gpio):
        self.enabled = not self.enabled

        if self.preset_callback is not None:
            self.preset_callback()

        # Send midi
        if self.midi_CC is not None:
            cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, 127 if self.enabled else 0]
            logging.debug("Sending CC event: %d %s" % (self.midi_CC, gpio))
            self.midiout.send_message(cc)

        # Update Relay (if relay is associated with this footswitch)
        for r in self.relay_list:
            if self.enabled:
                r.enable()
            else:
                r.disable()

        # Update LED
        GPIO.output(self.led_pin, self.enabled)

        # Update LCD
        if self.parameter is not None:
            self.parameter.value = not self.enabled  # TODO assumes mapped parameter is :bypass
            self.refresh_callback()

    def add_relay(self, relay):
        self.relay_list.append(relay)

    def clear_relays(self):
        self.relay_list.clear()

    def add_preset(self, callback):
        self.preset_callback = callback

    def clear_preset(self):
        self.preset_callback = None
