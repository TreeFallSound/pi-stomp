"""Custom layout menu for low-band-count plugins.

A fullscreen panel that behaves like a regular menu dialog: it dims the
background, shows a title bar, and exposes its own selectable widgets plus a
Back button.  The body is a user-supplied ``Widget`` subclass (registered via
``PluginCustomization.menu_widget_cls``) which lays out up to 8 parameters as
arc rings in a 2x4 grid.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from modalapi.plugin import Plugin
from pistomp.fullscreen_panel import FullscreenPanel
from uilib.box import Box
from uilib.config import Config
from uilib.misc import get_text_size
from uilib.panel import Panel
from uilib.text import Button

if TYPE_CHECKING:
    from uilib.widget import Widget

# ── layout constants ──────────────────────────────────────────────────────────

_W = 320
_H = 240

_TITLE_H = 24
_BOTTOM_GAP = 4
_BTN_H = 28
_CONTENT_Y0 = _TITLE_H
_CONTENT_Y1 = _H - _BTN_H - _BOTTOM_GAP

_BACK_W = 60


class CustomLayoutMenu(FullscreenPanel):
    """Fullscreen menu panel hosting a custom parameter widget and a Back button.

    The supplied ``menu_widget_cls`` receives the ``Plugin`` instance in its
    constructor and is expected to build its own selectable children.  Navigation
    cycles through the widget's selectable list, then the Back button.
    """

    def __init__(
        self,
        *,
        plugin: Plugin,
        menu_widget_cls: type[Widget],
        on_dismiss: Callable[[Panel], None],
    ) -> None:
        super().__init__(box=Box.xywh(0, 0, _W, _H))
        self.plugin = plugin
        self._on_dismiss = on_dismiss

        cfg = Config()
        font = cfg.get_font("small") or cfg.get_font("default")
        assert font is not None
        self._title_font = cfg.get_font("default_title") or font

        # Custom widget body
        self._body = menu_widget_cls(
            box=Box.xywh(0, _CONTENT_Y0, _W, _CONTENT_Y1 - _CONTENT_Y0),
            plugin=plugin,
            parent=self,
        )

        # Back button at the bottom
        _, btn_text_h = get_text_size("Back", font)
        v_margin = max(0, (_BTN_H - btn_text_h) // 2)
        self._btn_back = Button(
            box=Box.xywh(_BOTTOM_GAP, _H - _BTN_H - _BOTTOM_GAP, _BACK_W, _BTN_H),
            text="Back",
            font=font,
            v_margin=v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_dismiss(self),
        )

        # Register selectables: body first, then Back.
        self.add_sel_widget(self._body)
        self.add_sel_widget(self._btn_back)

    def tick(self) -> None:
        body = self._body
        if callable(getattr(body, "tick", None)):
            body.tick()  # type: ignore[attr-defined]

    def _draw(self, ctx) -> None:
        # Paint title bar background; children (body + Back) draw on top.
        title_box = Box.xywh(0, 0, _W, _TITLE_H)
        ctx.draw_rectangle(title_box, fill=Config().get_color("default_title_bkgnd"))
        ctx.draw_line(
            [(0, _TITLE_H - 1), (_W - 1, _TITLE_H - 1)],
            fill=Config().get_color("default_title_fgnd"),
            width=1,
        )
        _, th = get_text_size(self.plugin.display_name, self._title_font)
        ty = (_TITLE_H - th) // 2
        ctx.draw_text(
            (6, ty),
            self.plugin.display_name,
            fill=Config().get_color("default_title_fgnd"),
            font=self._title_font,
        )
        # Don't call super()._draw(); ContainerWidget's do_draw will paint children.
