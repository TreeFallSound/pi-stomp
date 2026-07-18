"""Windowed plugin panel: a centered ``Dialog``-styled card.

Shares the regular menu's title strip and outline, plus the Back/Bypass/Reset
row used by ``FullscreenPluginPanel``. ``self.content_box`` is the body area
between them where ``build_widgets()`` places widgets.

Built on ``plugins.modal_dialog.ModalDialog`` (the shared ``__init__``
choreography + ``footer_buttons()`` hook); this subclass supplies the
plugin-specific three-button footer.
"""

from __future__ import annotations

from modalapi.plugin import Plugin
from plugins.chrome import build_bottom_row
from plugins.modal_dialog import ModalDialog, TState
from uilib.text import Button


class PluginWindow(ModalDialog[TState]):
    """Centered rounded-card plugin UI, visually aligned with the menus.

    The title strip sits above the body as a ``DialogDecorator``, so ``WIN_H``
    is the body height and the on-screen card is ``WIN_H`` plus the strip
    (still centered, still fits 240px). Subclasses may override ``WIN_W`` /
    ``WIN_H``; ``_window_size()`` to size to content.
    """

    plugin: Plugin  # narrowing: PluginWindow is always a Plugin panel

    WIN_W: int = 304
    WIN_H: int = 208

    def footer_buttons(self, btn_y: int, btn_v_margin: int) -> tuple[Button, ...]:
        return build_bottom_row(
            parent=self,
            width=self._win_w,
            bottom_y=btn_y,
            font=self._btn_font,
            v_margin=btn_v_margin,
            on_back=lambda *_: self._on_dismiss(),
            on_bypass=lambda *_: self._on_toggle_bypass(),
            on_reset=lambda *_: self._on_reset(),
        )