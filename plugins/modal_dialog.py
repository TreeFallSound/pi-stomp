"""ModalDialog — a presentation base for menu-idiom panels with an optional
footer button row.

Hoists the ``__init__`` choreography that ``PluginWindow`` and the Audio &
MIDI menu share: title strip (via ``Dialog``), an optional footer placed by
``footer_buttons()``, a ``content_box`` computed between them, and the nav
order (subclass widgets → footer). ``build_widgets()`` is the subclass hook
that fills ``content_box``.

The Audio & MIDI panel (``docs/audio-midi-menu.md`` §4.2/§7) composes this
with the reactive ``PluginPanel`` core and a ``(Back,)`` footer; a bypass-free
panel simply returns no Bypass/Reset buttons. ``PluginWindow`` is reduced to
the plugin-specific footer (Back/Bypass/Reset) on top of this base.

Scope note (§4.2 wrinkle): only the ``DIMMED_WINDOW`` mode is exercised
today — ``FullscreenPluginPanel`` keeps its own opaque ``Panel`` base since
the opaque-vs-shroud split is structural (§3.1). If a future fullscreen
menu-idiom surface wants the opaque fast path, add ``OPAQUE_FULLSCREEN``
here and verify the title-decorator slow-path regression (risk #2) then.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import Enum, auto
from typing import TYPE_CHECKING

from common.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.handler import Handler
from plugins.base import PluginPanel, TState
from plugins.chrome import BTN_GAP, BTN_H, build_bottom_row
from plugins.scheme import scheme_for_category
from uilib.box import Box
from uilib.config import Config
from uilib.dialog import Dialog
from uilib.misc import get_text_size
from uilib.text import Button

if TYPE_CHECKING:
    pass


class ModalMode(Enum):
    """Presentation mode for a ``ModalDialog``.

    Only ``DIMMED_WINDOW`` is exercised today (see module docstring); the
    enum is closed so the mode flag is a single switch, per §4.2.
    """

    DIMMED_WINDOW = auto()


class ModalDialog(PluginPanel[TState], Dialog):
    """Menu-idiom presentation base: dimmed rounded card + optional footer.

    Subclass contract
    -----------------
    1. Implement ``snapshot_state`` / ``apply_state`` / ``build_widgets`` (the
       ``PluginPanel`` behaviour contract). ``build_widgets`` places widgets
       inside ``self.content_box`` and calls ``add_sel_widget`` for each
       NAV-cycle target.
    2. Override ``footer_buttons()`` to return the footer row (default: none).
       Plugin panels return ``build_bottom_row(Back, Bypass, Reset)``; the
       Audio & MIDI menu returns ``(Back,)``.
    3. Override ``title_text()`` if the title isn't the plugin's display name.
    """

    WIN_W: int = 304
    WIN_H: int = 208
    _CONTENT_PAD = 2

    mode: ModalMode = ModalMode.DIMMED_WINDOW
    _btn_bypass: Button | None
    _btn_reset: Button | None
    _btn_back: Button | None

    @classmethod
    def _chrome_overhead(cls) -> tuple[int, int]:
        return (cls._CONTENT_PAD, BTN_H + BTN_GAP * 2 + cls._CONTENT_PAD)

    def _window_size(self) -> tuple[int, int]:
        return (self.WIN_W, self.WIN_H)

    def title_text(self) -> str:
        return self.plugin.display_name if isinstance(self.plugin, Plugin) else "Menu"

    def scheme(self):
        return scheme_for_category(self.plugin.category) if isinstance(self.plugin, Plugin) else None

    def footer_buttons(self, btn_y: int, btn_v_margin: int) -> tuple[Button, ...]:  # noqa: D418
        """Subclass hook. Default: no footer (a pure menu).

        Called after ``Dialog.__init__`` so the panel surface exists for
        button parenting. ``btn_y`` / ``btn_v_margin`` are pre-computed for
        the panel's button font and passed so a subclass can forward them to
        ``build_bottom_row`` without re-measuring.
        """
        return ()

    def __init__(
        self,
        *,
        plugin: Plugin,
        handler: Handler,
        on_dismiss: Callable[[], None],
        badge_fn: Callable[[Parameter], str | None] | None = None,
    ) -> None:
        self._init_plugin_state(plugin, handler, on_dismiss)
        self._badge_fn = badge_fn

        w, h = self._window_size()
        from plugins.chrome import MIN_CHROME_WIDTH
        w = max(w, MIN_CHROME_WIDTH)
        self._win_w, self._win_h = w, h

        cfg = Config()
        self._title_font = cfg.get_font("default_title")
        self._btn_font = cfg.get_font("small")

        Dialog.__init__(
            self,
            width=w,
            height=h,
            title=self.title_text(),
            title_font=self._title_font,
            auto_destroy=True,
            scheme=self.scheme(),
        )

        btn_y = h - BTN_H - BTN_GAP
        _, btn_text_h = get_text_size("Bypass", self._btn_font)
        btn_v_margin = max(0, (BTN_H - btn_text_h) // 2)
        footer = self.footer_buttons(btn_y=btn_y, btn_v_margin=btn_v_margin)
        self._layout_footer(footer)

        pad = self._CONTENT_PAD
        self.content_box = Box.xywh(0, pad, w, btn_y - BTN_GAP - 2 * pad) if footer else Box.xywh(0, pad, w, h - 2 * pad)

        self.build_widgets()
        for btn in footer:
            if btn.visible:
                self.add_sel_widget(btn)

        self._badge_bypass()
        self._refresh_bypass_style()
        self._start_observing()

    def _layout_footer(self, footer: Sequence[Button]) -> None:
        """Wire conventional ``_btn_*`` attributes from the footer tuple.

        A single-button footer (Audio & MIDI's Back) is re-positioned here to
        span the row; ``build_bottom_row``'s three-button row is already
        positioned by the subclass."""
        if not footer:
            self._btn_back = None
            self._btn_bypass = None
            self._btn_reset = None
            return
        if len(footer) == 1:
            btn = footer[0]
            btn.box = Box.xywh(BTN_GAP, self._win_h - BTN_H - BTN_GAP, self._win_w - 2 * BTN_GAP, BTN_H)
            self._btn_back = btn
            self._btn_bypass = None
            self._btn_reset = None
            return
        self._btn_back = next((b for b in footer if b.text == "Back"), None)
        self._btn_bypass = next((b for b in footer if b.text == "Bypass"), None)
        self._btn_reset = next((b for b in footer if b.text == "Reset"), None)