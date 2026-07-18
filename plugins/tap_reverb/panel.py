from __future__ import annotations

from dataclasses import dataclass

from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextRef,
    ControlClass,
    ControlRef,
    EventKind,
    ParamEffect,
    SelectionEditEffect,
)
from common.parameter import Symbol
from modalapi.plugin import Plugin
from plugins.fullscreen import FullscreenPluginPanel
from plugins.layouts.arc_knob import ArcKnobWidget
from plugins.layouts.mode_selector import ModeSelectorWidget
from plugins.layouts.readout_bar import ReadoutBar
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.badge import BadgeGlyph

_W = 320
_H = 240

READOUT_Y0 = 0
READOUT_Y1 = 22

MODE_Y0 = 24
MODE_H = 34

KNOB_Y0 = 62
KNOB_Y1 = 200
KNOB_H = KNOB_Y1 - KNOB_Y0

RING_SPACING = _W // 3

_BG = (0, 0, 0)

COLOR_DECAY = (255, 180, 80)
COLOR_DRY = (110, 200, 230)
COLOR_WET = (210, 130, 230)

_BADGE_TWEAK1 = BadgeGlyph("1")  # enc1, selection-dependent (SelectionEditEffect) — shown in the readout only
_BADGE_TWEAK2 = BadgeGlyph("2")  # enc2, fixed to mode — drawn on the mode selector itself (static, not selection-dependent)
_BADGE_TWEAK3 = BadgeGlyph("3")  # enc3/Volume, fixed to decay — drawn on the knob itself (static, not selection-dependent)


@dataclass(frozen=True)
class TapReverbState:
    decay: float
    drylevel: float
    wetlevel: float
    mode: int


def _fmt_decay(ms: float) -> tuple[str, str]:
    if ms >= 1000.0:
        return f"{ms / 1000.0:.1f}", "s"
    return f"{int(ms)}", "ms"


def _fmt_db(db: float) -> tuple[str, str]:
    return f"{db:+.0f}", "dB"


class TapReverbPanel(FullscreenPluginPanel[TapReverbState]):
    plugin: Plugin  # narrowing: TapReverbPanel is always a Plugin panel

    def snapshot_state(self) -> TapReverbState:
        params = self.plugin.parameters

        def _val(symbol: Symbol, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None else default

        return TapReverbState(
            decay=_val(Symbol("decay"), 2800.0),
            drylevel=_val(Symbol("drylevel"), -4.0),
            wetlevel=_val(Symbol("wetlevel"), -12.0),
            mode=int(_val(Symbol("mode"), 0.0)),
        )

    def apply_state(self, state: TapReverbState) -> None:
        self._state = state
        self._knob_decay.set_value(state.decay)
        self._knob_dry.set_value(state.drylevel)
        self._knob_wet.set_value(state.wetlevel)
        self._mode_selector.set_value(state.mode)
        self._update_readout()

    def build_widgets(self) -> None:
        self._state = self.snapshot_state()
        cfg = Config()
        btn_font = cfg.get_font("default")

        self._readout = ReadoutBar(
            box=Box.xywh(0, READOUT_Y0, _W, READOUT_Y1 - READOUT_Y0),
            font=btn_font,
            parent=self,
        )

        mode_param = self.plugin.parameters.get(Symbol("mode"))
        assert mode_param is not None, "tap_reverb plugin is missing its mode parameter"
        self._mode_selector = ModeSelectorWidget(
            box=Box.xywh(4, MODE_Y0, _W - 8, MODE_H),
            param=mode_param,
            handler=self.handler,
            set_param=self.set_param,
            on_change=self._on_mode_changed,
            parent=self,
        )
        self._mode_selector.set_value(self._state.mode)
        self._mode_selector.set_badge(_BADGE_TWEAK2)

        col_w = _W // 3
        knob_w = RING_SPACING
        self._knob_decay = ArcKnobWidget(
            box=Box.xywh(0 * col_w, KNOB_Y0, knob_w, KNOB_H),
            symbol=Symbol("decay"),
            label="DECAY",
            color=COLOR_DECAY,
            minimum=0.0,
            maximum=10000.0,
            formatter=_fmt_decay,
            panel=self,
            parent=self,
        )
        self._knob_dry = ArcKnobWidget(
            box=Box.xywh(1 * col_w, KNOB_Y0, knob_w, KNOB_H),
            symbol=Symbol("drylevel"),
            label="DRY",
            color=COLOR_DRY,
            minimum=-70.0,
            maximum=10.0,
            formatter=_fmt_db,
            panel=self,
            parent=self,
        )
        self._knob_wet = ArcKnobWidget(
            box=Box.xywh(2 * col_w, KNOB_Y0, knob_w, KNOB_H),
            symbol=Symbol("wetlevel"),
            label="WET",
            color=COLOR_WET,
            minimum=-70.0,
            maximum=10.0,
            formatter=_fmt_db,
            panel=self,
            parent=self,
        )

        self._knobs_by_symbol: dict[str, ArcKnobWidget] = {
            "decay": self._knob_decay,
            "drylevel": self._knob_dry,
            "wetlevel": self._knob_wet,
        }
        self._knob_decay.set_badge(_BADGE_TWEAK3)
        self.add_sel_widget(self._mode_selector)
        self.add_sel_widget(self._knob_decay)
        self.add_sel_widget(self._knob_dry)
        self.add_sel_widget(self._knob_wet)

        self.apply_state(self._state)
        self.sel_widget(self._mode_selector)

    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="tap_reverb")
        # enc3 is chassis-labeled Tweak3/Volume; decay stays bound there as a
        # deliberate, explicit override (see ContextLayer.add in common/contexts.py).
        volume_ctx = ContextRef(kind=ContextKind.PANEL, name="tap_reverb", override_volume=True)
        return (
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=1),
                event_kind=EventKind.ROTATE,
                effects=(SelectionEditEffect(),),
                context=panel_ctx,
            ),
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=2),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=self.plugin, symbol=Symbol("mode")),),
                context=panel_ctx,
            ),
            BindingDecl(
                control=ControlRef(cls=ControlClass.VOLUME, id=3),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=self.plugin, symbol=Symbol("decay")),),
                context=volume_ctx,
            ),
        )

    def edit_symbol(self, symbol: Symbol, rotations: int, multiplier: float = 1.0) -> bool:
        if not super().edit_symbol(symbol, rotations, multiplier):
            return False
        self._sync_after_edit(symbol)
        return True

    def _sync_after_edit(self, symbol: Symbol) -> None:
        knob = self._knobs_by_symbol.get(symbol)
        if knob is not None:
            knob.set_value(self._current(symbol))
        elif symbol == "mode":
            self._mode_selector.set_value(int(self._current(symbol)))
        self._state = self.snapshot_state()
        self._update_readout()

    def tick(self) -> None:
        super().tick()

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        bypassed = self.plugin.is_bypassed()
        self._knob_decay.set_bypassed(bypassed)
        self._knob_dry.set_bypassed(bypassed)
        self._knob_wet.set_bypassed(bypassed)
        self._update_readout()

    def _current(self, symbol: Symbol) -> float:
        p = self.plugin.parameters.get(symbol)
        return float(p.value) if p is not None else 0.0

    def _on_mode_changed(self, new_mode: int) -> None:
        """Wired as ModeSelectorWidget's on_change. Optimistic: apply_state does
        the same on the next tick — this only spares the readout that 10ms."""
        self._state = self.snapshot_state()
        self._update_readout()

    def _reset_to_default(self, symbol: Symbol) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is None:
            return
        self.set_param(symbol, p.default)
        self._sync_after_edit(symbol)

    def _update_readout(self) -> None:
        sel = self.sel_ref
        if isinstance(sel, ArcKnobWidget):
            val = self._current(sel.symbol)
            self._readout.set_text(f"{sel._label.capitalize()}: {sel.reading_text(val)}")
            self._readout.set_badge(_BADGE_TWEAK1)
        elif isinstance(sel, ModeSelectorWidget):
            self._readout.set_text("Select reverb mode")
            self._readout.set_subtitle(f"{self._mode_selector.value + 1} of {self._mode_selector.max_index + 1}")
            # enc1 still edits the selection here too (same symbol enc2 is fixed
            # to) — the readout badge means "enc1 edits your selection", a fact
            # that's true regardless of what's selected, not "enc2 is bound".
            self._readout.set_badge(_BADGE_TWEAK1)
            return
        elif sel is self._btn_bypass:
            self._readout.set_text("Plugin bypassed" if self.plugin.is_bypassed() else "Bypass plugin")
            self._readout.set_badge(None)
        elif sel is self._btn_back:
            self._readout.set_text("Close")
            self._readout.set_badge(None)
        elif sel is self._btn_reset:
            self._readout.set_text("Reset to pedalboard")
            self._readout.set_badge(None)
        else:
            self._readout.set_text("TAP Reverberator")
            self._readout.set_badge(None)
        self._readout.set_subtitle("")

    def _select_widget_ref(self, w):
        super()._select_widget_ref(w)
        self._update_readout()
