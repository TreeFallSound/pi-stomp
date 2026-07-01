"""Mode selector widget for the TAP Reverberator's 43-value enumeration.

Renders ``‹  LABEL  ›`` centered with a thin progress strip showing the
position within the 0..42 range. CLICK opens the parameter dialog (full
list of modes); Tweak1 (when focused) cycles by one detent per index.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from uilib.box import Box
from uilib.config import Config
from uilib.misc import InputEvent, get_text_size
from uilib.widget import Widget

if TYPE_CHECKING:
    from plugins.tap_reverb.panel import TapReverbPanel

# ── layout constants ───────────────────────────────────────────────────────

_BAR_H = 3
_BAR_Y_OFFSET = 6  # gap between label baseline and progress bar
_TOP_PADDING = 4  # inset from the selection reticule's top edge

# ── colours ─────────────────────────────────────────────────────────────────

_BG = (0, 0, 0)
_LABEL_FG = (255, 255, 255)
_BAR_EMPTY = (45, 45, 45)
_BAR_FILL = (255, 230, 80)


class ModeSelectorWidget(Widget):
    """Full-width selector for the ``mode`` enumeration port.

    The widget is a Nav-selectable leaf: Tweak1 edits the value when this
    widget is ``sel_ref``, and CLICK opens the parameter dialog (the full
    list of 43 modes as a scrollable selection menu).
    """

    symbol: str = "mode"

    def __init__(self, box: Box, panel: "TapReverbPanel", **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", _BG)
        super().__init__(box=box, **kwargs)
        self._panel = panel
        cfg = Config()
        self._font = cfg.get_font("footswitch")
        self._value: int = 0
        self._labels: list[str] = []
        self._max: int = 42

    @property
    def value(self) -> int:
        return self._value

    @property
    def max_index(self) -> int:
        return self._max

    # ── public setters ──────────────────────────────────────────────────────

    def set_value(self, value: int) -> None:
        value = max(0, min(self._max, int(value)))
        if value == self._value and self._labels:
            return
        self._value = value
        self.refresh()

    def set_labels(self, labels: list[str]) -> None:
        self._labels = labels
        self._max = max(len(labels) - 1, 1)
        self.refresh()

    # ── Widget overrides ────────────────────────────────────────────────────

    def input_event(self, event) -> bool:  # type: ignore[override]
        if event == InputEvent.CLICK:
            self._panel._open_mode_dialog()
            return True
        return False

    def _draw_erase(self, ctx) -> None:  # type: ignore[override]
        ctx.draw_rectangle(ctx.dirty_bounds, fill=_BG)

    def _draw(self, ctx) -> None:
        if not self._labels:
            return
        label = self._labels[self._value] if self._value < len(self._labels) else "?"
        text = f"\u2039  {label}  \u203a"

        tw, th = get_text_size(text, self._font)
        cx = ctx.width // 2
        ty = _TOP_PADDING

        ctx.draw_text((cx - tw // 2, ty), text, fill=_LABEL_FG, font=self._font)

        # Progress strip below the label — inset 4px from widget edges
        bar_y = ty + th + _BAR_Y_OFFSET
        bar_x0 = 4
        bar_x1 = ctx.width - 4
        bar_w = bar_x1 - bar_x0

        ctx.draw_rectangle(Box(bar_x0, bar_y, bar_x1, bar_y + _BAR_H), fill=_BAR_EMPTY)

        if self._max > 0:
            fill_w = int(bar_w * (self._value / self._max))
            if fill_w > 0:
                ctx.draw_rectangle(Box(bar_x0, bar_y, bar_x0 + fill_w, bar_y + _BAR_H), fill=_BAR_FILL)
