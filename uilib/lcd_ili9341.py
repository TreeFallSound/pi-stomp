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

import adafruit_rgb_display.ili9341 as ili9341

from uilib.panel import LcdBase, Box
from functools import cached_property
import logging
import threading
import os

INIT_STAMP = "/run/lcd.init"


class LcdIli9341(LcdBase):
    # XXX
    # TODO: Turn "flip" into all 90deg angle combinations
    def __init__(self, spi, cs_pin, dc_pin, reset_pin, baudrate, flip=True):
        rst = reset_pin if not self.has_system_splash else None

        self.disp = ili9341.ILI9341(spi, cs=cs_pin, dc=dc_pin, rst=rst, baudrate=baudrate)

        # Use this to assure we don't have multiple threads trying to change the screen
        # All methods which do change the screen (eg. dist. calls) should acquire/release
        self.lock = threading.Lock()

        if not self.has_system_splash:
            self.clear()
            self._set_stamp()

        # Test full screen image
        self.width = self.disp.height
        self.height = self.disp.width
        self.flip = flip

    @cached_property
    def has_system_splash(self):
        """Does the OS provide a splash screen?"""
        return os.path.exists(INIT_STAMP)

    def _set_stamp(self):
        try:
            with open(INIT_STAMP, "w") as _f:
                pass
        except Exception:
            pass

    def dimensions(self):
        return (self.width, self.height)

    def default_format(self):
        return "RGB"

    def clear(self):
        self.lock.acquire()
        self.disp.fill(0)
        self.lock.release()

    def update(self, image, box = None):
        if self.lock.locked():
            logging.debug("LCD update was locked by another thread")
        self.lock.acquire()
        # LCD coordinates
        #
        # portrait mode, connector = bottom
        #
        # on pi-stomp, X=0 is "bottom" (away from jacks)
        #              Y=0 is "left" (out jack side)
        #
        img_width, img_height = image.size
        if box is None:
            box = Box(0, 0, img_width, img_height)

        # Check if we need to crop the image to the LCD size
        x1, y1, x2, y2 = box.rect
        if x2 > self.width:
            x2 = self.width
        if y2 > self.height:
            y2 = self.height
        if x1 != 0 or y1 != 0 or x2 != img_width or y2 != img_width:
            image = image.crop((x1, y1, x2, y2))
            if self.flip:
                x = self.height - y2
                y = x1
            else:
                x = y1
                y = self.width - x2
        self.disp.image(image, 270 if self.flip else 90, x, y)
        self.lock.release()

