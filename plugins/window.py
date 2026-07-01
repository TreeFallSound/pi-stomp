"""Windowed plugin panel: a centered rounded card sharing fullscreen's chrome.

Chrome: plugin name along a title band at the top, and the same Back / Bypass
/ Reset row ``FullscreenPluginPanel`` uses at the bottom (see
``plugins.chrome``). The content area between them (``self.content_box``) is
where ``build_widgets()`` places widgets, in a smaller font than the
fullscreen panels since the card itself is smaller.

Unlike the old ``CustomLayoutMenu`` (a bare pstack push), a ``PluginWindow`` is
registered as the active plugin panel via ``handler.show_fullscreen_panel``, so
it receives Tweak1/2/3 through the same ``InputSink`` path as fullscreen panels
and participates in the fast-poll / board-change bookkeeping.

Size is class-level (``WIN_W`` / ``WIN_H``) so subclasses can pick a compact
card or a near-fullscreen one without touching the constructor signature.
``WIN_W`` is clamped to ``plugins.chrome.MIN_CHROME_WIDTH`` so the three bottom
buttons stay legible.
"""

from __future__ import annotations

from collections.abc import Callable

from modalapi.plugin import Plugin
from pistomp.handler import Handler
from plugins.base import PluginPanel, TState
from plugins.chrome import BTN_GAP, BTN_H, MIN_CHROME_WIDTH, build_bottom_row
from uilib.box import Box
from uilib.config import Config
from uilib.misc import WidgetAlign, get_text_size
from uilib.panel import RoundedPanel

# In-window chrome bands (fixed across sizes).
_TITLE_H = 24


class PluginWindow(PluginPanel[TState], RoundedPanel):
    """Compact, centered rounded-card plugin UI.

    Parameters mirror ``FullscreenPluginPanel``: ``plugin``, ``handler``, and an
    ``on_dismiss`` callback fired by the Back button. Subclasses may override
    ``WIN_W`` / ``WIN_H`` / ``WIN_RADIUS`` to resize the card.
    """

    WIN_W: int = 304
    WIN_H: int = 208
    WIN_RADIUS: int = 8

    @staticmethod
    def _chrome_overhead() -> tuple[int, int]:
        """(top, bottom) pixels the title band and button row consume."""
        return (_TITLE_H, BTN_H + BTN_GAP * 2)

    def _window_size(self) -> tuple[int, int]:
        """Card (width, height). Override to size dynamically to content."""
        return (self.WIN_W, self.WIN_H)

    def __init__(
        self,
        *,
        plugin: Plugin,
        handler: Handler,
        on_dismiss: Callable[[], None],
    ) -> None:
        self._init_plugin_state(plugin, handler, on_dismiss)

        w, h = self._window_size()
        w = max(w, MIN_CHROME_WIDTH)
        self._win_w, self._win_h = w, h
        RoundedPanel.__init__(
            self,
            box=Box.xywh(0, 0, w, h),
            radius=self.WIN_RADIUS,
            align=WidgetAlign.CENTRE,
            auto_destroy=True,
        )

        cfg = Config()
        self._title_font = cfg.get_font("default_title") or cfg.get_font("default")
        self._btn_font = cfg.get_font("small") or cfg.get_font("default")
        assert self._title_font is not None and self._btn_font is not None

        # Back / Bypass / Reset row at the bottom, shared with FullscreenPluginPanel.
        btn_y = h - BTN_H - BTN_GAP
        _, btn_text_h = get_text_size("Bypass", self._btn_font)
        btn_v_margin = max(0, (BTN_H - btn_text_h) // 2)
        self._btn_back, self._btn_bypass, self._btn_reset = build_bottom_row(
            panel=self,
            width=w,
            bottom_y=btn_y,
            font=self._btn_font,
            v_margin=btn_v_margin,
            on_back=lambda *_: self._on_dismiss(),
            on_bypass=lambda *_: self._on_toggle_bypass(),
            on_reset=lambda *_: self._on_reset(),
        )

        # Content area between title band and the button row.
        self.content_box = Box.xywh(0, _TITLE_H, w, btn_y - BTN_GAP - _TITLE_H)

        # Subclass widgets first, then chrome, so Nav cycles content → Back → Bypass → Reset.
        self.build_widgets()
        self.add_sel_widget(self._btn_back)
        self.add_sel_widget(self._btn_bypass)
        self.add_sel_widget(self._btn_reset)

        self._refresh_bypass_style()

    def _draw(self, ctx) -> None:
        # Card body + title band; children paint content on top.
        super()._draw(ctx)
        title_col = Config().get_color("default_title_fgnd")
        ctx.draw_line([(0, _TITLE_H - 1), (self._win_w - 1, _TITLE_H - 1)], fill=title_col, width=1)
        _, th = get_text_size(self.plugin.display_name, self._title_font)
        ctx.draw_text((6, (_TITLE_H - th) // 2), self.plugin.display_name, fill=title_col, font=self._title_font)
