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

from __future__ import annotations

import threading
from typing import Any


class Encoder:
    """Pure hardware quadrature decoder. Owns GPIO pins and direction state.
    No controller concerns (no sink, no quantizer, no parameter).

    Public API: read_rotary() -> int (returns accumulated direction, clears accumulator).
    """

    # Cap on how many detents are drained per poll tick.
    MAX_DRAIN = 8

    def __init__(self, d_pin: int | None, clk_pin: int | None):
        self.d_pin = d_pin
        self.clk_pin = clk_pin
        self._lock = threading.Lock()
        self.data: Any = None
        self.clk: Any = None
        if d_pin is not None:
            from gpiozero import Button  # pyright: ignore[reportMissingImports]

            self.data = Button(d_pin)
            self.data.when_pressed = self._gpio_callback
            self.data.when_released = self._gpio_callback
            self.clk = Button(clk_pin)
            self.clk.when_pressed = self._gpio_callback
            self.clk.when_released = self._gpio_callback

        self.prevNextCode = 0
        self.store = 0
        self.direction = 0
        # 16 grey codes; 1 = valid transition, 0 = bounce.
        self.rot_enc_table = [0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0]

    def __del__(self):
        if self.data is not None:
            self.data.close()
        if self.clk is not None:
            self.clk.close()

    def _process_gpios(self) -> int:
        # https://www.best-microcontroller-projects.com/rotary-encoder.html
        self.prevNextCode <<= 2
        if self.data.value:
            self.prevNextCode |= 0x02
        if self.clk.value:
            self.prevNextCode |= 0x01
        self.prevNextCode &= 0x0F

        direction = 0
        if self.rot_enc_table[self.prevNextCode]:
            self.store <<= 4
            self.store |= self.prevNextCode
            if (self.store & 0xFF) == 0x2B:
                direction = 1
            if (self.store & 0xFF) == 0x17:
                direction = -1
        if direction != 0:
            self.store = self.prevNextCode
        return direction

    def _gpio_callback(self, channel):
        d = self._process_gpios()
        if d != 0:
            with self._lock:
                self.direction += d

    def read_rotary(self) -> int:
        """Return accumulated direction since the last call, capped to ±MAX_DRAIN.

        Drains the full accumulator (up to MAX_DRAIN) so that fast spins
        deliver a batched count in one EncoderEvent rather than ±1 per tick.
        Returns 0 when no ISR edges have fired since the last call.
        """
        if self.direction != 0:
            with self._lock:
                if self.direction > 0:
                    d = min(self.direction, self.MAX_DRAIN)
                else:
                    d = max(self.direction, -self.MAX_DRAIN)
                self.direction -= d
        else:
            d = 0
        return d
