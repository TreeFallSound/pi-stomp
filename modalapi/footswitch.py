#!/usr/bin/env python3

import RPi.GPIO as GPIO
from rtmidi.midiconstants import CONTROL_CHANGE

import modalapi.controller as controller


class Footswitch(controller.Controller):

    def __init__(self, fs_pin, led_pin, midi_CC, midi_channel, midiout):
        super(Footswitch, self).__init__(midi_channel, midi_CC, None)
        self.enabled = False
        self.fs_pin = fs_pin
        self.led_pin = led_pin
        self.midiout = midiout
        self.lcd_refresh_required = False
        self.relay_list = []

        GPIO.setup(fs_pin, GPIO.IN)
        GPIO.add_event_detect(fs_pin, GPIO.FALLING, callback=self.toggle, bouncetime=250)

        GPIO.setup(led_pin, GPIO.OUT)
        GPIO.output(led_pin, GPIO.LOW)

    def toggle(self, foo):
        self.enabled = not self.enabled

        # Send midi
        cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, 127 if self.enabled else 0]
        print("Sending CC event: %d %s" % (self.midi_CC, foo))
        self.midiout.send_message(cc)

        # Update Relay (if relay is associated with this footswitch)
        for r in self.relay_list:
            if self.enabled:
                r.enable()
            else:
                r.disable()

        # Update LED
        GPIO.output(self.led_pin, self.enabled)   # TODO assure that GPIO.HIGH is same as True

        # TODO schedule LCD update - some global refresh state or check object state during main poll loop
        self.lcd_refresh_required = True

    def add_relay(self, relay):
        self.relay_list.append(relay)

    def remove_relay(self, relay):
        self.relay_list.remove(relay)

