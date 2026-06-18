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

"""Monkeypatch the adafruit_rgb_display ILI9341 driver for faster transfers.

The upstream ``image_to_data`` (adafruit-circuitpython-rgb-display 3.14.3,
``adafruit_rgb_display/rgb.py``) ends with::

    return numpy.dstack(...).flatten().tolist()

``.flatten().tolist()`` builds a Python list of ~W*H int objects (one per
pixel), then the caller wraps it in ``bytes(...)`` which walks that list
again to pack it. On a Raspberry Pi this is the single most expensive step
of the per-frame transfer path — measured at ~3.5ms for a 320x240 frame
vs ~1.35ms for the vectorised version below (2.6x speedup, see
``tools/bench_lcd_transfer.py``).
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)

_PATCHED = False


def apply() -> None:
    """Patch ``adafruit_rgb_display.rgb.image_to_data`` in place.

    Idempotent; safe to call more than once. Uses the
    ``__patched_by_pistomp__`` sentinel attribute on the target function
    to detect prior patches, which survives module reloads.
    """
    global _PATCHED
    if _PATCHED:
        return

    try:
        import adafruit_rgb_display.rgb as rgb  # pyright: ignore[reportMissingImports]
    except ImportError:
        _logger.warning("adafruit_rgb_display not found; skipping driver patch")
        return

    if getattr(rgb.image_to_data, "__patched_by_pistomp__", False):
        _PATCHED = True
        return

    import numpy

    def image_to_data_fast(image):
        data = numpy.array(image.convert("RGB")).astype("uint16")
        color = ((data[:, :, 0] & 0xF8) << 8) | ((data[:, :, 1] & 0xFC) << 3) | (data[:, :, 2] >> 3)
        packed = numpy.dstack(((color >> 8) & 0xFF, color & 0xFF)).astype(numpy.uint8)
        return packed.tobytes()

    image_to_data_fast.__patched_by_pistomp__ = True  # pyright: ignore[reportFunctionMemberAccess]
    rgb.image_to_data = image_to_data_fast
    _PATCHED = True
    _logger.info("Patched adafruit_rgb_display.rgb.image_to_data (tobytes variant)")


if __name__ == "__main__":
    apply()
