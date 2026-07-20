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

"""Generic, data-driven footswitch-LED rendering.

Pure function of (LedSpec, plugin.output_values) -> (color, style). No
footswitch, beat, or plugin-instance coupling — the per-tick brightness
envelope (pulse phase, downbeat emphasis) is applied uniformly by the
handler's single LED-writing helper, not here.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modalapi.plugin_customization import LedSpec


class LedDisplayStyle(Enum):
    SOLID = auto()
    METRONOME = auto()


def render_led_spec(
    spec: LedSpec, output_values: dict[str, float]
) -> tuple[tuple[int, int, int] | None, LedDisplayStyle]:
    state = int(output_values.get(spec.state_symbol, 0))
    if state in spec.off_states:
        return None, LedDisplayStyle.SOLID
    base = spec.colors.get(state)
    if base is None:
        return None, LedDisplayStyle.SOLID
    if spec.downbeat_symbol is not None and int(output_values.get(spec.downbeat_symbol, -1)) == 0:
        base = (
            min(255, base[0] + spec.downbeat_tint),
            min(255, base[1] + spec.downbeat_tint),
            min(255, base[2] + spec.downbeat_tint),
        )
    style = LedDisplayStyle.METRONOME if (spec.pulse and state not in spec.steady_states) else LedDisplayStyle.SOLID
    return base, style
