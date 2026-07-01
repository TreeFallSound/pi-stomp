"""Windowed plugin panel: a centered rounded card with retro chrome.

Chrome: plugin name + a retro square ``[X]`` close along a title band at the
top, and a slim ``Bypass | Reset`` line at the bottom. The content area between
them (``self.content_box``) is where ``build_widgets()`` places widgets.

Unlike the old ``CustomLayoutMenu`` (a bare pstack push), a ``PluginWindow`` is
registered as the active plugin panel via ``handler.show_fullscreen_panel``, so
it receives Tweak1/2/3 through the same ``InputSink`` path as fullscreen panels
and participates in the fast-poll / board-change bookkeeping.

Size is class-level (``WIN_W`` / ``WIN_H``) so subclasses can pick a compact
card or a near-fullscreen one without touching the constructor signature.
"""

from __future__ import annotations

from collections.abc import Callable

from modalapi.plugin import Plugin
from pistomp.handler import Handler
from plugins.base import PluginPanel, TState
from uilib.box import Box
from uilib.config import Config
from uilib.misc import WidgetAlign, get_text_size
from uilib.panel import RoundedPanel
from uilib.text import Button

# In-window chrome bands (fixed across sizes).
_TITLE_H = 24
_CLOSE_SZ = 18  # retro square [X], top-right
_CLOSE_PAD = 3
_STRIP_H = 26  # slim Bypass | Reset line at the bottom
_STRIP_GAP = 2


class PluginWindow(PluginPanel[TState], RoundedPanel):
    """Compact, centered rounded-card plugin UI.

    Parameters mirror ``FullscreenPluginPanel``: ``plugin``, ``handler``, and an
    ``on_dismiss`` callback fired by the ``[X]`` close. Subclasses may override
    ``WIN_W`` / ``WIN_H`` / ``WIN_RADIUS`` to resize the card.
    """

    WIN_W: int = 304
    WIN_H: int = 208
    WIN_RADIUS: int = 8

    @staticmethod
    def _chrome_overhead() -> tuple[int, int]:
        """(top, bottom) pixels the title band and Bypass|Reset strip consume."""
        return (_TITLE_H, _STRIP_H + _STRIP_GAP * 2)

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

        # Retro square close button, top-right.
        _, close_text_h = get_text_size("✕", self._btn_font)
        self._btn_close = Button(
            box=Box.xywh(w - _CLOSE_SZ - _CLOSE_PAD, _CLOSE_PAD, _CLOSE_SZ, _CLOSE_SZ),
            text="✕",
            font=self._btn_font,
            v_margin=max(0, (_CLOSE_SZ - close_text_h) // 2),
            outline_radius=0,
            parent=self,
            action=lambda *_: self._on_dismiss(),
        )

        # Slim Bypass | Reset line at the bottom.
        strip_y = h - _STRIP_H - _STRIP_GAP
        strip_w = (w - 3 * _STRIP_GAP) // 2
        _, strip_text_h = get_text_size("Bypass", self._btn_font)
        strip_v_margin = max(0, (_STRIP_H - strip_text_h) // 2)
        self._btn_bypass = Button(
            box=Box.xywh(_STRIP_GAP, strip_y, strip_w, _STRIP_H),
            text="Bypass",
            font=self._btn_font,
            v_margin=strip_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_toggle_bypass(),
        )
        self._btn_reset = Button(
            box=Box.xywh(_STRIP_GAP * 2 + strip_w, strip_y, strip_w, _STRIP_H),
            text="Reset",
            font=self._btn_font,
            v_margin=strip_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_reset(),
        )

        # Content area between title band and bottom strip.
        self.content_box = Box.xywh(0, _TITLE_H, w, strip_y - _TITLE_H)

        # Subclass widgets first, then chrome, so Nav cycles content → X → Bypass → Reset.
        self.build_widgets()
        self.add_sel_widget(self._btn_close)
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
