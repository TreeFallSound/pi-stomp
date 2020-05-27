#!/usr/bin/env python3

import logging
import RPi.GPIO as GPIO


class Relay:

    def __init__(self, relay_pin):
        self.enabled = False
        self.relay_pin = relay_pin
        GPIO.setup(relay_pin, GPIO.OUT)
        GPIO.output(relay_pin, GPIO.LOW)

    def enable(self):
        self.enabled = True
        GPIO.output(self.relay_pin, self.enabled)
        logging.debug("Relay on: %d" % self.relay_pin)

    def disable(self):
        self.enabled = False
        GPIO.output(self.relay_pin, self.enabled)
        logging.debug("Relay off: %d" % self.relay_pin)
