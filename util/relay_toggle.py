#!/usr/bin/env python3

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

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import RPi.GPIO as GPIO
import pistomp.relay as Relay


# Warning these pin assignments must match pistomp/pistomp.py
RELAY_RESET_PIN = 16
RELAY_SET_PIN = 12


def main():
    mode_previously_unset = False
    if GPIO.getmode() is None:
        print ("set GPIO mode")
        mode_previously_unset = True
        GPIO.setmode(GPIO.BCM)

    relay = Relay.Relay(RELAY_SET_PIN, RELAY_RESET_PIN)
    relay.init_state()
    if relay.enabled is True:
        print("disabling...")
        relay.disable()
    else:
        print("enabling...")
        relay.enable()

    if mode_previously_unset is True:
        print ("cleanup GPIO")
        GPIO.cleanup()

if __name__ == '__main__':
    main()
