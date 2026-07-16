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

_LABEL_GAP = 1   # px between label ink and the ring bounding box
_LINE_GAP = 3    # px between the value line and the unit line
_RING_NUDGE_Y = 3  # push the ring down from the centred position


def _ink_metrics(text: str, font) -> tuple[int, int, int, int]:
    """(x0, y0, ink_w, ink_h) of ``text`` — ink box relative to the draw origin
    (top-left of the ascender line), matching PIL's getbbox via get_text_bbox."""
    x0, y0, x1, y1 = get_text_bbox(text, font)
    return x0, y0, x1 - x0, y1 - y0


def _draw_baseline_centered_x(ctx: PaintContext, cx: int, baseline_y: int, text: str, font, fill: Color) -> None:
    """Centre ``text`` horizontally on ``cx`` and sit its **baseline** on
    ``baseline_y``. Unlike ink-centring, a glyph with no ascender ("x") lands on
    its baseline just like the bottom of "dB" — the two stacked lines keep a
    consistent gap regardless of which letters the unit happens to have."""
    if not text:
        return
    x0, _, ink_w, _ = _ink_metrics(text, font)
    ox = cx - (x0 + ink_w / 2)
    oy = baseline_y - font.get_sized_ascender()
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
    line_gap: int = _LINE_GAP,
    ring_dy: int = 0,
) -> None:
    """Render one dial centred on (cx, cy) into ``ctx``.

    The ring is pasted from ``glyph`` (which decides gap orientation via its own
    ``flip_v``). ``label`` is uppercased and placed outside the ring per
    ``label_pos``. The inner block is one line (``value``) unless ``two_line``
    and ``unit`` is non-empty, in which case ``unit`` is stacked beneath with
    ``line_gap`` px between baselines' cap boxes.

    ``ring_dy`` offsets the ring graphic and the inner value/unit together; the
    label stays on ``cy`` so a small optical nudge doesn't drag it along.
    """
    half = glyph.half_size
    ring = glyph.render(t, filled_color, empty_color, tip_color)
    ctx.paste(ring, (cx - half, cy - half + ring_dy))

    # Inner value / unit block. The value line is cap-centred on the ring's
    # optical centre — the same anchor whether or not a unit follows, so one- and
    # two-line dials read consistently — and the unit stacks beneath it. Lines
    # are placed by baseline over a canonical cap height, so unitless words with
    # different ascenders/descenders ("Light", "Med", "Heavy") share a baseline,
    # and a unit with no ascender ("x") sits like the bottom of "dB".
    inner_cy = cy + ring_dy
    # Centre by cap-height boxes (the digit "0"), not each string's own ink, so a
    # row of dials shares one baseline regardless of ascenders/descenders, and the
    # geometry scales with the font: a single value cap-box centres on the ring;
    # a value+unit pair centres as one block.
    cap_h = _ink_metrics("0", value_font)[3]
    if two_line and unit:
        value_base = int(round(inner_cy - line_gap / 2))
        _draw_baseline_centered_x(ctx, cx, value_base, value, value_font, value_fg)
        _draw_baseline_centered_x(ctx, cx, value_base + line_gap + cap_h, unit, unit_font, unit_fg)
    else:
        text = value if not unit else f"{value} {unit}"
        _draw_baseline_centered_x(ctx, cx, int(round(inner_cy + cap_h / 2)), text, value_font, value_fg)

    # Label outside the ring.
    text = label.upper()
    lx0, ly0, lw, lh = _ink_metrics(text, label_font)
    if label_pos == "top":
        oy = (cy - half - _LABEL_GAP) - (ly0 + lh)  # ink bottom sits above the ring
    else:
        oy = (cy + half + _LABEL_GAP) - ly0          # ink top sits below the ring
    ox = cx - (lx0 + lw / 2)
    ctx.draw_text((int(round(ox)), int(round(oy))), text, fill=label_fg, font=label_font)


def dial_box_size(radius: int, label_font, sel_width: int = 2) -> tuple[int, int]:
    """Smallest box a top-labelled dial fits in: the content block (label + gap
    + ring, plus the ring's optical nudge) with `sel_width` of padding at every
    edge for the selection reticule. Callers laying out a grid of dials should
    size cells from this rather than from the ring alone."""
    ring = ArcRingGlyph(radius)
    _, _, _, lh = _ink_metrics("Ag", label_font)
    w = ring.size + 2 * sel_width
    h = lh + _LABEL_GAP + ring.size + _RING_NUDGE_Y + 2 * sel_width
    return w, h


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
        # The smaller (MEDIUM/"small") face wants a tighter inter-line gap.
        self._line_gap = _LINE_GAP + (1 if variant == DialVariant.MEDIUM else 2)

    # ── input-context badge (R4) ────────────────────────────────────────────

    def _draw_badge(self, ctx: PaintContext) -> None:
        """Opposite the label, and never touching the label/value text
        (`Widget.set_badge` stores it; this only overrides placement).

        With the label on top the badge sits *in* the ring's bottom cutout —
        the arc's own gap — so a badged dial costs no extra height."""
        if self._badge is None:
            return
        cx = ctx.width // 2
        cy = self._cy() + _RING_NUDGE_Y
        half = self._ring.half_size
        bx = cx - self._badge.width // 2
        if self._label_pos == "top":
            by = cy + half - self._badge.height
        else:
            by = cy - half - _LABEL_GAP - self._badge.height
        ctx.paste(self._badge.render(), (bx, by))

    # ── ring vertical centre within the widget box ──────────────────────────

    def _cy(self) -> int:
        """Ring centre y, derived by centring the whole *content block* — label
        plus gap plus ring — inside the box's padding, not by centring the ring
        and letting the label hang out of flow above it.

        Centring the ring alone pools all the slack below it (the label only
        eats into the top half), so a tight box clips the label against the
        selection reticule while the bottom sits empty. `sel_width` is reserved
        as padding at both edges: the reticule is an inset border, and content
        never enters it."""
        assert self.box is not None
        half = self._ring.half_size
        _, _, _, lh = _ink_metrics(self._label.upper(), self._label_font)
        pad = self.sel_width
        block_h = lh + _LABEL_GAP + 2 * half
        top = pad + max(0, (self.box.height - 2 * pad - block_h) // 2)
        if self._label_pos == "top":
            return int(top + lh + _LABEL_GAP + half)
        return int(top + half)

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
            line_gap=self._line_gap,
            ring_dy=_RING_NUDGE_Y,
        )
