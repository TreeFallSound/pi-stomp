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

from dataclasses import dataclass
from typing import TypedDict


class PygameBorderRadiusKwargs(TypedDict):
    """The per-corner border-radius kwargs accepted by `pygame.draw.rect`."""

    border_radius: int
    border_top_left_radius: int
    border_top_right_radius: int
    border_bottom_left_radius: int
    border_bottom_right_radius: int


@dataclass(frozen=True)
class Radius:
    """Per-corner border radii for `PaintContext.draw_rectangle`.

    Pass as `radius=Radius.top(10)` (or `.bottom(...)`, `.uniform(...)`) when
    only some corners should round. A bare int is also accepted by
    `draw_rectangle` and treated as `Radius.uniform(int)`.
    """

    top_left: int = 0
    top_right: int = 0
    bottom_left: int = 0
    bottom_right: int = 0

    @classmethod
    def uniform(cls, r: int) -> "Radius":
        return cls(r, r, r, r)

    @classmethod
    def top(cls, r: int) -> "Radius":
        return cls(top_left=r, top_right=r)

    @classmethod
    def bottom(cls, r: int) -> "Radius":
        return cls(bottom_left=r, bottom_right=r)

    @classmethod
    def _coerce(cls, value: "int | Radius | None") -> "Radius":
        if value is None:
            return cls()
        if isinstance(value, Radius):
            return value
        return cls.uniform(int(value))

    def as_pygame_kwargs(self) -> PygameBorderRadiusKwargs:
        # pygame.draw.rect treats negative per-corner radii as "use border_radius".
        # Setting border_radius=0 and explicit per-corner values is unambiguous.
        return PygameBorderRadiusKwargs(
            border_radius=0,
            border_top_left_radius=int(self.top_left),
            border_top_right_radius=int(self.top_right),
            border_bottom_left_radius=int(self.bottom_left),
            border_bottom_right_radius=int(self.bottom_right),
        )
