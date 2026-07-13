from __future__ import annotations

from uilib.misc import get_text_size
from uilib.widget import Widget

_BG = (0, 0, 0)
_READOUT_COLOR = (200, 200, 200)
_BADGE_GAP = 3


class ReadoutBar(Widget):
    """Overrides `Widget._draw_badge` (not the storage) so the badge tracks
    whatever text is currently shown, drawn beside it rather than in the
    base's fixed left-edge corner. Uses the inherited `_badge`/`set_badge()`
    directly — no shadow field needed now that `_draw_badge` is the one
    call site every widget's override feeds into."""

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
            text_x = 6
            if self._badge is not None:
                text_x += self._badge.width + _BADGE_GAP
            ctx.draw_text((text_x, 1), self._text, fill=_READOUT_COLOR, font=self._font)
        if self._subtitle:
            sw, _ = get_text_size(self._subtitle, self._font)
            sub_x = ctx.width - sw - 6
            ctx.draw_text((sub_x, 1), self._subtitle, fill=_READOUT_COLOR, font=self._font)

    def _draw_badge(self, ctx) -> None:
        """Encoder-binding badge for the currently displayed text, e.g. which
        tweak encoder edits the selected control (§9 step 6: this is where
        the selection-dependent badge lives, not on the widget it edits)."""
        if self._badge is None:
            return
        by = (ctx.height - self._badge.height) // 2
        ctx.paste(self._badge.render(), (6, by))
