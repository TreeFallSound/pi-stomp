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
4. Optionally override ``on_event(event) -> bool`` to drive this panel's own
   non-NAV controls (return True to consume). NAV events never reach
   ``on_event`` — the base panel owns NAV and shapes it only through the
   selection model.
5. Use ``self.set_param(symbol, value)`` for every live parameter edit.
6. A subclass ``tick()`` override must call ``super().tick()`` so the coalesce
   queue drains.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Generic, TypeVar

from common.contexts import ControlClass, ControlRef, EventKind
from common.param_roles import ParamRole
from common.param_source import BypassSource, ParamSource
from common.parameter import BYPASS_SYMBOL, Parameter, Symbol
from common.parameter_steps import ParameterSteps, effective_multiplier
from modalapi.plugin import Plugin
import common.token as Token
from pistomp.input.dispatch import MultiSelectable, Selectable, fire, resolve_local
from pistomp.input.event import ControllerEvent, EncoderEvent, SwitchEvent, SwitchEventKind
from pistomp.handler import Handler
from uilib.glyphs.badge import BadgeGlyph
from uilib.panel import Panel
from uilib.text import Button

if TYPE_CHECKING:
    pass

TState = TypeVar("TState")

# Bypass button background when the plugin is bypassed. Shared by both children
# via _refresh_bypass_style.
BYPASS_ACTIVE_COLOR = (140, 50, 0)


class PluginPanel(Panel, Generic[TState], ABC):
    """Panel-kind-agnostic core for a parameter-editing UI.

    The behaviour core: param-send coalescing queue, the reactive
    subscribe→dirty→``apply_state`` reconcile, tweak dispatch via
    ``declare_bindings()``, ``edit_symbol``'s ``ParameterSteps`` math, and
    the NAV-only editor open path. It depends on a ``ParamSource``
    (``common.param_source``) — a reactive bag of parameters — not on
    ``Plugin`` specifically. ``Plugin`` satisfies ``ParamSource``
    structurally; the Audio & MIDI menu supplies a synthetic bundle of the
    audiocard + global-EQ params (see ``docs/audio-midi-menu.md`` §4.1).

    Bypass/reset are gated on the source also implementing
    ``BypassSource``; a bypass-free source (audiocard, global EQ) simply
    composes this core with a footer that omits Bypass/Reset.

    Inherits ``Panel`` (so subclasses get the widget/selection API) but never
    calls ``Panel.__init__`` itself — the concrete child picks the actual panel
    flavour (a plain ``Panel`` via ``FullscreenPluginPanel`` or ``RoundedPanel``
    via ``PluginWindow``) and initialises it. Plugin-panel subclasses that need
    ``Plugin``-specific members (``customization``, ``instance_number``,
    ``visible_parameters``) narrow ``self.plugin`` with a class-level
    ``plugin: Plugin`` annotation.
    """

    # `plugin` is the reactive param source (see common.param_source). It is
    # not declared at class level so plugin-specific subclasses may narrow it
    # to `Plugin` via a class-level `plugin: Plugin` annotation without an
    # incompatible-override warning; the base types it as `ParamSource` only
    # on the `_init_plugin_state` parameter and the instance attribute.
    handler: Handler
    _on_dismiss: Callable[[], None]
    _param_queue: dict[Symbol, float]
    _btn_bypass: Button | None
    _badge_fn: Callable[[Parameter], str | None] | None
    _model_dirty: bool
    _unsub_model: Callable[[], None] | None

    def _init_plugin_state(
        self,
        plugin: ParamSource,
        handler: Handler,
        on_dismiss: Callable[[], None],
    ) -> None:
        """Wire the shared references. Call first from a child ``__init__``."""
        self.plugin = plugin
        self.handler = handler
        self._on_dismiss = on_dismiss
        self._param_queue = {}
        self._badge_fn = None
        self._model_dirty = False
        self._unsub_model = None

    def _badge_for(self, symbol: Symbol) -> str | None:
        if self._badge_fn is None:
            return None
        param = self.plugin.parameters.get(symbol)
        return self._badge_fn(param) if param is not None else None

    def _badge_bypass(self) -> None:
        if self._btn_bypass is None:
            return
        badge_char = self._badge_for(BYPASS_SYMBOL)
        if badge_char is not None:
            self._btn_bypass.set_badge(BadgeGlyph(badge_char))

    def _start_observing(self) -> None:
        """Subscribe to plugin param changes. Call at the end of a child
        ``__init__``, after ``build_widgets`` and ``_refresh_bypass_style`` —
        the observer only marks dirty; ``tick`` drains."""
        self._unsub_model = self.plugin.subscribe(self._on_param_changed)

    def _on_param_changed(self, _param: Parameter) -> None:
        self._model_dirty = True

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

    def on_event(self, event: ControllerEvent) -> bool:
        """Resolve declare_bindings() against the event and fire the winner.
        Panels with a state-machine on_event (e.g. NAM) should override this."""
        # A tweak/volume long-press would otherwise fall through to the handler's
        # global encoder-longpress callback (e.g. previous/next_snapshot), which
        # reloads every parameter under the open panel. While a plugin editor is
        # open the encoders belong to the panel, so swallow it.
        if (isinstance(event, SwitchEvent)
                and event.kind is SwitchEventKind.LONGPRESS
                and event.controller.type in (Token.KNOB, Token.VOLUME)):
            return True
        if not isinstance(event, EncoderEvent):
            return False
        rows = self.declare_bindings()
        control_id = event.controller.id
        for cls in (ControlClass.TWEAK, ControlClass.VOLUME):
            decl = resolve_local(rows, ControlRef(cls=cls, id=control_id), EventKind.ROTATE)
            if decl is not None:
                return fire(decl, self, event)
        return False

    def _open_editor_for_selection(self) -> bool:
        """NAV CLICK on the current selection: open whatever editor the
        generic plugin-parameter-menu would for the same symbol(s) — a
        submenu for a compound selection (e.g. an EQ band), else a single
        dialog. Reuses Handler.open_parameter_dialog/open_parameter_submenu,
        the same mechanism a v3 Tweak encoder's SelectionEditEffect edits
        directly and NAV-only (v2) hardware has no other way to reach.

        No ``on_change`` callback: the dialog writes ``parameter.value``
        directly, which fires this panel's parameter subscription →
        ``_model_dirty`` → ``tick`` drains into ``apply_state``.

        Sources without a submenu path (audiocard params) override
        ``open_selection_editor``; the base path assumes a ``Plugin``.
        """
        sel = self.sel_ref
        if isinstance(sel, MultiSelectable):
            rows = sel.menu_rows()
            if not rows:
                return False
            return self.open_selection_submenu(rows, sel.menu_title())
        if isinstance(sel, Selectable):
            symbol = sel.symbol_for(ParamRole.GENERIC)
            if symbol is None:
                return False
            p = self.plugin.parameters.get(symbol)
            if p is None:
                return False
            return self.open_selection_dialog(p)
        return False

    def open_selection_submenu(self, rows: tuple[tuple[str, Symbol], ...], title: str) -> bool:
        """Open a multi-symbol submenu for a compound selection. Plugin panels
        delegate to ``Handler.open_parameter_submenu``; sources without a
        ``Plugin`` (audiocard) override with their own submenu path."""
        plugin = self.plugin
        if isinstance(plugin, Plugin):
            self.handler.open_parameter_submenu(plugin, rows, title)
            return True
        return False

    def open_selection_dialog(self, parameter: Parameter) -> bool:
        """Open a single-symbol editor for the current selection. Plugin panels
        use the generic parameter dialog; sources without a ``Plugin``
        (audiocard) override to route through their own commit callback."""
        self.handler.open_parameter_dialog(parameter)
        return True

    def edit_symbol(self, symbol: Symbol, rotations: int, multiplier: float = 1.0) -> bool:
        """Step, clamp, and commit symbol's value; returns True iff changed."""
        p = self.plugin.parameters.get(symbol)
        if p is None:
            return False
        steps = ParameterSteps.for_parameter(p)
        delta = int(round(rotations * effective_multiplier(multiplier, p)))
        if delta == 0:
            return False
        new_val = steps.move(delta)
        if new_val == p.value:
            return False
        self.set_param(symbol, new_val)
        return True

    # ── param-send coalescing ─────────────────────────────────────────────

    def set_param(self, symbol: Symbol, value: float) -> None:
        """Queue a parameter change.

        Writes ``value`` into ``plugin.parameters[symbol]`` immediately so the UI
        stays consistent; the websocket send is deferred to the next ``tick()``
        so rapid encoder spins collapse into one send per symbol. Goes through
        set_param_value so a bound footswitch reconciles now, the same mirror the
        mod-host echo runs — a tweak edit must match the NAV commit path.
        """
        self._param_queue[symbol] = value
        self.plugin.set_param_value(symbol, value)

    def tick(self) -> None:
        """Drain the coalesced parameter queue, then reconcile from the model
        if any parameter changed under us since the last tick.

        Subclasses that override ``tick()`` **must** call ``super().tick()`` so
        queued sends are not lost and the model-dirty drain runs.
        """
        self._flush_param_queue()
        if self._model_dirty:
            self._model_dirty = False
            self.apply_state(self.snapshot_state())
            self._refresh_bypass_style()

    def _flush_param_queue(self) -> None:
        if not self._param_queue:
            return
        instance_id = self.plugin.instance_id
        for symbol, value in self._param_queue.items():
            self._send_param(instance_id, symbol, value)
        self._param_queue.clear()

    def _send_param(self, instance_id: str, symbol: Symbol, value: float) -> None:
        """Commit one queued param to the backend. Plugin panels send over the
        WebSocket; a synthetic source (audiocard) overrides to no-op — its
        ``set_param_value`` already wrote the hardware and there is no
        mod-host instance to mirror."""
        bridge = self.handler.ws_bridge
        if bridge is not None:
            bridge.send_parameter(instance_id, symbol, value)

    # ── chrome actions ─────────────────────────────────────────────────────

    def _on_toggle_bypass(self) -> None:
        source = self.plugin
        if not isinstance(source, BypassSource) or self._btn_bypass is None:
            return
        new_bypass = not source.is_bypassed()
        source.set_bypass(new_bypass)
        bridge = self.handler.ws_bridge
        if bridge is not None:
            bridge.send_parameter(source.instance_id, BYPASS_SYMBOL, 1.0 if new_bypass else 0.0)
        # Optimistic: the set_bypass above already marked us dirty, so tick would
        # repaint within 10ms anyway. Painting here keeps the button instant.
        self._refresh_bypass_style()

    def _on_reset(self) -> None:
        """Restore all symbols from the parse-time snapshot, skipping locked ones and :bypass."""
        source = self.plugin
        if not isinstance(source, BypassSource):
            return
        self._flush_param_queue()
        snap = source.pedalboard_snapshot
        for symbol, value in snap.items():
            if symbol == BYPASS_SYMBOL:
                continue
            if self._is_symbol_locked(source.instance_id, symbol):
                continue
            self.set_param(symbol, value)
        self._flush_param_queue()
        self.apply_state(self.snapshot_state())
        self._refresh_bypass_style()

    def _is_symbol_locked(self, instance_id: str, symbol: Symbol) -> bool:
        return self.handler.is_symbol_locked(instance_id, symbol)

    def _refresh_bypass_style(self) -> None:
        if self._btn_bypass is None:
            return
        source = self.plugin
        bypassed = source.is_bypassed() if isinstance(source, BypassSource) else False
        self._btn_bypass.set_background(BYPASS_ACTIVE_COLOR if bypassed else (0, 0, 0))
        self._btn_bypass.refresh()

    def destroy(self) -> None:
        if self._unsub_model is not None:
            self._unsub_model()
            self._unsub_model = None
        super().destroy()

    def wants_fast_tick(self) -> bool:
        return True
