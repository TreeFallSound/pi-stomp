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

import time
import pistomp.analogcontrol as analogcontrol
import pistomp.switchstate as switchstate
import pistomp.taptempo as taptempo

LONG_PRESS_TIME = 0.5    # Hold seconds which defines a long press
FALLING_THRESHOLD = 800  # ASSUMES 10-bit ADC, can be changed for debounce handling

class AnalogSwitch(analogcontrol.AnalogControl):

    def __init__(self, spi, adc_channel, tolerance, callback, tap_tempo_callback=None):
        super(AnalogSwitch, self).__init__(spi, adc_channel, tolerance)
        #self.value = None          # this keeps track of the last value, do we still need this?
        self.callback = callback
        self.state = switchstate.Value.RELEASED
        self.start_time = 0
        self.duration = 0
        self.taptempo = taptempo.TapTempo(tap_tempo_callback) if tap_tempo_callback else None

    def get_tap_tempo(self):
        return self.taptempo.get_tap_tempo() if self.taptempo else 0

    # Override of base class method
    def refresh(self):
        # read the analog channel
        new_value = self.readChannel()

        if new_value <= FALLING_THRESHOLD:
            # switch pressed
            if self.state is switchstate.Value.RELEASED:
                self.state = switchstate.Value.PRESSED
                self.start_time = time.monotonic()
                if self.taptempo:
                    self.taptempo.stamp(self.start_time)
            elif self.state is not switchstate.Value.LONGPRESSED:
                # not longpress yet, but check how long
                self.duration = time.monotonic() - self.start_time
                if self.duration >= LONG_PRESS_TIME:
                    self.state = switchstate.Value.LONGPRESSED
                    self.callback(switchstate.Value.LONGPRESSED)
        elif new_value > FALLING_THRESHOLD:
            # switch released
            if self.state is switchstate.Value.PRESSED:
                self.state = switchstate.Value.RELEASED
                self.callback(switchstate.Value.RELEASED)
            elif self.state is switchstate.Value.LONGPRESSED:
                self.state = switchstate.Value.RELEASED
