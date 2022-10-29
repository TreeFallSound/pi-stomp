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

import _rpi_ws281x as ws
from rpi_ws281x import PixelStrip, Color
import matplotlib
from PIL import ImageColor

import pistomp.category as Category

# LED strip configuration:  # TODO get these from hardware impl (pisompcore.py)
LED_COUNT = 4        # Number of LED pixels.
LED_PIN = 13          # GPIO pin connected to the pixels (must have PWM).
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 12          # DMA channel to use for generating signal (try 10)   # TODO XXX need to figure this out
LED_BRIGHTNESS = 30  # Set to 0 for darkest and 255 for brightest
LED_INVERT = False    # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 1      # set to '1' for GPIOs 13, 19, 41, 45 or 53

class Ledstrip:

    def __init__(self):
        # Create NeoPixel object with appropriate configuration.
        self.strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL,
                                strip_type=ws.WS2811_STRIP_RGB)
        # Intialize the library (must be called once before other functions).
        self.strip.begin()

        self.pixels = []

    def add_pixel(self, id, position):
        p = Pixel(self.strip, id, position)
        self.pixels.append(p)
        return p

    def get_gpio(self):
        return LED_PIN


class Pixel:
    def __init__(self, strip, id, position):
        self.strip = strip
        self.id = id
        self.position = position
        self.color = (0, 0, 0)

    def set_color_by_category(self, category):
        self._set_color(Category.get_category_color(category))

    def set_enable(self, enable):
        if enable and self.color:
            self._set_color_rgb(self.color[0], self.color[1], self.color[2])
        else:
            self._set_color_rgb(0, 0, 0)

    def _set_color(self, color):
        try:
            c = matplotlib.colors.cnames[color]
            c = ImageColor.getcolor(c, "RGB")
        except:
            c = color
        if c is None:
            c = (0, 0, 0)

        self.color = c
        self._set_color_rgb(c[0], c[1], c[2])

    def _set_color_rgb(self, r, g, b):
        # TODO use setPixelColorRGB
        self.strip.setPixelColor(self.position, Color(r, g, b))
        self.strip.show()
