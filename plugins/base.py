"""Abstract core for plugin-type-specific UIs.

``PluginPanel[TState]`` is the panel-kind-agnostic core: it owns the
plugin/handler references, the param-send coalescing queue, the bypass/reset
actions, and the ``InputSink`` tweak-encoder dispatch. It does **not** commit to
a window geometry or chrome layout.

Two concrete children specialise the presentation (each in its own module),
sharing the same Back / Bypass / Reset button row from ``plugins.chrome``:

- ``plugins.fullscreen.FullscreenPluginPanel`` — whole 320x240 LCD (every
  EQ / Notes panel).
- ``plugins.window.PluginWindow`` — a smaller, centered rounded card (at least
  ``plugins.chrome.MIN_CHROME_WIDTH`` wide) with a smaller content font, for
  compact windowed UIs.

Both children share the constructor signature ``(*, plugin, handler,
on_dismiss)`` so the LCD's ``show_fullscreen_panel`` dispatch is uniform, and
both are ``isinstance(_, PluginPanel)`` so the active-panel bookkeeping (fast
poll, board-change dismiss) treats them alike.

Subclass checklist
------------------
1. Implement ``snapshot_state() -> TState``.
2. Implement ``apply_state(state)``.
3. Implement ``build_widgets()`` (add widgets to ``self``; the concrete base
   appends its chrome afterward).
4. Optionally override ``on_encoder_rotation(encoder_id, rotations) -> bool``.
5. Use ``self.set_param(symbol, value)`` for every live parameter edit.
6. A subclass ``tick()`` override must call ``super().tick()`` so the coalesce
   queue drains.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Generic, TypeVar

import common.token as Token
from modalapi.plugin import Plugin
from pistomp.handler import Handler
from pistomp.input.event import ControllerEvent, EncoderEvent
from pistomp.input.sink import InputSink
from uilib.panel import Panel
from uilib.text import Button

TState = TypeVar("TState")

# Bypass button background when the plugin is bypassed. Shared by both children
# via _refresh_bypass_style.
BYPASS_ACTIVE_COLOR = (140, 50, 0)


class PluginPanel(Panel, InputSink, Generic[TState], ABC):
    """Panel-kind-agnostic core for a plugin-editing UI.

    Inherits ``Panel`` (so subclasses get the widget/selection API) but never
    calls ``Panel.__init__`` itself — the concrete child picks the actual panel
    flavour (``FullscreenPanel`` via ``FullscreenPluginPanel`` or
    ``RoundedPanel`` via ``PluginWindow``) and initialises it. Children must,
    during construction, create a bypass button named ``self._btn_bypass`` (its
    background reflects bypass state).
    """

    plugin: Plugin
    handler: Handler
    _on_dismiss: Callable[[], None]
    _param_queue: dict[str, float]
    _btn_bypass: Button

    def _init_plugin_state(
        self,
        plugin: Plugin,
        handler: Handler,
        on_dismiss: Callable[[], None],
    ) -> None:
        """Wire the shared references. Call first from a child ``__init__``."""
        self.plugin = plugin
        self.handler = handler
        self._on_dismiss = on_dismiss
        self._param_queue = {}

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

        Use ``self.add_sel_widget(...)`` for anything that should participate in
        Nav cycling. The concrete base appends its chrome *after* this returns.
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

        Writes ``value`` into ``plugin.parameters[symbol]`` immediately so the UI
        stays consistent; the websocket send is deferred to the next ``tick()``
        so rapid encoder spins collapse into one send per symbol.
        """
        self._param_queue[symbol] = value
        p = self.plugin.parameters.get(symbol)
        if p is not None:
            p.value = value

    def tick(self) -> None:
        """Drain the coalesced parameter queue.

        Subclasses that override ``tick()`` **must** call ``super().tick()`` so
        queued sends are not lost.
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
        self._btn_bypass.set_background(BYPASS_ACTIVE_COLOR if bypassed else (0, 0, 0))

    # ── InputSink (LCD dispatches here when we are the top panel) ──────────

    def handle(self, event: ControllerEvent) -> bool:
        """Return *True* to stop the event from reaching the normal handler cascade."""
        if isinstance(event, EncoderEvent):
            cid = event.controller.id
            if cid in (1, 2, 3):
                return self.on_encoder_rotation(cid, event.rotations)
        return False
