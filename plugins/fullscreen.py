"""Full-screen plugin panel: whole 320x240 LCD with a bottom button row."""

from __future__ import annotations

from collections.abc import Callable

from modalapi.plugin import Plugin
from pistomp.fullscreen_panel import FullscreenPanel
from pistomp.handler import Handler
from plugins.base import PluginPanel, TState
from uilib.box import Box
from uilib.config import Config
from uilib.misc import get_text_size
from uilib.text import Button

# ── chrome layout ─────────────────────────────────────────────────────────────
_W = 320
_H = 240
_BTN_GAP = 2
_BTN_H = 28
_BTN_Y = _H - _BTN_H - _BTN_GAP
_BTN_W = (_W - 4 * _BTN_GAP) // 3


def _build_btn(text: str, x: int, font, v_margin, parent, action) -> Button:
    return Button(
        box=Box.xywh(x, _BTN_Y, _BTN_W, _BTN_H),
        text=text,
        font=font,
        v_margin=v_margin,
        outline_radius=4,
        parent=parent,
        action=action,
    )


class FullscreenPluginPanel(PluginPanel[TState], FullscreenPanel):
    """Full-screen plugin UI with a Back / Bypass / Reset button row.

    Parameters
    ----------
    plugin :
        The ``modalapi.plugin.Plugin`` instance this panel edits.
    handler :
        The handler object (e.g. ``Modhandler``) that opened the panel.
    on_dismiss :
        Callback fired when the Back button is pressed. Usually
        ``handler.hide_fullscreen_panel``.
    """

    def __init__(
        self,
        *,
        plugin: Plugin,
        handler: Handler,
        on_dismiss: Callable[[], None],
    ) -> None:
        self._init_plugin_state(plugin, handler, on_dismiss)

        FullscreenPanel.__init__(self)

        cfg = Config()
        self._btn_font = cfg.get_font("default")
        assert self._btn_font is not None, "FullscreenPluginPanel requires a 'default' font"
        _, btn_text_h = get_text_size("Bypass", self._btn_font)
        self._btn_v_margin = max(0, (_BTN_H - btn_text_h) // 2)

        self._btn_back = _build_btn(
            "Back", _BTN_GAP, self._btn_font, self._btn_v_margin, self, lambda *_: self._on_dismiss()
        )
        self._btn_bypass = _build_btn(
            "Bypass", _BTN_GAP * 2 + _BTN_W, self._btn_font, self._btn_v_margin, self, lambda *_: self._on_toggle_bypass()
        )
        self._btn_reset = _build_btn(
            "Reset", _BTN_GAP * 3 + _BTN_W * 2, self._btn_font, self._btn_v_margin, self, lambda *_: self._on_reset()
        )

        # Subclass widgets first …
        self.build_widgets()

        # … then chrome last so Nav cycles subclass-widgets → Back → Bypass → Reset.
        # build_widgets() may hide individual buttons (e.g. notes hides
        # bypass/reset); skip invisible ones so add_sel_widget's assert holds.
        for btn in (self._btn_back, self._btn_bypass, self._btn_reset):
            if btn.visible:
                self.add_sel_widget(btn)

        self._refresh_bypass_style()
