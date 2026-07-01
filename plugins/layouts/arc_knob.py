from __future__ import annotations

from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.arc_ring import ArcRingGlyph
from uilib.misc import INACTIVE_SHADE, InputEvent, get_text_size, shade_color
from uilib.widget import Widget

_BG = (0, 0, 0)
_RING_EMPTY = (50, 50, 50)
_RING_TIP = (255, 255, 255)
_LABEL_FG = (180, 180, 180)
_VALUE_FG = (255, 255, 255)

_RING_RADIUS = 32


class ArcKnobWidget(Widget):
    def __init__(
        self,
        box: Box,
        symbol: str,
        label: str,
        color: tuple[int, int, int],
        minimum: float,
        maximum: float,
        formatter,
        panel,
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", _BG)
        super().__init__(box=box, **kwargs)
        self.symbol = symbol
        self._label = label
        self._color = color
        self._minimum = minimum
        self._maximum = maximum
        self._formatter = formatter
        self._panel = panel
        self._value: float = minimum
        self._bypassed: bool = False
        self._ring = ArcRingGlyph(_RING_RADIUS)

        cfg = Config()
        self._label_font = cfg.get_font("tiny")
        self._value_font = cfg.get_font("small")

    def set_value(self, value: float) -> None:
        value = max(self._minimum, min(self._maximum, value))
        if value == self._value:
            return
        self._value = value
        self.refresh()

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.dirty_bounds, fill=_BG)

    def _draw(self, ctx) -> None:
        cx = ctx.width // 2
        cy = (ctx.height // 2) - 8

        shade = INACTIVE_SHADE if self._bypassed else 1.0
        ring_color = shade_color(self._color, shade)
        tip_color = shade_color(_RING_TIP, shade)
        span = self._maximum - self._minimum
        t = (self._value - self._minimum) / span if span > 0 else 0.0
        t = max(0.0, min(1.0, t))
        ring = self._ring.render(t, ring_color, _RING_EMPTY, tip_color)
        hs = self._ring.half_size
        ctx.paste(ring, (cx - hs, cy - hs))

        val_text = self._formatter(self._value)
        vw, vh = get_text_size(val_text, self._value_font)
        ctx.draw_text((cx - vw // 2, cy - vh // 2), val_text, fill=_VALUE_FG, font=self._value_font)

        lw, lh = get_text_size(self._label, self._label_font)
        ctx.draw_text((cx - lw // 2, cy + hs + 2), self._label, fill=_LABEL_FG, font=self._label_font)

    def input_event(self, event) -> bool:
        if event == InputEvent.CLICK:
            self._panel._reset_to_default(self.symbol)
            return True
        return False
