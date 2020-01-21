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

        self.prevNextCode = 0
        self.store = 0

        # 16 possible grey codes.  1=Valid, 0=Invalid (bounce)
        self.rot_enc_table = [0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0]

    def get_data(self):
        return GPIO.input(self.d_pin)

    def get_clk(self):
        return GPIO.input(self.clk_pin)

    def read_rotary(self):
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

        if direction is not 0:
            self.store = self.prevNextCode
            self.callback(direction)
