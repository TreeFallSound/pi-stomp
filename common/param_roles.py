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

"""Parameter role classification: a per-symbol tag supplementing the LV2
port's ground truth (name/range/type) with how a tweak encoder should edit
it. Plugin customizations declare a port's role (`PluginCustomization.
param_roles`); GENERIC falls back to the existing range/type-derived step
(`uilib.misc.step_for_param`)."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal


class ParamRole(Enum):
    GENERIC = auto()        # caller falls back to its own range/type-derived step
    GAIN_DB = auto()         # fixed dB step, additive
    FREQUENCY_HZ = auto()    # musical (equal-tempered) step, multiplicative
    Q_FACTOR = auto()        # fixed step, additive


@dataclass(frozen=True)
class RoleStep:
    kind: Literal["additive", "multiplicative"]
    amount: float   # additive: value delta per detent; multiplicative: ratio per detent


_ROLE_STEPS: dict[ParamRole, RoleStep] = {
    ParamRole.GAIN_DB: RoleStep("additive", 0.5),
    ParamRole.FREQUENCY_HZ: RoleStep("multiplicative", 2.0 ** (1.0 / 12.0)),
    ParamRole.Q_FACTOR: RoleStep("additive", 0.05),
}


def edit_value(role: ParamRole, current: float, rotations: int, minimum: float, maximum: float) -> float:
    """Apply `rotations` detents of `role`'s step to `current`, clamped to
    [minimum, maximum]. Not meaningful for GENERIC — callers handle that role
    themselves (range/type-derived step, e.g. uilib.misc.step_for_param)."""
    step = _ROLE_STEPS[role]
    if step.kind == "additive":
        new_val = current + rotations * step.amount
    else:
        new_val = current * (step.amount**rotations)
    return max(minimum, min(maximum, new_val))
