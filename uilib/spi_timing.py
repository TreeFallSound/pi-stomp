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

Callers must pass the *actual* clock, not the requested one — see actual_spi_hz.
"""

import math
from pathlib import Path
from typing import Optional

_DT_COMPATIBLE = Path("/proc/device-tree/compatible")

# SPI controller source clock by SoC. spi-bcm2835 (Pi <=4) divides the VPU core
# clock; spi-dw (Pi 5, inside RP1) divides RP1_CLK_SYS.
SPI_SOURCE_HZ: dict[str, int] = {
    "brcm,bcm2837": 400_000_000,  # Pi 3 (v2)
    "brcm,bcm2711": 500_000_000,  # Pi 4
    "brcm,bcm2712": 200_000_000,  # Pi 5 (v3)
}

# Off-device (tests, emulator).
DEFAULT_SOURCE_HZ: int = 200_000_000


def spi_source_hz() -> int:
    """SPI controller source clock for the running host."""
    try:
        raw = _DT_COMPATIBLE.read_bytes()
    except OSError:
        return DEFAULT_SOURCE_HZ
    for entry in raw.decode("ascii", errors="replace").split("\0"):
        source = SPI_SOURCE_HZ.get(entry)
        if source is not None:
            return source
    return DEFAULT_SOURCE_HZ


def actual_spi_hz(requested_hz: float, source_hz: Optional[int] = None) -> float:
    """The clock the SPI controller will really run at for `requested_hz`.

    Both drivers take ceil(source / requested) then round that divisor up to an
    even number, so the achieved clock lands on source/even and never exceeds
    the request. One hertz below an exact divisor point costs a whole step: on a
    Pi 3, 66_666_666 gives 50 MHz and 66_666_667 gives 66.67 MHz.
    """
    if requested_hz <= 0:
        raise ValueError(f"requested_hz must be positive, got {requested_hz}")
    source = spi_source_hz() if source_hz is None else source_hz

    # Integer DIV_ROUND_UP; float division rounds the wrong way at divisor points.
    divisor = -(-source // math.floor(requested_hz))
    if divisor < 2:
        divisor = 2
    elif divisor % 2:
        divisor += 1
    return source / divisor

# Constants fit from on-device timing of LcdIli9341.update() at 20 MHz, 33.3 MHz,
# and 50 MHz actual (Pi 5 / Python 3.14, tools/bench_lcd_device.py).
#
# DW APB SSI BAUDR rounding means only these speeds are achievable:
#   request 20 MHz (BAUDR=10) → 20.00 MHz actual
#   request 34–49 MHz (BAUDR=6) → 33.33 MHz actual
#   request 50–99 MHz (BAUDR=4) → 50.00 MHz actual
#
# The push cost is affine:
#   fixed per-call  +  clock-independent per-pixel  +  bits-on-the-wire / clock
#
# Fit holds within ~1% across all three clocks and the full size range.

# Wire bits per pixel: 16 (RGB565). The fit converges very close to 16,
# confirming negligible framing overhead at these clock speeds.
BITS_PER_PIXEL = 16.0071

# Clock-independent per-pixel cost: numpy 565 packing + driver. Doesn't get
# cheaper with a faster clock, so it floors how fast large pushes can go.
PIPELINE_MS_PER_PX = 5.856e-05

# Fixed per-call cost: address-window commands + Python/driver call overhead.
FIXED_MS = 0.7117


def transfer_ms(pixels: int, spi_hz: float) -> float:
    """Estimated milliseconds to push `pixels` to an SPI display at `spi_hz`."""
    wire_ms = pixels * BITS_PER_PIXEL / spi_hz * 1000
    return FIXED_MS + pixels * PIPELINE_MS_PER_PX + wire_ms
