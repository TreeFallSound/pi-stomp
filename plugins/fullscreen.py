"""Full-screen plugin panel: whole 320x240 LCD with a bottom button row."""

from __future__ import annotations

from collections.abc import Callable

from modalapi.plugin import Plugin
from pistomp.fullscreen_panel import FullscreenPanel
from pistomp.handler import Handler
from plugins.base import PluginPanel, TState
from plugins.chrome import BTN_GAP, BTN_H, build_bottom_row
from uilib.config import Config
from uilib.misc import get_text_size

# ── chrome layout ─────────────────────────────────────────────────────────────
_W = 320
_H = 240
_BTN_Y = _H - BTN_H - BTN_GAP


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
        self._btn_v_margin = max(0, (BTN_H - btn_text_h) // 2)

        self._btn_back, self._btn_bypass, self._btn_reset = build_bottom_row(
            panel=self,
            width=_W,
            bottom_y=_BTN_Y,
            font=self._btn_font,
            v_margin=self._btn_v_margin,
            on_back=lambda *_: self._on_dismiss(),
            on_bypass=lambda *_: self._on_toggle_bypass(),
            on_reset=lambda *_: self._on_reset(),
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
