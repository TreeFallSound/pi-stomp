#!/usr/bin/env python3

import RPi.GPIO as GPIO

from functools import partial


class Encoder:

    def __init__(self, d_pin, clk_pin, callback):

        self.d_pin = d_pin
        self.clk_pin = clk_pin
        self.callback = callback

        GPIO.setup(self.d_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.clk_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(self.d_pin, GPIO.FALLING, callback=self.read_rotary)  # Can optionally add bouncetime=120
        GPIO.add_event_detect(self.clk_pin, GPIO.FALLING, callback=self.read_rotary)

        self.prevNextCode = 0
        self.store = 0

    def get_data(self):
        return GPIO.input(self.d_pin)

    def get_clk(self):
        return GPIO.input(self.clk_pin)

    def read_rotary(self, channel):
        # This alg adapted from
        # https://www.best-microcontroller-projects.com/rotary-encoder.html
        rot_enc_table = [0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0]

        self.prevNextCode <<= 2
        if GPIO.input(self.clk_pin):
            self.prevNextCode |= 0x02
        if GPIO.input(self.d_pin):
            self.prevNextCode |= 0x01
        self.prevNextCode &= 0x0f

        #print("%d %d" % (a, b))
        direction = 0
        if rot_enc_table[self.prevNextCode]:
            self.store <<= 4
            self.store |= self.prevNextCode
            if (self.store & 0xff) == 0x2b:
                direction = -1  # Counter Clockwise
            if (self.store & 0xff) == 0x17:
                direction = 1  # Clockwise

        if direction is not 0:
            self.callback(direction)
