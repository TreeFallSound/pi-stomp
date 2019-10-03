#!/usr/bin/env python3

import RPi.GPIO as GPIO


class Encoder:

    def __init__(self, d_pin, clk_pin):

        self.fs_pin = d_pin
        self.led_pin = clk_pin
        self.lcd_refresh_required = False

        GPIO.setup(d_pin, GPIO.IN)
        GPIO.add_event_detect(fs_pin, GPIO.FALLING, callback=self.change, bouncetime=250)

    def change(self, foo):
        self.enabled = not self.enabled

        self.lcd_refresh_required = True

