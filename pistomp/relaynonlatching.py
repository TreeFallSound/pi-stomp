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
