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

import pygame
from uilib.panel import LcdBase


class LcdPygame(LcdBase):
    """LCD implementation that renders into a pygame Surface.

    Simulates SPI transfer latency so partial zone refreshes stay snappy
    but full-screen redraws feel sluggish the way they do on the device.
    Default matches the ILI9341 wiring in lcdili9341.py (24 MHz, RGB565).
    """

    # Bits per pixel when clocked over SPI. PIL 'RGB' is 24bpp in memory but
    # ILI9341 takes RGB565 on the wire; '1'/'L' are mono/8bpp for small OLEDs.
    _BPP_BY_MODE = {"1": 1, "L": 8, "RGB": 16, "RGBA": 16}

    # time.sleep() on macOS has ~1 ms granularity, so sleeping for values
    # smaller than this just burns wall-clock time waking up. Below the
    # threshold we skip the sleep — pygame's own blit overhead already
    # eats a few hundred µs per call which roughly approximates SPI cost
    # at this scale.
    _SLEEP_THRESHOLD_S = 0.001

    def __init__(self, width=320, height=240, spi_hz=24_000_000):
        self.width = width
        self.height = height
        self.spi_hz = spi_hz
        self.surface = pygame.Surface((width, height))

    def dimensions(self):
        return (self.width, self.height)

    def default_format(self):
        return 'RGB'

    def update(self, image, box=None):
        img_w, img_h = image.size

        if box is not None:
            x0, y0, x1, y1 = box.rect
            x1 = min(x1, self.width)
            y1 = min(y1, self.height)
            # Crop if the image is larger than the dirty region
            if x0 != 0 or y0 != 0 or x1 != img_w or y1 != img_h:
                image = image.crop((x0, y0, x1, y1))
            dest = (x0, y0)
        else:
            dest = (0, 0)

        t0 = time.perf_counter()
        pg_surf = pygame.image.fromstring(image.tobytes(), image.size, image.mode)
        self.surface.blit(pg_surf, dest)
        blit_elapsed = time.perf_counter() - t0

        bpp = self._BPP_BY_MODE.get(image.mode, 16)
        transfer_s = (image.size[0] * image.size[1] * bpp) / self.spi_hz
        deficit = transfer_s - blit_elapsed
        if deficit >= self._SLEEP_THRESHOLD_S:
            time.sleep(deficit)

    def blit_scaled(self, dest_surface, dest_rect):
        """Scale the LCD surface to dest_rect and blit it onto dest_surface."""
        scaled = pygame.transform.scale(self.surface, (dest_rect.width, dest_rect.height))
        dest_surface.blit(scaled, dest_rect.topleft)
