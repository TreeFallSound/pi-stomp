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


import pistomp.analogcontrol as AnalogControl


class AnalogVU(AnalogControl.AnalogControl):

    def __init__(self, spi, adc_channel, tolerance, ledstrip, ledstrip_pos):
        super(AnalogVU, self).__init__(spi, adc_channel, tolerance)
        self.ledstrip = ledstrip
        self.pixel = ledstrip.add_pixel(None, ledstrip_pos)
        self.pixel._set_color("red")  # TODO maybe set_color shouldn't be private

    def refresh(self):
        # read the analog pin
        value = self.readChannel()

        # how much has it changed since the last read?
        pot_adjust = abs(value - self.last_read)
        value_changed = (pot_adjust > self.tolerance)

        # TODO save the last color too so don't have to change it with every enable
        # TODO window the samples with some hysteresis/averaging.  On, should maybe be immediate, but off can lag

        if value_changed:
            if value > 500 and value < 526:
                self.pixel.set_enable(False)
            if value >= 526 and value < 580:
                self.pixel._set_color("green")
                self.pixel.set_enable(True)
            elif value >= 580 and value < 610:
                self.pixel._set_color("yellow")
                self.pixel.set_enable(True)
            elif value >= 610:
                self.pixel._set_color("red")
                self.pixel.set_enable(True)

            # save the potentiometer reading for the next loop
            self.last_read = value

        #elif value < 512:
        #    self.pixel.set_enable(False)
