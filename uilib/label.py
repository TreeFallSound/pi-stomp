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

from uilib.box import Box
from uilib.misc import get_text_bbox
from uilib.paint import ColorLike
from uilib.widget import Widget

_PAD = 1  # px around bbox to absorb anti-aliasing fringe


class Label(Widget):
    """Positioned text widget with surgical dirty-rectangle updates.

    set_text() recomputes the bounding box and refreshes only the union of
    old and new bboxes, so a one-character change pushes a few-pixel column
    to the LCD rather than the whole parent.

    The widget's box tracks the text bbox (with _PAD around it). Empty text
    collapses the box to a zero-area point at the anchor — _draw_erase and
    _draw both become no-ops, so an unset Label is invisible without any
    state hacks.
    """

    def __init__(self, x: int, y: int, font, parent: Widget | None = None, **kwargs) -> None:
        super().__init__(box=Box(x, y, x, y), parent=parent, **kwargs)
        self._font = font
        self._anchor_x = x
        self._anchor_y = y
        self._text: str | None = None
        self._color: ColorLike | None = None

    @property
    def text(self) -> str | None:
        return self._text

    def _measure(self, text: str, x: int, y: int) -> Box:
        tb = get_text_bbox(text, self._font)
        return Box(x + tb[0] - _PAD, y + tb[1] - _PAD, x + tb[2] + _PAD, y + tb[3] + _PAD)

    def set_text(self, text: str | None, color: ColorLike, *, x: int | None = None) -> None:
        rx = x if x is not None else self._anchor_x
        if text == self._text and color == self._color and rx == self._anchor_x:
            return

        old_box = self.box
        new_box = (
            self._measure(text, rx, self._anchor_y)
            if text
            else Box(rx, self._anchor_y, rx, self._anchor_y)
        )

        if self._text and text:
            assert old_box is not None
            dirty = old_box.union(new_box)
        elif self._text:
            dirty = old_box
        elif text:
            dirty = new_box
        else:
            # both empty — anchor may have moved, but there's nothing to repaint
            self._anchor_x = rx
            self.box = new_box
            return

        self._text = text
        self._color = color
        self._anchor_x = rx
        self.box = dirty
        self.refresh()
        self.box = new_box

    def _draw_erase(self, ctx) -> None:
        # Skip the rounded-rect path in the default _draw_erase; a zero-area
        # box would still trigger a one-pixel artifact.
        erase = ctx.dirty_bounds
        if erase.width <= 0 or erase.height <= 0:
            return
        ctx.draw_rectangle(erase, fill=self.bkgnd_color)

    def _draw(self, ctx) -> None:
        if not self._text or self.box is None:
            return
        # ctx is frame-relative (0,0 = self.box top-left); the anchor is stored
        # in parent coords, so shift it by the frame origin.
        ctx.draw_text(
            (self._anchor_x - self.box.x0, self._anchor_y - self.box.y0),
            self._text,
            fill=self._color,
            font=self._font,
        )
