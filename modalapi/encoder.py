#!/usr/bin/env python3

import RPi.GPIO as GPIO


class Encoder:

    def __init__(self, fs_pin, led_pin, midi_CC, midiout):

        self.enabled = False
        self.fs_pin = fs_pin
        self.led_pin = led_pin
        self.midi_CC = midi_CC
        self.midiout = midiout
        self.lcd_refresh_required = False

        GPIO.setup(fs_pin, GPIO.IN)
        GPIO.add_event_detect(fs_pin, GPIO.FALLING, callback=self.toggle, bouncetime=250)

        GPIO.setup(led_pin, GPIO.OUT)
        GPIO.output(led_pin, GPIO.LOW)

    def toggle(self, foo):
        self.enabled = not self.enabled

        # Send midi
        cc = [CONTROL_CHANGE, self.midi_CC, 127 if self.enabled else 0]
        print("Sending CC event: %d %s" % (self.midi_CC, foo))
        self.midiout.send_message(cc)

        # Update LED
        GPIO.output(self.led_pin, self.enabled)   # TODO assure that GPIO.HIGH is same as True

        # TODO schedule LCD update - some global refresh state or check object state during main poll loop
        self.lcd_refresh_required = True

