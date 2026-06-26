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

from abc import abstractmethod

from uilib.box import Box
from uilib.panel import Panel

from pistomp.input.event import ControllerEvent
from pistomp.input.sink import InputSink


class FullscreenPanel(Panel, InputSink):
    """Base class for panels that occupy the full 320x240 LCD.
    Subclasses must implement tick(); handle() defaults to False
    (pass-through) and may be overridden.
    """

    def __init__(
        self,
        box: Box = Box.xywh(0, 0, 320, 240),
        auto_destroy: bool = True,
        no_dim: bool = True,
        **kwargs,
    ):
        super().__init__(box=box, auto_destroy=auto_destroy, no_dim=no_dim, **kwargs)

    @abstractmethod
    def tick(self) -> None: ...

    def handle(self, event: ControllerEvent) -> bool:
        return False

    def should_persist_on_board_change(self) -> bool:
        return False
