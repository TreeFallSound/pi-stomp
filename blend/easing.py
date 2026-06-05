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

"""Easing functions that shape knob feel for blend mode."""

import math
from typing import Callable


def linear(t: float) -> float:
    return t


def smooth(t: float) -> float:
    """Ease-in-out cubic: slow at both ends, expressive in the middle."""
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - 4.0 * (1.0 - t) ** 3


def build(t: float) -> float:
    """Ease-in cubic: gradual start, rushes at the far end."""
    return t * t * t


def drop(t: float) -> float:
    """Ease-out cubic: grabs immediately, fine-tunes at the far end."""
    return 1.0 - (1.0 - t) ** 3


def snap(t: float) -> float:
    """Exponential: stays near start, sudden jump at the far end."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return (2.0 ** (10.0 * t) - 1.0) / (2.0 ** 10.0 - 1.0)


def bloom(t: float) -> float:
    """Square root: immediate big shift, then plateaus."""
    return math.sqrt(t)


EasingFunc = Callable[[float], float]

EASING_FUNCTIONS: dict[str, EasingFunc] = {
    "linear": linear,
    "smooth": smooth,
    "build": build,
    "drop": drop,
    "snap": snap,
    "bloom": bloom,
}
