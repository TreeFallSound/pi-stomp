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

"""
Blend mode package - Analog input-driven snapshot interpolation.

This package provides functionality for smoothly interpolating between snapshots
based on analog input position (expression pedals or tweak encoders).
"""

from blend.easing import EASING_FUNCTIONS, EasingFunc
from blend.input_controller import InputController
from blend.manager import BlendMode
from blend.parameter_setter import ParameterSetter
from blend.snapshot import SnapshotManager
from blend.stop import BlendStop
from blend.types import BlendSnapshotConfig, NormalizedStops

__all__ = [
    "BlendMode",
    "BlendStop",
    "InputController",
    "SnapshotManager",
    "ParameterSetter",
    "BlendSnapshotConfig",
    "NormalizedStops",
    "EASING_FUNCTIONS",
    "EasingFunc",
]
