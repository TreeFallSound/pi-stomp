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
import os
from pathlib import Path
import gpiozero as GPIO
import shutil
import time


class Relay:

    def __init__(self, set_pin, reset_pin):
        self.enabled = False
        self.set_pin = set_pin
        self.reset_pin = reset_pin

        # The existence of this file indicates that the pi-stomp should be true-bypassed
        # Non-existence indicates the pi-stomp should process audio
        self.sentinel_file = os.path.join(os.path.expanduser("~"), ".relay_bypass%d" % set_pin)

        self.set = GPIO.DigitalOutputDevice(pin=set_pin)
        self.reset = GPIO.DigitalOutputDevice(pin=reset_pin)

    def init_state(self):
        bypass = os.path.isfile(self.sentinel_file)
        if bypass:
            self.disable()
        else:
            self.enable()
        return not bypass

    def enable(self):
        self.set.on()
        time.sleep(0.04)
        self.enabled = True
        self.set.off()
        logging.debug("Relay on: %d" % self.set_pin)

        if os.path.isfile(self.sentinel_file):
            os.remove(self.sentinel_file)

    def disable(self):
        self.reset.on()
        time.sleep(0.04)
        self.enabled = False
        self.reset.off()
        logging.debug("Relay off: %d" % self.reset_pin)

        f = Path(self.sentinel_file)
        f.touch()
        shutil.chown(f, user="pistomp", group=None)

    def update(self, enable):
        if enable:
            self.enable()
        else:
            self.disable()

    def get(self):
        return self.enabled

