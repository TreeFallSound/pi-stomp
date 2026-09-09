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

"""Shared models and step math for encoder-driven parameter edits."""

import bisect
from collections.abc import Callable
from dataclasses import dataclass
from typing import List

import common.util as util
from common.parameter import Parameter, Symbol, Type


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
# MAX_MULTIPLIER. At or above this, the per-parameter cap binds; below it, the
# multiplier is interpolated linearly between 1 step/detent and the cap.
REFERENCE_FAST_MULTIPLIER = 4.0


EditCommit = Callable[[Parameter, float], None]


@dataclass(frozen=True)
class EditContext:
    parameter: Parameter
    commit: EditCommit
    grid_range: tuple[float, float] | None = None

    @property
    def cache_key(self) -> tuple[str | None, Symbol]:
        return self.parameter.instance_id, self.parameter.symbol

    @property
    def extents(self) -> tuple[float, float]:
        if self.grid_range is not None:
            return self.grid_range
        return self.parameter.declared_extents


def resolution(parameter: Parameter | None, minimum: float | None = None, maximum: float | None = None) -> int:
    """Detents needed to cross the selected parameter range."""
    if parameter is None:
        return CONTINUOUS_STEPS
    lo = parameter.minimum if minimum is None else minimum
    hi = parameter.maximum if maximum is None else maximum
    match parameter.type:
        case Type.INTEGER:
            return int(hi - lo) + 1
        case Type.ENUMERATION:
            return len(parameter.get_enum_value_list())
        case Type.TOGGLED:
            return 2
        case _:
            return CONTINUOUS_STEPS


def effective_multiplier(
    multiplier: float,
    parameter: Parameter | None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """
    Maps the encoder's raw speed multiplier onto the parameter's step range
    so a full-speed spin covers the same fraction of any grid in roughly the
    same number of detents.
    """
    res = resolution(parameter, minimum, maximum)
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

    def __init__(self, minimum: float, maximum: float, logarithmic: bool, num_steps: int):
        self.num_steps = num_steps
        self.index = 0
        self.values: List[float] = []
        if num_steps <= 1:
            self.values = [minimum]
            return
        # Geometric for log ports — the same curve mod-host decodes a CC with,
        # so a 128-step grid lands on exactly the CC-expressible values.
        self.values = [
            util.from_normalized(i / (num_steps - 1), minimum, maximum, logarithmic) for i in range(num_steps)
        ]

    @classmethod
    def for_parameter(cls, parameter: Parameter, extents: tuple[float, float] | None = None) -> "ParameterSteps":
        minimum, maximum = extents or (parameter.minimum, parameter.maximum)
        steps = cls(minimum, maximum, parameter.is_logarithmic, resolution(parameter, minimum, maximum))
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
