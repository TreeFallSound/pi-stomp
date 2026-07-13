# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-Stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Arc-ring rotary "dial": the one primitive + widget every rotary uses.

A dial is a split arc-ring (:class:`ArcRingGlyph`) with:
  - an UPPERCASE BOLD **label** outside the ring (in the top gap when the glyph
    is flipped, or below it for dense layouts),
  - a **value** line inside the ring, optionally with the **unit** stacked on a
    second line beneath it,
  - the whole inner block **ink-centered** on the ring centre so digits and
    descenders don't shift it vertically.

``paint_arc_dial`` is the low-level routine (used by dense multi-cell layouts
that own their own geometry); :class:`ArcDialWidget` is the single-arc Widget
that wraps it for the common one-ring-per-widget case.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Callable, Literal

from uilib.box import Box
from uilib.config import Color, Config, FontName
from uilib.glyphs.arc_ring import ArcRingGlyph, ColorRGB
from uilib.misc import INACTIVE_SHADE, get_text_bbox, shade_color
from uilib.paint import PaintContext
from uilib.widget import Widget

LabelPos = Literal["top", "bottom"]

# Value/unit formatter: parameter value -> (value_text, unit_text). unit "" ⇒
# a single centred value line (no reserved second line).
DialFormatter = Callable[[float], tuple[str, str]]


class DialVariant(Enum):
    """Text size preset. The value/unit share one font; the label is the bold
    counterpart one notch smaller."""

    MEDIUM = "medium"
    LARGE = "large"


# variant -> (label font, value/unit font)
_VARIANT_FONTS: dict[DialVariant, tuple[FontName, FontName]] = {
    DialVariant.MEDIUM: ("arc_label", "small"),
    DialVariant.LARGE: ("arc_label_lg", "default"),
}

_LABEL_GAP = 2   # px between label ink and the ring bounding box
_LINE_GAP = 3    # px between the value line and the unit line
_RING_NUDGE_Y = 3  # push the ring down from the centred position


def _ink_metrics(text: str, font) -> tuple[int, int, int, int]:
    """(x0, y0, ink_w, ink_h) of ``text`` — ink box relative to the draw origin
    (top-left of the ascender line), matching PIL's getbbox via get_text_bbox."""
    x0, y0, x1, y1 = get_text_bbox(text, font)
    return x0, y0, x1 - x0, y1 - y0


def _draw_ink_centered(ctx: PaintContext, cx: int, cy: int, text: str, font, fill: Color) -> None:
    """Draw ``text`` so its **ink** midpoint lands on (cx, cy)."""
    if not text:
        return
    x0, y0, ink_w, ink_h = _ink_metrics(text, font)
    ox = cx - (x0 + ink_w / 2)
    oy = cy - (y0 + ink_h / 2)
    ctx.draw_text((int(round(ox)), int(round(oy))), text, fill=fill, font=font)


def _draw_ink_centered_x(ctx: PaintContext, cx: int, ink_cy: int, text: str, font, fill: Color) -> None:
    """Centre ``text`` horizontally on ``cx`` with its ink vertical centre at
    ``ink_cy`` (used to stack the value/unit lines)."""
    if not text:
        return
    x0, y0, ink_w, ink_h = _ink_metrics(text, font)
    ox = cx - (x0 + ink_w / 2)
    oy = ink_cy - (y0 + ink_h / 2)
    ctx.draw_text((int(round(ox)), int(round(oy))), text, fill=fill, font=font)


def paint_arc_dial(
    ctx: PaintContext,
    *,
    cx: int,
    cy: int,
    glyph: ArcRingGlyph,
    t: float,
    filled_color: ColorRGB,
    empty_color: ColorRGB,
    tip_color: ColorRGB,
    label: str,
    value: str,
    unit: str,
    label_font,
    value_font,
    unit_font,
    label_fg: Color,
    value_fg: Color,
    unit_fg: Color,
    label_pos: LabelPos = "top",
    two_line: bool = True,
    ring_dy: int = 0,
) -> None:
    """Render one dial centred on (cx, cy) into ``ctx``.

    The ring is pasted from ``glyph`` (which decides gap orientation via its own
    ``flip_v``). ``label`` is uppercased and placed outside the ring per
    ``label_pos``. The inner block is one line (``value``) unless ``two_line``
    and ``unit`` is non-empty, in which case ``unit`` is stacked beneath.

    ``ring_dy`` offsets the ring graphic and the inner value/unit together; the
    label stays on ``cy`` so a small optical nudge doesn't drag it along.
    """
    half = glyph.half_size
    ring = glyph.render(t, filled_color, empty_color, tip_color)
    ctx.paste(ring, (cx - half, cy - half + ring_dy))

    # Inner value / unit block, ink-centred on the (nudged) ring centre.
    inner_cy = cy + ring_dy
    if two_line and unit:
        _, _, _, vh = _ink_metrics(value, value_font)
        _, _, _, uh = _ink_metrics(unit, unit_font)
        block_h = vh + _LINE_GAP + uh
        top = inner_cy - block_h / 2
        _draw_ink_centered_x(ctx, cx, int(round(top + vh / 2)), value, value_font, value_fg)
        _draw_ink_centered_x(ctx, cx, int(round(top + vh + _LINE_GAP + uh / 2)), unit, unit_font, unit_fg)
    else:
        text = value if not unit else f"{value} {unit}"
        _draw_ink_centered(ctx, cx, inner_cy, text, value_font, value_fg)

    # Label outside the ring.
    text = label.upper()
    lx0, ly0, lw, lh = _ink_metrics(text, label_font)
    if label_pos == "top":
        oy = (cy - half - _LABEL_GAP) - (ly0 + lh)  # ink bottom sits above the ring
    else:
        oy = (cy + half + _LABEL_GAP) - ly0          # ink top sits below the ring
    ox = cx - (lx0 + lw / 2)
    ctx.draw_text((int(round(ox)), int(round(oy))), text, fill=label_fg, font=label_font)


class ArcDialWidget(Widget):
    """One arc-ring dial as a Widget: flipped ring, bold label in the top gap,
    ink-centred value with an optional unit line.

    Subclass to add input behaviour (click-to-reset, encoder edits); this base
    owns only rendering + value state and a tip-based incremental dirty rect.
    """

    def __init__(
        self,
        *,
        box: Box,
        label: str,
        minimum: float,
        maximum: float,
        color: ColorRGB,
        formatter: DialFormatter,
        parent: Widget,
        radius: int,
        ring_half: float = 4.5,
        tip_radius: float = 3.5,
        empty_color: ColorRGB = (56, 56, 56),
        tip_color: ColorRGB = (255, 255, 255),
        value_fg: ColorRGB = (255, 255, 255),
        unit_fg: ColorRGB = (170, 170, 180),
        label_fg: ColorRGB = (150, 150, 160),
        two_line: bool = True,
        label_pos: LabelPos = "top",
        variant: DialVariant = DialVariant.MEDIUM,
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", (0, 0, 0))
        super().__init__(box=box, parent=parent, **kwargs)
        self._label = label
        self._minimum = minimum
        self._maximum = maximum
        self._color = color
        self._formatter = formatter
        self._empty_color = empty_color
        self._tip_color = tip_color
        self._value_fg = value_fg
        self._unit_fg = unit_fg
        self._label_fg = label_fg
        self._two_line = two_line
        self._label_pos: LabelPos = label_pos
        self._value: float = minimum
        self._bypassed: bool = False
        self._ring = ArcRingGlyph(radius, ring_half=ring_half, tip_radius=tip_radius, flip_v=False)

        cfg = Config()
        label_name, value_name = _VARIANT_FONTS[variant]
        self._label_font = cfg.get_font(label_name)
        self._value_font = cfg.get_font(value_name)
        self._unit_font = self._value_font  # unit shares the value font

    # ── input-context badge (R4) ────────────────────────────────────────────

    def _draw_badge(self, ctx: PaintContext) -> None:
        """Centred on the opposite side of the ring from the label — the one
        other symmetric spot on this widget, and never touches the label/value
        text (`Widget.set_badge` stores it; this only overrides placement)."""
        if self._badge is None:
            return
        cx = ctx.width // 2
        cy = self._cy()
        half = self._ring.half_size
        bx = cx - self._badge.width // 2
        if self._label_pos == "top":
            by = cy + half + _LABEL_GAP
        else:
            by = cy - half - _LABEL_GAP - self._badge.height
        ctx.paste(self._badge.render(), (bx, by))

    # ── ring vertical centre within the widget box ──────────────────────────

    def _cy(self) -> int:
        """Ring centre y: vertically centred in the box, but nudged inward just
        enough that the outside label never clips past the box edge."""
        assert self.box is not None
        half = self._ring.half_size
        center = self.box.height // 2
        _, _, _, lh = _ink_metrics(self._label.upper(), self._label_font)
        if self._label_pos == "top":
            return max(center, half + _LABEL_GAP + lh)
        return min(center, self.box.height - (half + _LABEL_GAP + lh))

    # ── value state ─────────────────────────────────────────────────────────

    def set_value(self, value: float) -> None:
        value = max(self._minimum, min(self._maximum, value))
        if value == self._value:
            return
        old_t = self._t()
        self._value = value
        self.refresh(self._dirty_rect(old_t, self._t()))

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    @property
    def value(self) -> float:
        return self._value

    def reading_text(self, value: float | None = None) -> str:
        """One-line "value unit" for readout bars (unit omitted when empty)."""
        v, u = self._formatter(self._value if value is None else value)
        return f"{v} {u}".strip()

    def _t(self) -> float:
        span = self._maximum - self._minimum
        if span <= 0:
            return 0.0
        return max(0.0, min(1.0, (self._value - self._minimum) / span))

    def _tip_rect_abs(self, t: float) -> Box:
        assert self.box is not None
        cx = self.box.x0 + self.box.width // 2
        cy = self.box.y0 + self._cy()
        half = self._ring.half_size
        tx, ty = self._ring.tip_center(t)
        x = cx - half + tx
        y = cy - half + ty + _RING_NUDGE_Y
        pad = int(math.ceil(self._ring.tip_radius)) + 1
        return Box.xywh(int(x) - pad, int(y) - pad, 2 * pad + 1, 2 * pad + 1)

    def _dirty_rect(self, old_t: float, new_t: float) -> Box:
        """Tight dirty rect: for small moves only the two tip positions + the
        inner text strip; large jumps repaint the whole widget."""
        assert self.box is not None
        if abs(new_t - old_t) >= 0.10:
            return self.box
        cx = self.box.x0 + self.box.width // 2
        cy = self.box.y0 + self._cy()
        half = self._ring.half_size
        inner = Box.xywh(cx - half, cy - half // 2, 2 * half, half)
        res = self._tip_rect_abs(old_t).union(self._tip_rect_abs(new_t)).union(inner)
        assert res is not None
        return res

    # ── drawing ─────────────────────────────────────────────────────────────

    def _draw(self, ctx: PaintContext) -> None:
        shade = INACTIVE_SHADE if self._bypassed else 1.0
        cx = ctx.width // 2
        cy = self._cy()
        value, unit = self._formatter(self._value)
        paint_arc_dial(
            ctx,
            cx=cx,
            cy=cy,
            glyph=self._ring,
            t=self._t(),
            filled_color=shade_color(self._color, shade),
            empty_color=shade_color(self._empty_color, shade),
            tip_color=shade_color(self._tip_color, shade),
            label=self._label,
            value=value,
            unit=unit,
            label_font=self._label_font,
            value_font=self._value_font,
            unit_font=self._unit_font,
            label_fg=shade_color(self._label_fg, shade),
            value_fg=shade_color(self._value_fg, shade),
            unit_fg=shade_color(self._unit_fg, shade),
            label_pos=self._label_pos,
            two_line=self._two_line,
            ring_dy=_RING_NUDGE_Y,
        )
