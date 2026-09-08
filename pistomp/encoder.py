# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gpiozero import RotaryEncoder


class Encoder:
    """Hardware rotary encoder backed by gpiozero's quadrature decoder.

    Public API: read_rotary() -> int (returns accumulated direction, clears accumulator).
    """

    DEFAULT_MAX_DRAIN = 8

    def __init__(self, d_pin: int | None, clk_pin: int | None, max_drain: int = DEFAULT_MAX_DRAIN):
        self.d_pin = d_pin
        self.clk_pin = clk_pin
        self.max_drain = max_drain
        self._lock = threading.Lock()
        self.direction = 0
        self._rotary: RotaryEncoder | None = None

        if d_pin is not None and clk_pin is not None:
            from gpiozero import RotaryEncoder

            self._rotary = RotaryEncoder(d_pin, clk_pin, bounce_time=None, max_steps=0)
            self._rotary.when_rotated_clockwise = self._clockwise
            self._rotary.when_rotated_counter_clockwise = self._counter_clockwise

    def __del__(self):
        if self._rotary is not None:
            self._rotary.close()

    def _clockwise(self, _: RotaryEncoder) -> None:
        with self._lock:
            self.direction += 1

    def _counter_clockwise(self, _: RotaryEncoder) -> None:
        with self._lock:
            self.direction -= 1

    def read_rotary(self) -> int:
        """Return accumulated direction since the last call, capped to ±max_drain."""
        with self._lock:
            if self.direction > 0:
                d = min(self.direction, self.max_drain)
            elif self.direction < 0:
                d = max(self.direction, -self.max_drain)
            else:
                d = 0
            self.direction -= d
            return d
