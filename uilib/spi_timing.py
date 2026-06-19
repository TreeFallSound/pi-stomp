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

"""Shared SPI-display transfer-cost model.

One source of truth for "how long does it take to push N pixels at this SPI
clock", used by the LCD drivers' transfer_ms (the inline-push gate), the
emulator's transfer-time simulation, and lcd320x240's poll_divisor.
"""

# Constants fit from on-device timing of LcdIli9341.update() at 24 and 80 MHz
# (tools/bench_lcd_device.py), Pi 5 / Python 3.14. The push cost is affine:
#
#   fixed per-call  +  clock-independent per-pixel  +  bits-on-the-wire / clock
#
# The fit holds within ~1% across both clocks and the full size range.

# Wire bits per pixel: 16 (RGB565) plus measured SPI framing / clock-divisor
# quantization overhead. Only this term shrinks as the clock rises.
BITS_PER_PIXEL = 16.64

# Clock-independent per-pixel cost: numpy 565 packing + driver. Doesn't get
# cheaper with a faster clock, so it floors how fast large pushes can go.
PIPELINE_MS_PER_PX = 1.66e-4

# Fixed per-call cost: address-window commands + Python/driver call overhead.
FIXED_MS = 0.64


def transfer_ms(pixels: int, spi_hz: float) -> float:
    """Estimated milliseconds to push `pixels` to an SPI display at `spi_hz`."""
    wire_ms = pixels * BITS_PER_PIXEL / spi_hz * 1000
    return FIXED_MS + pixels * PIPELINE_MS_PER_PX + wire_ms
