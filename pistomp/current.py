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

from dataclasses import dataclass, field

from pistomp.controller import AnalogControllers
from modalapi.pedalboard import Pedalboard


@dataclass
class Current:
    """Mutable per-pedalboard state for the active ("current") pedalboard."""

    pedalboard: Pedalboard
    presets: dict[int, str] = field(default_factory=dict)
    preset_index: int = 0  # Assumes pedalboard loads at snapshot 0 (default behavior)
    analog_controllers: AnalogControllers = field(default_factory=dict)
