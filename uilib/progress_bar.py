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
from uilib.misc import get_text_size
from uilib.paint import PaintContext
from uilib.widget import Widget

ColorStops = list[tuple[float, tuple[int, int, int]]]

# Green→red: reads as "time running out", for a capture with a fixed duration.
HEAT_STOPS: ColorStops = [
    (0.00, (0, 200, 75)),
    (0.35, (120, 215, 0)),
    (0.65, (230, 148, 0)),
    (1.00, (215, 55, 10)),
]

# Dark→light steel blue, between the grid's wire blue and the Hz arc blue. For
# work that merely takes as long as it takes — no urgency to signal.
STEEL_STOPS: ColorStops = [
    (0.00, (26, 58, 80)),
    (0.50, (70, 150, 200)),
    (1.00, (110, 200, 230)),
]

_BAR_DIM = 0.13  # brightness of unfilled segments

# Elapsed / remaining label pairs, keyed to the bar they sit under.
HEAT_LABELS = ((130, 118, 80), (205, 180, 110))
STEEL_LABELS = ((92, 116, 136), (150, 190, 215))


def fmt_time(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


class ProgressBarWidget(Widget):
    """Segmented colour-gradient progress bar with elapsed/remaining time labels."""

    _MARGIN = 12  # left/right inset
    _BAR_Y = 30  # top of bar within widget
    _BAR_H = 30  # bar height
    _LABEL_GAP = 10  # gap between bar bottom and label top
    # 42 segments of 5px with 2px gaps divide evenly (42*5 + 41*2 == 292), leaving
    # 4px to split as an extra inset. Changing either without re-solving that
    # identity brings back segments of uneven width.
    _N_SEGS = 42
    _SEG_GAP = 2

    def __init__(
        self,
        box: Box,
        total_seconds: float,
        font,
        caption_font,
        parent: Widget,
        stops: ColorStops | None = None,
        label_colors: tuple[tuple[int, int, int], tuple[int, int, int]] = HEAT_LABELS,
    ) -> None:
        super().__init__(box=box, bkgnd_color=(0, 0, 0), parent=parent)
        self._stops = HEAT_STOPS if stops is None else stops
        self._label_colors = label_colors
        self._total = total_seconds
        self._progress = 0.0
        self._frozen = False
        self._elapsed = 0.0
        self._remaining = total_seconds
        self._font = font
        self._caption_font = caption_font
        self._segments = self._layout(int(box.width) - 2 * self._MARGIN)

    @classmethod
    def _layout(cls, inner_w: int) -> list[tuple[int, int]]:
        # Uniform widths, with any leftover split between the two ends rather than
        # stranded on the right. At 320 wide the leftover is zero by construction.
        n = cls._N_SEGS
        gap = cls._SEG_GAP
        seg_w = max(1, (inner_w - (n - 1) * gap) // n)
        x0 = (inner_w - (n * seg_w + (n - 1) * gap)) // 2
        return [(x0 + i * (seg_w + gap), seg_w) for i in range(n)]

    def set_total(self, total_seconds: float) -> None:
        # Archiving has no known duration; callers revise this from throughput.
        self._total = max(0.0, total_seconds)

    def set_progress(self, progress: float) -> None:
        if self._frozen:
            return
        p = max(0.0, min(1.0, progress))
        old_filled = int(self._progress * self._N_SEGS)
        self._progress = p
        self._elapsed = p * self._total
        self._remaining = self._total - self._elapsed
        if int(p * self._N_SEGS) != old_filled:
            self.refresh()

    def freeze(self) -> None:
        self._frozen = True

    def set_done(self) -> None:
        self._progress = 1.0
        self._elapsed = self._total
        self._remaining = 0.0
        self._frozen = True

    def reset(self) -> None:
        self._progress = 0.0
        self._elapsed = 0.0
        self._remaining = self._total
        self._frozen = False

    def advance_rotation(self, dt: float) -> None:
        pass

    def _color_at(self, t: float) -> tuple[int, int, int]:
        stops = self._stops
        if t <= stops[0][0]:
            return stops[0][1]
        if t >= stops[-1][0]:
            return stops[-1][1]
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0)
                return (
                    int(c0[0] + f * (c1[0] - c0[0])),
                    int(c0[1] + f * (c1[1] - c0[1])),
                    int(c0[2] + f * (c1[2] - c0[2])),
                )
        return stops[-1][1]

    def _draw(self, ctx: PaintContext) -> None:
        n = self._N_SEGS
        filled = int(self._progress * n)
        bx = self._MARGIN
        by = self._BAR_Y
        ctx.fill((0, 0, 0))

        for i, (sx, sw) in enumerate(self._segments):
            t = i / (n - 1) if n > 1 else 0.0
            r, g, b = self._color_at(t)
            if i < filled:
                color: tuple[int, int, int] = (r, g, b)
            else:
                color = (int(r * _BAR_DIM), int(g * _BAR_DIM), int(b * _BAR_DIM))
            ctx.draw_rectangle(Box.xywh(bx + sx, by, sw, self._BAR_H), fill=color)

        # No duration yet (archiving, before throughput is measurable) — 0:00/−0:00
        # would read as a stalled job, so draw no labels at all.
        if self._total <= 0:
            return

        label_y = by + self._BAR_H + self._LABEL_GAP
        right_x = ctx.width - self._MARGIN

        elapsed_col, remaining_col = self._label_colors
        elapsed_str = fmt_time(self._elapsed)
        ctx.draw_text((bx, label_y), elapsed_str, fill=elapsed_col, font=self._font)

        remaining_str = f"−{fmt_time(self._remaining)}"
        rw, _ = get_text_size(remaining_str, self._font)
        ctx.draw_text((right_x - rw, label_y), remaining_str, fill=remaining_col, font=self._font)
