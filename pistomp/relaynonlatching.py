#!/usr/bin/env python3

import logging
import RPi.GPIO as GPIO

import pistomp.relay as relay


class Relay(relay.Relay):

    def __init__(self, set_pin, reset_pin):
        self.enabled = False
        self.set_pin = set_pin
        GPIO.setup(set_pin, GPIO.OUT)
        GPIO.output(set_pin, GPIO.LOW)

    def enable(self):
        self.enabled = True
        GPIO.output(self.set_pin, self.enabled)
        logging.debug("Relay on: %d" % self.set_pin)

    def disable(self):
        self.enabled = False
        GPIO.output(self.set_pin, self.enabled)
        logging.debug("Relay off: %d" % self.set_pin)
