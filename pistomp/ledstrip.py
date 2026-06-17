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

import pygame

import common.util as Util
import pistomp.category as Category

# LED strip configuration:  # TODO get these from hardware impl (pisompcore.py)
LED_COUNT = 6          # Number of LED pixels.
LED_BRIGHTNESS = 0.19  # Set to 0 for darkest, 1.0 for brightest (0.19 seems good, 0.06 for photos)

class Ledstrip:

    def __init__(self):
        import board
        import neopixel
        self._led_pin = board.D13  # TODO get this from hardware impl (pisompcore.py)
        self.strip = neopixel.NeoPixel(self._led_pin, LED_COUNT, brightness=LED_BRIGHTNESS)
        self.pixels = []

    def add_pixel(self, id, position):
        if position >= LED_COUNT:
            raise ValueError(f"Position {position} exceeds LED strip length {LED_COUNT}")
        p = Pixel(self.strip, id, position)
        self.pixels.append(p)
        return p

    def get_gpio(self):
        return self._led_pin

    def cleanup(self):
        for p in self.pixels:
            p.set_enable(False)


class Pixel:
    def __init__(self, strip, id, position):
        self.strip = strip
        self.id = id
        self.position = position
        self.color = (0, 0, 0)
        self.color_cache = {}

    # set the color for the pixel based on category, then render based on enabled status
    def set_color_by_category(self, category, enabled):
        self.set_color(Category.get_category_color(category))
        self.set_enable(enabled)

    # render based on enable
    def set_enable(self, enable):
        if enable and self.color:
            self._render_color_rgb(self.color[0], self.color[1], self.color[2])
        else:
            self._render_color_rgb(0, 0, 0)

    # set the color for the pixel based on the name or rgb
    def set_color(self, color):
        import matplotlib
        try:
            c = Util.DICT_GET(self.color_cache, color)
            if c is None:
                c = matplotlib.colors.cnames[color]
                pc = pygame.Color(c)
                c = (pc.r, pc.g, pc.b)
                self.color_cache[color] = c
        except:
            c = color
        if c is None:
            c = (0, 0, 0)
        self.color = c

    def _render_color_rgb(self, r, g, b):
        try:
            self.strip[self.position] = (r, g, b) # Set the pixel color
        except:
            logging.warning("Failed to set LED pixel color for pixel %d", self.position)
            pass
