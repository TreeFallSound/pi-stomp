from __future__ import annotations

from uilib.misc import get_text_size
from uilib.widget import Widget

_BG = (0, 0, 0)
_READOUT_COLOR = (200, 200, 200)


class ReadoutBar(Widget):
    def __init__(self, box, font, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", _BG)
        super().__init__(box=box, **kwargs)
        self._font = font
        self._text = ""
        self._subtitle = ""

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self.refresh()

    def set_subtitle(self, subtitle: str) -> None:
        if subtitle == self._subtitle:
            return
        self._subtitle = subtitle
        self.refresh()

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.dirty_bounds, fill=_BG)

    def _draw(self, ctx) -> None:
        if self._text:
            ctx.draw_text((6, 1), self._text, fill=_READOUT_COLOR, font=self._font)
        if self._subtitle:
            sw, _ = get_text_size(self._subtitle, self._font)
            ctx.draw_text((ctx.width - sw - 6, 1), self._subtitle, fill=_READOUT_COLOR, font=self._font)
