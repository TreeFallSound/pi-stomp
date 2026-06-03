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

"""Software stubs for the three gfxhat modules (lcd, backlight, touch).

GfxLcd renders to a LcdPygame backend via set_pixel/show.
GfxBacklight and GfxTouch are no-ops.
"""

from PIL import Image


class GfxLcd:
    def __init__(self, lcd_pygame, width=128, height=64):
        self._pygame = lcd_pygame
        self._w = width
        self._h = height
        self._buf = Image.new('L', (width, height))

    def dimensions(self):
        return (self._w, self._h)

    def set_pixel(self, x, y, val):
        if 0 <= x < self._w and 0 <= y < self._h:
            self._buf.putpixel((x, y), 255 if val else 0)

    def show(self):
        # Production code stores pixels with both axes inverted (hardware orientation).
        # Rotate 180° to recover the correct image for pygame display.
        img = self._buf.transpose(Image.ROTATE_180)
        self._pygame.update(img.convert('RGB'))

    def clear(self):
        self._buf.paste(0, (0, 0, self._w, self._h))


class GfxBacklight:
    def set_pixel(self, x, r, g, b):
        pass

    def set_all(self, r, g, b):
        pass

    def show(self):
        pass


class GfxTouch:
    def set_led(self, i, val):
        pass
