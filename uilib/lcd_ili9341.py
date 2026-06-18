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

import pygame
from PIL import Image

from uilib.panel import LcdBase, Box
from functools import cached_property
import logging
import threading
import os

INIT_STAMP = "/run/lcd.init"


class LcdIli9341(LcdBase):
    # TODO: Turn "flip" into all 90deg angle combinations
    def __init__(self, spi, cs_pin, dc_pin, reset_pin, baudrate, flip=True):
        from uilib import driver_patch
        driver_patch.apply()
        import adafruit_rgb_display.ili9341 as ili9341
        rst = reset_pin if not self.has_system_splash else None
        self.disp = ili9341.ILI9341(spi, cs=cs_pin, dc=dc_pin, rst=rst, baudrate=baudrate)

        self.lock = threading.Lock()

        if not self.has_system_splash:
            self.clear()
            self._set_stamp()

        # Portrait dimensions (the panel itself is landscape; we rotate at push).
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

    def update(self, surface: pygame.Surface, box=None):
        """Push (a sub-rect of) the composed pygame surface to the LCD.

        Converts surface → packed RGB888 bytes → PIL.Image at the seam and
        hands it to adafruit_rgb_display, which handles the SPI bulk write."""
        if self.lock.locked():
            logging.debug("LCD update was locked by another thread")
        self.lock.acquire()
        try:
            img_width, img_height = surface.get_size()
            if box is None:
                box = Box(0, 0, img_width, img_height)

            x1, y1, x2, y2 = box.rect
            x1 = max(0, min(x1, img_width))
            y1 = max(0, min(y1, img_height))
            x2 = max(x1, min(x2, img_width))
            y2 = max(y1, min(y2, img_height))

            cropped = x1 != 0 or y1 != 0 or x2 != img_width or y2 != img_height
            if cropped:
                sub_rect = pygame.Rect(x1, y1, x2 - x1, y2 - y1)
                sub = surface.subsurface(sub_rect)
                if self.flip:
                    x, y = self.height - y2, x1
                else:
                    x, y = y1, self.width - x2
            else:
                sub = surface
                x, y = 0, 0

            rgb_bytes = pygame.image.tobytes(sub, "RGB")
            pil_img = Image.frombytes("RGB", sub.get_size(), rgb_bytes)
            self.disp.image(pil_img, 270 if self.flip else 90, x, y)
        finally:
            self.lock.release()
