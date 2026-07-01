"""Windowed plugin panel: a centered ``Dialog``-styled card.

Shares the regular menu's title strip and outline, plus the Back/Bypass/Reset
row used by ``FullscreenPluginPanel``. ``self.content_box`` is the body area
between them where ``build_widgets()`` places widgets.
"""

from __future__ import annotations

from collections.abc import Callable

from modalapi.plugin import Plugin
from pistomp.handler import Handler
from plugins.base import PluginPanel, TState
from plugins.chrome import BTN_GAP, BTN_H, MIN_CHROME_WIDTH, build_bottom_row
from uilib.box import Box
from uilib.config import Config
from uilib.dialog import Dialog
from uilib.misc import get_text_size


class PluginWindow(PluginPanel[TState], Dialog):
    """Centered rounded-card plugin UI, visually aligned with the menus.

    The title strip sits above the body as a ``DialogDecorator``, so ``WIN_H``
    is the body height and the on-screen card is ``WIN_H`` plus the strip
    (still centered, still fits 240px). Subclasses may override ``WIN_W`` /
    ``WIN_H``; ``_window_size()`` to size to content.
    """

    WIN_W: int = 304
    WIN_H: int = 208

    _CONTENT_PAD = 2  # top/bottom breathing room around content_box

    @classmethod
    def _chrome_overhead(cls) -> tuple[int, int]:
        """(top, bottom) pixels the chrome consumes inside the panel body."""
        return (cls._CONTENT_PAD, BTN_H + BTN_GAP * 2 + cls._CONTENT_PAD)

    def _window_size(self) -> tuple[int, int]:
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

        cfg = Config()
        self._title_font = cfg.get_font("default_title") or cfg.get_font("default")
        self._btn_font = cfg.get_font("small") or cfg.get_font("default")
        assert self._title_font is not None and self._btn_font is not None

        Dialog.__init__(
            self, width=w, height=h, title=plugin.display_name, title_font=self._title_font, auto_destroy=True
        )

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

        pad = self._CONTENT_PAD
        self.content_box = Box.xywh(0, pad, w, btn_y - BTN_GAP - 2 * pad)

        self.build_widgets()
        self.add_sel_widget(self._btn_back)
        self.add_sel_widget(self._btn_bypass)
        self.add_sel_widget(self._btn_reset)

        self._refresh_bypass_style()
