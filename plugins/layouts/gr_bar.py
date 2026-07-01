from __future__ import annotations

from uilib.box import Box
from uilib.misc import INACTIVE_SHADE, get_text_size, shade_color
from uilib.widget import Widget

_GR_MAX_DB = 24.0
_BG = (0, 0, 0)
_GRID = (46, 64, 54)
_CURVE = (120, 240, 150)
_RETICULE = (255, 200, 90)
_TEXT = (200, 224, 206)
_LABEL = (150, 168, 156)

_LABEL_W = 22
_VALUE_W = 46
_PAD = 4


class GrBarWidget(Widget):
    def __init__(self, *, box: Box, font, parent: Widget) -> None:
        super().__init__(box=box, bkgnd_color=_BG, parent=parent, visible=True)
        self._font = font
        self._bypassed = False
        self._gr_db: float | None = None

    def set_gr(self, gr_db: float | None) -> None:
        rounded = None if gr_db is None else round(max(0.0, min(_GR_MAX_DB, gr_db)), 1)
        if rounded == self._gr_db:
            return
        self._gr_db = rounded
        self.refresh()

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def _bar_span(self) -> tuple[int, int]:
        bx = self.box
        assert bx is not None
        w = bx.x1 - bx.x0
        return _LABEL_W + _PAD, w - _VALUE_W - _PAD

    def _fill_color(self, gr_db: float, shade: float) -> tuple[int, int, int]:
        if gr_db < 6.0:
            base = _CURVE
        elif gr_db < 12.0:
            base = _RETICULE
        else:
            base = (230, 90, 70)
        return shade_color(base, shade)

    def _draw(self, ctx) -> None:
        shade = INACTIVE_SHADE if self._bypassed else 1.0
        h = ctx.height
        bar_y0, bar_y1 = 2, h - 2
        bar_x0, bar_x1 = self._bar_span()

        _lw, lh = get_text_size("GR", self._font)
        ctx.draw_text((0, (h - lh) // 2), "GR", fill=shade_color(_LABEL, shade), font=self._font)

        ctx.draw_rectangle(Box(bar_x0, bar_y0, bar_x1, bar_y1), fill=shade_color(_GRID, shade))
        gr_db = self._gr_db
        if gr_db is not None and gr_db > 0.0:
            fill_w = int(round((bar_x1 - bar_x0) * (gr_db / _GR_MAX_DB)))
            if fill_w > 0:
                color = self._fill_color(gr_db, shade)
                ctx.draw_rectangle(Box(bar_x0, bar_y0, bar_x0 + fill_w, bar_y1), fill=color)

        val_text = "--" if gr_db is None else f"{gr_db:.1f}"
        vw, vh = get_text_size(val_text, self._font)
        w = ctx.width
        ctx.draw_text((w - vw, (h - vh) // 2), val_text, fill=shade_color(_TEXT, shade), font=self._font)
