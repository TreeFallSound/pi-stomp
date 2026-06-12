"""Generic full-screen panel base for plugin-type-specific UIs.

Subclass checklist
------------------
1. Implement ``snapshot_state() -> TState``.
2. Implement ``apply_state(state)``.
3. Implement ``build_widgets()`` (add widgets to ``self``, base appends chrome).
4. Optionally override ``on_encoder_rotation(encoder_id, rotations) -> bool``.
5. Use ``self.set_param(symbol, value)`` for every live parameter edit.
6. The subclass ``tick()`` should call ``super().tick()`` so the coalesce
   queue drains.

What the base provides for free
-------------------------------
- Chrome row (Back / Bypass / Reset) fixed at the bottom.
- Bypass routed directly to the plugin + websocket push.
- Reset restores all symbols from ``plugin.pedalboard_snapshot``, skipping
  blend-locked ones.
- Param-send coalescing via ``set_param`` + ``tick``.
- InputSink so the LCD can dispatch tweak encoders to the panel.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from typing import Generic, TypeVar

import common.token as Token
from pistomp.input.event import ControllerEvent, EncoderEvent
from pistomp.input.sink import InputSink
from uilib.box import Box
from uilib.config import Config
from uilib.misc import get_text_size
from uilib.panel import Panel
from uilib.text import Button

TState = TypeVar("TState")

# ── chrome layout ───────────────────────────────────────────────────────────
_W = 320
_H = 240
_BTN_GAP = 2
_BTN_H = 28
_BTN_Y = _H - _BTN_H - _BTN_GAP
_BTN_W = (_W - 4 * _BTN_GAP) // 3
_BYPASS_ACTIVE_COLOR = (140, 50, 0)


def _build_btn(text: str, x: int, font, v_margin, parent, action):
    return Button(
        box=Box.xywh(x, _BTN_Y, _BTN_W, _BTN_H),
        text=text,
        font=font,
        v_margin=v_margin,
        outline_radius=4,
        parent=parent,
        action=action,
    )


# ── base class ──────────────────────────────────────────────────────────────

class PluginPanel(Panel, InputSink, Generic[TState]):
    """Full-screen UI for a specific LV2 plugin type.

    Parameters
    ----------
    plugin :
        The ``modalapi.plugin.Plugin`` instance this panel edits.
    handler :
        The handler object (e.g. ``Modhandler``) that opened the panel.
    on_dismiss :
        Callback fired when the Back button is pressed or the panel is
        otherwise dismissed.  Usually calls ``lcd.hide_plugin_panel()``.
    """

    def __init__(
        self,
        *,
        plugin: object,
        handler: object,
        on_dismiss: Callable[[], None],
    ) -> None:
        self.plugin = plugin
        self.handler = handler
        self._on_dismiss = on_dismiss
        self._param_queue: dict[str, float] = {}

        Panel.__init__(self, box=Box.xywh(0, 0, _W, _H))

        # Chrome buttons (created now, appended to nav *after* subclass widgets)
        cfg = Config()
        self._btn_font = cfg.get_font("small") or cfg.get_font("default")
        assert self._btn_font is not None, "PluginPanel requires a 'small' or 'default' font"
        _, btn_text_h = get_text_size("Bypass", self._btn_font)
        self._btn_v_margin = max(0, (_BTN_H - btn_text_h) // 2)

        self._btn_back = _build_btn(
            "Back", _BTN_GAP, self._btn_font, self._btn_v_margin, self,
            lambda *_: self._on_dismiss(),
        )
        self._btn_bypass = _build_btn(
            "Bypass", _BTN_GAP * 2 + _BTN_W, self._btn_font, self._btn_v_margin, self,
            lambda *_: self._on_toggle_bypass(),
        )
        self._btn_reset = _build_btn(
            "Reset", _BTN_GAP * 3 + _BTN_W * 2, self._btn_font, self._btn_v_margin, self,
            lambda *_: self._on_reset(),
        )

        # Let the subclass add its own widgets above the chrome row …
        self.build_widgets()

        # … then append chrome last so Nav always cycles through it.
        self.add_sel_widget(self._btn_back)
        self.add_sel_widget(self._btn_bypass)
        self.add_sel_widget(self._btn_reset)

        self._refresh_bypass_style()

    # ── subclass contract ──────────────────────────────────────────────────

    @abstractmethod
    def snapshot_state(self) -> TState:
        """Read ``plugin.parameters`` into a typed state object."""

    @abstractmethod
    def apply_state(self, state: TState) -> None:
        """Push *state* back into the panel's widgets."""

    @abstractmethod
    def build_widgets(self) -> None:
        """Create and register panel-specific widgets.

        Use ``self.add_sel_widget(...)`` for anything that should participate
        in Nav cycling.  The base class appends the chrome row *after* this
        method returns, so the nav order is:
        subclass-widgets → Back → Bypass → Reset.
        """

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        """Called for Tweak1/2/3 encoder events when this panel is visible.

        Return ``True`` to consume the event; ``False`` lets it fall through to
        normal parameter editing / volume control.
        """
        return False

    # ── param-send coalescing ─────────────────────────────────────────────

    def set_param(self, symbol: str, value: float) -> None:
        """Queue a parameter change.

        Writes ``value`` into ``plugin.parameters[symbol]`` immediately so
        the UI stays consistent.  The actual websocket send is deferred to the
        next ``tick()`` (or an explicit ``_flush_param_queue()``) so rapid
        encoder spins collapse into one send per symbol.
        """
        self._param_queue[symbol] = value
        p = self.plugin.parameters.get(symbol)
        if p is not None:
            p.value = value

    def tick(self) -> None:
        """Drain the coalesced parameter queue.

        Subclasses that override ``tick()`` (e.g. for animated curve diffing)
        **must** call ``super().tick()`` so queued sends are not lost.
        """
        self._flush_param_queue()

    def _flush_param_queue(self) -> None:
        if not self._param_queue:
            return
        instance_id = self.plugin.instance_id
        bridge = self.handler.ws_bridge
        for symbol, value in self._param_queue.items():
            if bridge is not None:
                bridge.send_parameter(instance_id, symbol, value)
        self._param_queue.clear()

    # ── chrome actions ─────────────────────────────────────────────────────

    def _on_toggle_bypass(self) -> None:
        new_bypass = not self.plugin.is_bypassed()
        self.plugin.set_bypass(new_bypass)
        bridge = self.handler.ws_bridge
        if bridge is not None:
            bridge.send_parameter(self.plugin.instance_id, ":bypass", 1.0 if new_bypass else 0.0)
        self._refresh_bypass_style()
        self._btn_bypass.refresh()

    def _on_reset(self) -> None:
        """Restore all symbols from the parse-time snapshot, skipping locked ones and :bypass."""
        self._flush_param_queue()
        snap = self.plugin.pedalboard_snapshot
        for symbol, value in snap.items():
            if symbol == Token.COLON_BYPASS:
                continue
            if self._is_symbol_locked(self.plugin.instance_id, symbol):
                continue
            self.set_param(symbol, value)
        self._flush_param_queue()
        self.apply_state(self.snapshot_state())
        self._refresh_bypass_style()

    def _is_symbol_locked(self, instance_id: str, symbol: str) -> bool:
        return self.handler.is_symbol_locked(instance_id, symbol)

    def _refresh_bypass_style(self) -> None:
        bypassed = self.plugin.is_bypassed()
        self._btn_bypass.set_background(_BYPASS_ACTIVE_COLOR if bypassed else (0, 0, 0))

    # ── InputSink (LCD dispatches here when we are the top panel) ──────────

    def handle(self, event: ControllerEvent) -> bool:
        """Return *True* to stop the event from reaching the normal handler cascade."""
        if isinstance(event, EncoderEvent):
            cid = event.controller.id
            if cid in (1, 2, 3):
                return self.on_encoder_rotation(cid, event.rotations)
        return False
