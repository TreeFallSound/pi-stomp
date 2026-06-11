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

import queue
import threading
import time

import pygame
from uilib.panel import LcdBase


class LcdPygame(LcdBase):
    """LCD implementation that renders into a pygame Surface.

    SPI transfers run on a background worker thread so the main thread
    (pygame event polling + encoder handling) stays responsive during long
    transfers, which block for a simulated amount of time on the SPI thread.
    """

    # Bits per pixel clocked over SPI: the ILI9341 takes RGB565 on the wire.
    _BPP = 16

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
        self._queue = queue.Queue()
        self._worker = threading.Thread(target=self._spi_worker, daemon=True)
        self._worker.start()

    def _spi_worker(self):
        while True:
            pg_surf, dest, transfer_s, t0 = self._queue.get()
            self.surface.blit(pg_surf, dest)
            self._queue.task_done()
            deficit = transfer_s - (time.perf_counter() - t0)
            if deficit >= self._SLEEP_THRESHOLD_S:
                time.sleep(deficit)

    def dimensions(self):
        return (self.width, self.height)

    def default_format(self):
        return "RGB"

    def update(self, surface: pygame.Surface, box=None):
        img_w, img_h = surface.get_size()

        if box is not None:
            x0, y0, x1, y1 = box.rect
            x0 = max(0, min(x0, img_w))
            y0 = max(0, min(y0, img_h))
            x1 = max(x0, min(x1, img_w))
            y1 = max(y0, min(y1, img_h))
            # Crop to the dirty region if the surface is larger
            if x0 != 0 or y0 != 0 or x1 != img_w or y1 != img_h:
                surface = surface.subsurface(pygame.Rect(x0, y0, x1 - x0, y1 - y0))
            dest = (x0, y0)
        else:
            dest = (0, 0)

        # Copy on the main thread so the caller can keep mutating its surface;
        # the worker only ever touches this detached snapshot.
        pg_surf = surface.copy()
        w, h = pg_surf.get_size()
        transfer_s = (w * h * self._BPP) / self.spi_hz
        self._queue.put((pg_surf, dest, transfer_s, time.perf_counter()))

    def blit_scaled(self, dest_surface, dest_rect):
        """
        Scale the LCD surface to dest_rect and blit it onto dest_surface.
        Blocks until all queued SPI transfers have been applied to
        self.surface, so the snapshot is always consistent.
        """
        self._queue.join()
        scaled = pygame.transform.scale(self.surface, (dest_rect.width, dest_rect.height))
        dest_surface.blit(scaled, dest_rect.topleft)
