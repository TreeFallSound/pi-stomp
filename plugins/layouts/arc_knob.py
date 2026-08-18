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

from common.param_roles import ParamRole
from common.parameter import Symbol
from uilib.box import Box
from uilib.arc_dial import ArcDialWidget, DialFormatter
from uilib.misc import InputEvent
from uilib.widget import Widget

_RING_RADIUS = 32
_LABEL_FG = (180, 180, 180)


class ArcKnobWidget(ArcDialWidget):
    """Single rotary knob for the fullscreen plugin panels. Click resets to
    the pedalboard default via the owning panel."""

    def __init__(
        self,
        *,
        box: Box,
        symbol: Symbol,
        label: str,
        color: tuple[int, int, int],
        minimum: float,
        maximum: float,
        formatter: DialFormatter,
        panel,
        parent: Widget | None = None,
        radius: int = _RING_RADIUS,
        **kwargs,
    ) -> None:
        super().__init__(
            box=box,
            label=label,
            minimum=minimum,
            maximum=maximum,
            color=color,
            formatter=formatter,
            parent=parent if parent is not None else panel,
            radius=radius,
            label_fg=_LABEL_FG,
            **kwargs,
        )
        self.symbol = symbol
        self._panel = panel

    def symbol_for(self, role: ParamRole) -> Symbol | None:
        return self.symbol

    def input_event(self, event) -> bool:
        if event == InputEvent.LONG_CLICK:
            self._panel._reset_to_default(self.symbol)
            return True
        return False
