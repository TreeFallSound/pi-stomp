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

"""RichTextWidget: a single widget that lays out a sequence of `Segment`s
horizontally — text runs, icon glyphs (emoji-style), and flexible spacers.

Glyphs are treated as custom unicode: each one ships its own pixels (color
baked in), has an intrinsic size, and is positioned vertically by the layout.
"""

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

import pygame

from uilib.config import Config
from uilib.misc import get_text_size
from uilib.paint import ColorLike, PaintContext
from uilib.widget import Widget


@runtime_checkable
class Glyph(Protocol):
    """An emoji-like custom glyph: self-contained pixels at a fixed size."""

    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    def render(self) -> pygame.Surface: ...


@runtime_checkable
class Segment(Protocol):
    """One unit in a RichTextWidget. Reports its (w, h) and draws itself at
    a top-left position the parent computes."""

    def measure(self, font) -> tuple[int, int]: ...
    def draw(self, ctx: PaintContext, x: int, y: int, font, color: ColorLike) -> None: ...


@dataclass(frozen=True)
class TextSeg:
    """A run of plain text. Inherits the widget's `fgnd_color`."""

    text: str

    def measure(self, font) -> tuple[int, int]:
        # Width is text-specific, but height always reserves room for a worst-
        # case descender ('g') so rows stay the same height regardless of
        # whether the current label happens to contain descenders.
        w, _ = get_text_size(self.text, font)
        _, h = get_text_size("Mg", font)
        return (w, h)

    def draw(self, ctx: PaintContext, x: int, y: int, font, color: ColorLike) -> None:
        # +1 matches the optical baseline of inline glyphs: glyphs sit at the
        # row top, but a font's ascender-line is 1px above the visual cap top,
        # so text drawn at the same y reads as too high next to a glyph.
        ctx.draw_text((x, y + 1), self.text, fill=color, font=font)


@dataclass(frozen=True)
class IconSeg:
    """A custom glyph. Color is whatever the glyph baked in; the `color`
    arg from RichTextWidget is ignored on purpose (emoji convention)."""

    glyph: Glyph

    def measure(self, font) -> tuple[int, int]:
        return (self.glyph.width, self.glyph.height)

    def draw(self, ctx: PaintContext, x: int, y: int, font, color: ColorLike) -> None:
        ctx.paste(self.glyph.render(), (x, y))


@dataclass(frozen=True)
class Spacer:
    """Flexible gap. `min_w` is the guaranteed width; any leftover row width
    is split evenly across spacers. Use one between left/right groups for
    left/right alignment."""

    min_w: int = 0

    def measure(self, font) -> tuple[int, int]:
        return (self.min_w, 0)

    def draw(self, ctx: PaintContext, x: int, y: int, font, color: ColorLike) -> None:
        pass


class RichTextWidget(Widget):
    """A single-row widget that lays out `Segment`s left-to-right.

    Vertical alignment: each segment is centered within the row's line height.
    Text segments are full line height so they sit flush top (and baseline
    where `ctx.draw_text` puts them); icons shorter than the line are centered.

    Width auto-sizing (when `box.width == 0`): sum of segment widths plus
    horizontal margins. Spacers contribute only their `min_w` in this mode.
    Height auto-sizing (when `box.height == 0`): max segment height plus
    vertical margins, floored at the font's line height.
    """

    def __init__(
        self,
        box,
        segments: Sequence[Segment],
        font=None,
        h_margin: int | None = None,
        v_margin: int | None = None,
        **kwargs,
    ) -> None:
        self.segments: list[Segment] = list(segments)
        if font is None:
            font = Config().get_font("default")
        self.font = font
        self.h_margin = h_margin
        self.v_margin = v_margin
        super().__init__(box, **kwargs)

    def _get_margins(self) -> tuple[int, int]:
        # Match TextWidget's margin defaulting: max(sel_width, outline) so
        # selection/outline rectangles don't clip the content.
        if self.selectable and self.sel_width > self.outline:
            def_margin = self.sel_width
        else:
            def_margin = self.outline
        h = def_margin if self.h_margin is None else self.h_margin
        v = def_margin if self.v_margin is None else self.v_margin
        return (h, v)

    def _adjust_box(self) -> None:
        if self.box.width != 0 and self.box.height != 0:
            return
        h_margin, v_margin = self._get_margins()
        _, line_h = get_text_size("", self.font)
        total_w = 0
        max_h = line_h
        for seg in self.segments:
            sw, sh = seg.measure(self.font)
            total_w += sw
            if sh > max_h:
                max_h = sh
        if self.box.width == 0:
            self.box.width = total_w + h_margin * 2 + self.outline
        if self.box.height == 0:
            self.box.height = max_h + v_margin * 2 + self.outline
        super()._adjust_box()

    def _draw(self, ctx: PaintContext) -> None:
        h_margin, v_margin = self._get_margins()
        extra = self.outline
        hroom = ctx.width - h_margin * 2 - extra
        vroom = ctx.height - v_margin - extra
        if hroom <= 0 or vroom <= 0:
            return

        _, line_h = get_text_size("", self.font)
        row_h = max(line_h, max((s.measure(self.font)[1] for s in self.segments), default=0))
        row_top = v_margin

        # Measure all segments first so we know how much slack to distribute.
        sizes = [s.measure(self.font) for s in self.segments]
        spacer_idx = [i for i, s in enumerate(self.segments) if isinstance(s, Spacer)]
        fixed_w = sum(w for i, (w, _) in enumerate(sizes) if i not in spacer_idx)
        spacer_min_w = sum(sizes[i][0] for i in spacer_idx)
        slack = max(0, hroom - fixed_w - spacer_min_w)
        per_spacer = slack // len(spacer_idx) if spacer_idx else 0

        x = h_margin
        for i, seg in enumerate(self.segments):
            sw, sh = sizes[i]
            if i in spacer_idx:
                x += sw + per_spacer
                continue
            # Center each segment vertically inside the row band.
            y = row_top + (row_h - sh) // 2
            seg.draw(ctx, x, y, self.font, self.fgnd_color)
            x += sw
