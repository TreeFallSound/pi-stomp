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

"""Quantized step grid for encoder-driven parameter edits.

Shared by EncoderController (v3 tweak encoders) and Parameterdialog (the nav
encoder, which is the only encoder on v2), so that one detent moves a parameter
by the same amount whichever control you turn.
"""

import bisect
from typing import List

from common.parameter import Parameter, Type

# Steps for a continuous parameter. Matches the 0-127 MIDI CC range, so a full
# sweep of a CC-bound encoder emits every distinct MIDI value.
CONTINUOUS_STEPS = 128

# A full-speed spin should cross a parameter's whole grid in roughly this many
# detents, regardless of the grid's resolution. The encoder's raw multiplier
# (time-based, 1× at REFERENCE_DT_MS) is mapped onto the per-parameter step
# range so a 43k-step integer log knob sweeps as fast as a 128-step continuous
# one. Slow spins (multiplier ≤ 1) always yield one step per detent, so every
# notch of a stepped range stays reachable.
FULL_SWEEP_DETENTS = 32
# The raw multiplier at which a spin counts as "full speed" — the historic
# MAX_MULTIPLIER. At or above this, the per-parameter cap binds; below it,
# the multiplier is interpolated linearly between 1 step/detent and the cap.
REFERENCE_FAST_MULTIPLIER = 4.0


def resolution(parameter: Parameter | None) -> int:
    """Detents needed to cross the parameter's range.

    An unbound encoder (parameter is None) is a free-running CC: give it the
    full 128-value sweep. A bound discrete parameter gets one detent per
    distinct value — extra steps would emit no additional MIDI values, since
    the CC is derived from the parameter.
    """
    if parameter is None:
        return CONTINUOUS_STEPS
    match parameter.type:
        case Type.INTEGER:
            return int(parameter.maximum - parameter.minimum) + 1
        case Type.ENUMERATION:
            return len(parameter.get_enum_value_list())
        case Type.TOGGLED:
            return 2
        case _:
            return CONTINUOUS_STEPS


def effective_multiplier(multiplier: float, parameter: Parameter | None) -> float:
    """The multiplier actually applied to a parameter edit.

    Maps the encoder's raw speed multiplier onto the parameter's step range
    so a full-speed spin covers the same fraction of any grid in roughly the
    same number of detents. At ``multiplier == 1`` (slow) every detent moves
    one step — every notch of a stepped range is reachable. At
    ``multiplier >= REFERENCE_FAST_MULTIPLIER`` (full speed) each detent moves
    ``resolution / FULL_SWEEP_DETENTS`` steps, so the whole range sweeps in
    ~32 detents regardless of grid size.
    """
    res = resolution(parameter)
    cap = res / FULL_SWEEP_DETENTS
    if cap <= 1.0:
        return multiplier  # small grid: precision floor, no scaling
    if multiplier <= 1.0:
        return multiplier  # slow: 1 step/detent, every notch reachable
    if multiplier >= REFERENCE_FAST_MULTIPLIER:
        return cap
    # Linear ramp: m=1 → 1 step/detent, m=4 → cap steps/detent.
    return 1.0 + (multiplier - 1.0) * (cap - 1.0) / (REFERENCE_FAST_MULTIPLIER - 1.0)


class ParameterSteps:
    """A tapered grid of reachable values, plus a cursor into it."""

    def __init__(self, minimum: float, maximum: float, taper: float, num_steps: int):
        self.num_steps = num_steps
        self.index = 0
        self.values: List[float] = []
        if num_steps <= 1:
            self.values = [minimum]
            return
        rng = maximum - minimum
        for i in range(num_steps):
            self.values.append(minimum + rng * ((i / (num_steps - 1)) ** taper))

    @classmethod
    def for_parameter(cls, parameter: Parameter) -> "ParameterSteps":
        steps = cls(parameter.minimum, parameter.maximum, parameter.get_taper(), resolution(parameter))
        steps.set_value(parameter.value)
        return steps

    @property
    def value(self) -> float:
        return self.values[self.index]

    def set_value(self, value: float) -> None:
        """Snap the cursor to the nearest step. Used to resync after an
        external change (MOD-UI echo, another control)."""
        idx = bisect.bisect_left(self.values, value)
        if idx == 0:
            self.index = 0
        elif idx == len(self.values):
            self.index = len(self.values) - 1
        elif abs(self.values[idx - 1] - value) <= abs(self.values[idx] - value):
            self.index = idx - 1
        else:
            self.index = idx

    def move(self, delta_steps: int) -> float:
        self.index = max(0, min(self.index + delta_steps, len(self.values) - 1))
        return self.value
