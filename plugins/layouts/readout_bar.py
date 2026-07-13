from __future__ import annotations

from uilib.glyphs.badge import BadgeGlyph
from uilib.misc import get_text_size
from uilib.widget import Widget

_BG = (0, 0, 0)
_READOUT_COLOR = (200, 200, 200)
_BADGE_GAP = 3


class ReadoutBar(Widget):
    """`set_badge` here shadows the base `Widget`'s fixed-corner marker
    (`uilib/widget.py`) with its own: the badge tracks whatever text is
    currently shown, so it's drawn beside that text rather than in a fixed
    corner. Stored under a different name (`_readout_badge`) so the base
    class's own `_badge`/`_draw_corner_badge` stay untouched (and inert,
    since nothing ever sets `self._badge`)."""

    def __init__(self, box, font, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", _BG)
        super().__init__(box=box, **kwargs)
        self._font = font
        self._text = ""
        self._subtitle = ""
        self._readout_badge: BadgeGlyph | None = None

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

    def set_badge(self, badge: BadgeGlyph | None) -> None:
        """Encoder-binding badge for the currently displayed text, e.g. which
        tweak encoder edits the selected control (§9 step 6: this is where
        the selection-dependent badge lives, not on the widget it edits)."""
        if badge == self._readout_badge:
            return
        self._readout_badge = badge
        self.refresh()

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.dirty_bounds, fill=_BG)

    def _draw(self, ctx) -> None:
        if self._text:
            text_x = 6
            if self._readout_badge is not None:
                by = (ctx.height - self._readout_badge.height) // 2
                ctx.paste(self._readout_badge.render(), (text_x, by))
                text_x += self._readout_badge.width + _BADGE_GAP
            ctx.draw_text((text_x, 1), self._text, fill=_READOUT_COLOR, font=self._font)
        if self._subtitle:
            sw, _ = get_text_size(self._subtitle, self._font)
            sub_x = ctx.width - sw - 6
            ctx.draw_text((sub_x, 1), self._subtitle, fill=_READOUT_COLOR, font=self._font)
