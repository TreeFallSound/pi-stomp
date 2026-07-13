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

import math
from pathlib import Path
from typing import NamedTuple, Optional

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


def soc_key() -> Optional[str]:
    """Device-tree `compatible` entry naming the running SoC, if we know it."""
    try:
        raw = _DT_COMPATIBLE.read_bytes()
    except OSError:
        return None
    for entry in raw.decode("ascii", errors="replace").split("\0"):
        if entry in SPI_SOURCE_HZ:
            return entry
    return None


def spi_source_hz() -> int:
    """SPI controller source clock for the running host."""
    soc = soc_key()
    return DEFAULT_SOURCE_HZ if soc is None else SPI_SOURCE_HZ[soc]


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


# The push cost is affine:
#   fixed per-call  +  clock-independent per-pixel  +  bits-on-the-wire / clock
#
# fixed and per-pixel are CPU-bound, so they are *per-SoC* -- an A53 at 1.2 GHz is
# nothing like an A76 at 2.4 GHz, and v2's per-pixel cost is 6.2x v3's. Sharing one
# global would let v3's cheap per-pixel cost admit a 31.7k-px clip inline on v2 that
# really costs 9.6 ms, against an 8 ms budget on a 10 ms tick. Underestimating is the
# unsafe direction -- transfer_ms gates inline pushes onto the UI thread
# (panel.py INLINE_BUDGET_MS).
#
# Refit with tools/bench_lcd_device.py, on each board, whenever the pack path changes.


class PushProfile(NamedTuple):
    fixed_ms: float  # address-window commands + Python/driver call overhead
    pipeline_ms_per_px: float  # 565 convert-blit + driver; no cheaper on a faster clock
    bits_per_pixel: float  # ~16 (RGB565); the fit converging there means no framing


# Fit from on-device timing of LcdIli9341.update() across three clocks per board
# (Python 3.13, SDL convert-blit pack). Errors: v3 rms 0.4%, v2 rms 3.1%.
_PI3 = PushProfile(1.2008, 2.3647e-05, 15.923)  # Pi 3A+ (v2), fit @ 20/40/66.7 MHz

PUSH_PROFILE: dict[str, PushProfile] = {
    "brcm,bcm2837": _PI3,
    "brcm,bcm2711": _PI3,  # Pi 4 unmeasured; the slower board is the safe guess
    "brcm,bcm2712": PushProfile(0.2727, 3.8290e-06, 16.032),  # Pi 5 (v3) @ 20/33.3/50 MHz
}

# Off-device (tests, emulator) — matches DEFAULT_SOURCE_HZ's Pi 5 assumption.
DEFAULT_PROFILE = PUSH_PROFILE["brcm,bcm2712"]


def push_profile() -> PushProfile:
    """Affine push-cost model for the running host.

    An unrecognised SoC on a *real* board (a Pi 2, a future Pi 6) gets the slowest
    profile we have, not the default: overestimating only defers a push to the
    worker, while underestimating stalls the poll loop.
    """
    soc = soc_key()
    if soc is not None:
        return PUSH_PROFILE[soc]
    return DEFAULT_PROFILE if not _DT_COMPATIBLE.exists() else _PI3


def transfer_ms(pixels: int, spi_hz: float) -> float:
    """Estimated milliseconds to push `pixels` to an SPI display at `spi_hz`."""
    p = push_profile()
    wire_ms = pixels * p.bits_per_pixel / spi_hz * 1000
    return p.fixed_ms + pixels * p.pipeline_ms_per_px + wire_ms
