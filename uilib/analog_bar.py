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

from typing import Callable

from uilib.box import Box
from uilib.misc import InputEvent
from uilib.container import ContainerWidget


class AnalogBarPanel(ContainerWidget):
    """The row of analog inputs, selectable as one whole widget (never per
    input: the Icon children are never added to any sel_list).

    CLICK and LONG_CLICK both delegate to ``on_press`` — this panel holds no
    opinion on what that opens."""

    def __init__(
        self,
        box: Box,
        on_press: Callable[[], None] | None = None,
        **kwargs,
    ):
        kwargs.setdefault("image_format", "RGBA")
        kwargs.setdefault("bkgnd_color", (0, 0, 0, 0))
        super(AnalogBarPanel, self).__init__(box=box, **kwargs)
        self.on_press = on_press

    def sel_children(self):
        return [self]

    def input_event(self, event: InputEvent) -> bool:
        if event in (InputEvent.CLICK, InputEvent.LONG_CLICK) and self.on_press is not None:
            self.on_press()
            return True
        return False
