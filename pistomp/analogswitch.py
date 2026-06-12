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

from typing_extensions import override

import time
import pistomp.analogcontrol as analogcontrol
import pistomp.switchstate as switchstate


class AnalogSwitch(analogcontrol.AnalogControl):
    """Raw ADC press detector (10-bit via MCP3008 SPI).

    Hardware paths:
      - Encoder buttons on v1 (Pistomp) — both nav encoders use ADC channels.
      - Nav encoder button on v3 (Pistomptre) — uses ADC channel 4.
      - Footswitches on ALL versions when wired to ADC channels (e.g. expression-pedal-style switches).

    The "tolerance" value is ignored.

    The owning object (Footswitch or EncoderController) is responsible for any
    MIDI / event-dispatch behavior. This class is polled via ``refresh()`` from
    the main loop (it does NOT implement ``poll()``)."""

    # ADC value below which a switch is considered pressed.
    THRESHOLD = 800

    # Hold seconds which defines a long press.
    LONG_PRESS_TIME = 0.5

    def __init__(self, spi, adc_channel, callback, longpress_callback=None):
        # Tolerance is not used for switch detection (binary pressed/released)
        super(AnalogSwitch, self).__init__(spi, adc_channel, tolerance=0)
        self.callback = callback
        self.longpress_callback = longpress_callback
        self.state = switchstate.Value.RELEASED
        self.start_time = 0
        self.duration = 0

    @override
    def refresh(self):
        # read the analog channel
        new_value = self.readChannel()

        if new_value <= self.THRESHOLD:
            # switch pressed
            if self.state is switchstate.Value.RELEASED:
                self.state = switchstate.Value.PRESSED
                self.start_time = time.monotonic()
            elif self.state is not switchstate.Value.LONGPRESSED:
                # not longpress yet, but check how long
                self.duration = time.monotonic() - self.start_time
                if self.duration >= self.LONG_PRESS_TIME:
                    self.state = switchstate.Value.LONGPRESSED
                    if self.longpress_callback is not None:
                        self.longpress_callback(switchstate.Value.LONGPRESSED, self.start_time)
        elif new_value > self.THRESHOLD:
            # switch released
            if self.state is switchstate.Value.PRESSED:
                self.state = switchstate.Value.RELEASED
                self.callback(switchstate.Value.RELEASED, self.start_time)
            elif self.state is switchstate.Value.LONGPRESSED:
                self.state = switchstate.Value.RELEASED
