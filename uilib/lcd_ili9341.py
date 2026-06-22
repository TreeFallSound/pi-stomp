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
import numpy as np

from uilib.panel import LcdBase, Box
from uilib.spi_timing import transfer_ms as spi_transfer_ms
from uilib import profiling
import logging
import threading
import os

INIT_STAMP = "/run/lcd.init"


try:
    with open("/sys/module/spidev/parameters/bufsiz", "r") as _f:
        SPIDEV_BUFSIZ = int(_f.read().strip())
except Exception:
    SPIDEV_BUFSIZ = 4096


class LcdIli9341(LcdBase):
    # TODO: Turn "flip" into all 90deg angle combinations
    def __init__(self, spi, cs_pin, dc_pin, reset_pin, baudrate, flip=True):
        import adafruit_rgb_display.ili9341 as ili9341

        rst = reset_pin if not self.has_system_splash else None
        self.disp = ili9341.ILI9341(spi, cs=cs_pin, dc=dc_pin, rst=rst, baudrate=baudrate)
        self.disp._block = self._block_fast
        self.baudrate = baudrate

        self.lock = threading.Lock()

        # FIXME: we should be able to bypass the init() altogether to avoid clearing
        # it's pretty clear we need to fork adafruit_rgb_display...
        # idea: maybe we can query the display's current state and only run init() if it's uninitialized?

        if not self.has_system_splash:
            self.clear()  # full-panel black while still in Adafruit's portrait MADCTL
            self._set_stamp()

        self.flip = flip
        # Drive the panel landscape-native so the 320x240 surface pushes row-major
        # with no np.rot90 at update() time. Adafruit's init leaves MADCTL=0x48
        # (portrait); re-assert lcd-splash's 0xE8 (MY|MX|MV|BGR). Non-flip drops
        # the MX|MY mirror bits -> 0x28 (MV|BGR).
        self._madctl = 0x28 if flip else 0xE8
        self.disp.write(0x36, bytes([self._madctl]))

        # Landscape dimensions presented to the UI (matches the panel post-MADCTL).
        self.width = self.disp.height  # 320
        self.height = self.disp.width  # 240
        self._pixels = np.empty((self.height, self.width, 2), dtype=np.uint8)

    def _block_fast(self, x0, y0, x1, y1, data=None):
        """Bypass adafruit_rgb_display's write method to perform a block write
        with a single SPI bus lock and CS pin assertion instead of six,
        and write directly using os.write to avoid Blinka/Adafruit PureIO copy overheads."""
        if data is None:
            import adafruit_rgb_display.rgb as rgb

            return rgb.DisplaySPI._block(self.disp, x0, y0, x1, y1, data)

        disp = self.disp
        spi_dev = disp.spi_device
        spi = spi_dev.spi
        cs = spi_dev.chip_select
        dc = disp.dc_pin
        pure_spi = spi._spi._spi
        fd = pure_spi.handle

        # Acquire the lock once
        while not spi.try_lock():
            import time

            time.sleep(0)

        try:
            # Configure bus once
            spi.configure(baudrate=spi_dev.baudrate, polarity=spi_dev.polarity, phase=spi_dev.phase)

            # Assert CS once
            if cs:
                cs.value = spi_dev.cs_active_value

            # Send column coordinates
            dc.value = 0
            os.write(fd, bytes([disp._COLUMN_SET]))
            dc.value = 1
            os.write(fd, disp._encode_pos(x0 + disp._X_START, x1 + disp._X_START))

            # Send page/row coordinates
            dc.value = 0
            os.write(fd, bytes([disp._PAGE_SET]))
            dc.value = 1
            os.write(fd, disp._encode_pos(y0 + disp._Y_START, y1 + disp._Y_START))

            # Write pixel data
            dc.value = 0
            os.write(fd, bytes([disp._RAM_WRITE]))
            dc.value = 1

            # Zero-copy chunked write using memoryview to comply with kernel spidev bufsiz
            mv = memoryview(data)
            for i in range(0, len(data), SPIDEV_BUFSIZ):
                os.write(fd, mv[i : i + SPIDEV_BUFSIZ])

        finally:
            # De-assert CS once
            if cs:
                cs.value = not spi_dev.cs_active_value
            # Release lock once
            spi.unlock()

    @property
    def has_system_splash(self) -> bool:
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

    def transfer_ms(self, box=None):
        w, h = (self.width, self.height) if box is None else (box.width, box.height)
        return spi_transfer_ms(w * h, self.baudrate)

    def clear(self):
        self.lock.acquire()
        self.disp.fill(0)
        self.lock.release()

    def update(self, image: pygame.Surface, box=None):
        """Push (a sub-rect of) the composed pygame surface to the LCD.

        Converts surface → RGB888 bytes → packed RGB565, writing via Display._block
        to bypass PIL. The panel runs landscape-native (MADCTL set in __init__) so
        no rotation is needed."""
        if self.lock.locked():
            logging.debug("LCD update was locked by another thread")
        self.lock.acquire()
        try:
            img_width, img_height = image.get_size()
            if box is None:
                box = Box(0, 0, img_width, img_height)

            x1, y1, x2, y2 = box.rect
            x1 = max(0, min(x1, img_width))
            y1 = max(0, min(y1, img_height))
            x2 = max(x1, min(x2, img_width))
            y2 = max(y1, min(y2, img_height))

            cropped = x1 != 0 or y1 != 0 or x2 != img_width or y2 != img_height
            sub = image.subsurface(pygame.Rect(x1, y1, x2 - x1, y2 - y1)) if cropped else image

            # Landscape-native: surface coords map straight to the panel address
            # window, so the RGB565 sub-rect ships row-major with no rotation.
            sw, sh = sub.get_size()
            with profiling.measure("lcd.update:pack"):
                arr = pygame.surfarray.pixels3d(sub).transpose(1, 0, 2)

                pix = self._pixels[:sh, :sw]
                g = arr[:, :, 1]
                pix[:, :, 0] = (arr[:, :, 0] & 0xF8) | (g >> 5)
                pix[:, :, 1] = ((g & 0x1C) << 3) | (arr[:, :, 2] >> 3)
                pixels_bytes = pix.tobytes()

            with profiling.measure("lcd.update:_block(SPI)"):
                self.disp._block(x1, y1, x1 + sw - 1, y1 + sh - 1, pixels_bytes)
        finally:
            self.lock.release()
