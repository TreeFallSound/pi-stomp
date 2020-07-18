#!/usr/bin/env python3

import logging
import RPi.GPIO as GPIO
import time


class Relay:

    def __init__(self, set_pin, reset_pin):
        self.enabled = False
        self.set_pin = set_pin
        self.reset_pin = reset_pin
        GPIO.setup(reset_pin, GPIO.OUT)
        GPIO.output(reset_pin, GPIO.LOW)
        GPIO.setup(set_pin, GPIO.OUT)
        GPIO.output(set_pin, GPIO.LOW)

    def enable(self):
        GPIO.output(self.set_pin, GPIO.HIGH)
        time.sleep(0.04)
        self.enabled = True
        GPIO.output(self.set_pin, GPIO.LOW)
        logging.debug("Relay on: %d" % self.set_pin)

    def disable(self):
        GPIO.output(self.reset_pin, GPIO.HIGH)
        time.sleep(0.04)
        self.enabled = False
        GPIO.output(self.reset_pin, GPIO.LOW)
        logging.debug("Relay off: %d" % self.reset_pin)

