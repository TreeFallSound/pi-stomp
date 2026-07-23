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


import math
from typing import Any


def LILV_FOREACH(collection, func):
    itr = collection.begin()
    while itr:
        yield func(collection.get(itr))
        itr.next()
        if itr.is_end():
            break


def DICT_GET(d, key) -> Any:
    if key in d:
        return d[key]
    else:
        return None


def renormalize(n, left_min, left_max, right_min, right_max):
    # this remaps a value from original (left) range to new (right) range
    # Figure out how 'wide' each range is
    delta1 = left_max - left_min
    delta2 = right_max - right_min
    return round((delta2 * (n - left_min) / delta1) + right_min)


def to_normalized(value: float, minimum: float, maximum: float, logarithmic: bool = False) -> float:
    """Value → [0,1] position in [minimum, maximum], honoring the port taper.
    Inverse of from_normalized. Logarithmic ports are geometric — the taper that
    mod-host applies to a MIDI-CC-addressed control, so the CC we emit must invert
    it or the port lands on the wrong value. Falls back to linear when a log range
    is non-positive (undefined), which log ports never are."""
    if logarithmic and minimum > 0.0 and maximum > 0.0:
        return math.log(value / minimum) / math.log(maximum / minimum)
    span = maximum - minimum
    return (value - minimum) / span if span else 0.0


def from_normalized(position: float, minimum: float, maximum: float, logarithmic: bool = False) -> float:
    """[0,1] position → value. Mirrors mod-host's CC→value mapping (geometric for
    logarithmic ports); the inverse of to_normalized."""
    if logarithmic and minimum > 0.0 and maximum > 0.0:
        return minimum * (maximum / minimum) ** position
    return minimum + position * (maximum - minimum)


def renormalize_float(value, left_min, left_max, right_min, right_max):
    # this remaps a value from original (left) range to new (right) range
    # Figure out how 'wide' each range is
    left_span = abs(left_max - left_min)
    num_divisions = left_span / value

    right_span = abs(right_max - right_min)

    return round(right_span / num_divisions, 2)


def format_float(value):
    if value < 10:
        if value < 1:
            return "%.2f" % value
        else:
            return "%.1f" % value
    else:
        return "%d" % value
