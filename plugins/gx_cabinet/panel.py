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

COLOR_LEVEL = (255, 180, 80)
COLOR_BASS = (110, 200, 230)
COLOR_TREBLE = (210, 130, 230)

_LEVEL_STEP = 0.05
_TONE_STEP = 0.4

_KNOB_STEPS = {"CLevel": _LEVEL_STEP, "CBass": _TONE_STEP, "CTreble": _TONE_STEP}

_BADGE_TWEAK1 = BadgeGlyph("1")  # enc1, selection-dependent (SelectionEditEffect) — shown in the readout only
_BADGE_TWEAK2 = BadgeGlyph("2")  # enc2, fixed to c_model — drawn on the mode selector itself (static, not selection-dependent)
_BADGE_TWEAK3 = BadgeGlyph("3")  # enc3/Volume, fixed to CLevel — drawn on the knob itself (static, not selection-dependent)


@dataclass(frozen=True)
class GxCabinetState:
    level: float
    bass: float
    treble: float
    model: int


def _fmt_level(v: float) -> tuple[str, str]:
    return f"{v:.2f}", "×"


def _fmt_tone(v: float) -> tuple[str, str]:
    return f"{v:+.1f}", "dB"


class GxCabinetPanel(FullscreenPluginPanel[GxCabinetState]):

    def snapshot_state(self) -> GxCabinetState:
        params = self.plugin.parameters

        def _val(symbol: str, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None and p.value is not None else default

        return GxCabinetState(
            level=_val("CLevel", 1.0),
            bass=_val("CBass", 0.0),
            treble=_val("CTreble", 0.0),
            model=int(_val("c_model", 0.0)),
        )

    def apply_state(self, state: GxCabinetState) -> None:
        self._state = state
        self._knob_level.set_value(state.level)
        self._knob_bass.set_value(state.bass)
        self._knob_treble.set_value(state.treble)
        self._mode_selector.set_value(state.model)
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

        model_param = self.plugin.parameters.get("c_model")
        assert model_param is not None, "gx_cabinet plugin is missing its c_model parameter"
        self._mode_selector = ModeSelectorWidget(
            box=Box.xywh(4, MODE_Y0, _W - 8, MODE_H),
            param=model_param,
            handler=self.handler,
            set_param=self.set_param,
            on_change=self._on_model_changed,
            parent=self,
        )
        self._mode_selector.symbol = "c_model"
        self._mode_selector.set_value(self._state.model)
        self._mode_selector.set_badge(_BADGE_TWEAK2)

        col_w = _W // 3
        knob_w = RING_SPACING
        self._knob_level = ArcKnobWidget(
            box=Box.xywh(0 * col_w, KNOB_Y0, knob_w, KNOB_H),
            symbol="CLevel",
            label="LEVEL",
            color=COLOR_LEVEL,
            minimum=0.5,
            maximum=5.0,
            formatter=_fmt_level,
            panel=self,
            parent=self,
        )
        self._knob_bass = ArcKnobWidget(
            box=Box.xywh(1 * col_w, KNOB_Y0, knob_w, KNOB_H),
            symbol="CBass",
            label="BASS",
            color=COLOR_BASS,
            minimum=-10.0,
            maximum=10.0,
            formatter=_fmt_tone,
            panel=self,
            parent=self,
        )
        self._knob_treble = ArcKnobWidget(
            box=Box.xywh(2 * col_w, KNOB_Y0, knob_w, KNOB_H),
            symbol="CTreble",
            label="TREBLE",
            color=COLOR_TREBLE,
            minimum=-10.0,
            maximum=10.0,
            formatter=_fmt_tone,
            panel=self,
            parent=self,
        )

        self._knobs_by_symbol: dict[str, ArcKnobWidget] = {
            "CLevel": self._knob_level,
            "CBass": self._knob_bass,
            "CTreble": self._knob_treble,
        }
        self._knob_level.set_badge(_BADGE_TWEAK3)
        self.add_sel_widget(self._mode_selector)
        self.add_sel_widget(self._knob_level)
        self.add_sel_widget(self._knob_bass)
        self.add_sel_widget(self._knob_treble)

        self.apply_state(self._state)
        self.sel_widget(self._mode_selector)

        self._last_bypassed = self.plugin.is_bypassed()

    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="gx_cabinet")
        # enc3 is chassis-labeled Tweak3/Volume; CLevel stays bound there as a
        # deliberate, explicit override (see ContextLayer.add in common/contexts.py).
        volume_ctx = ContextRef(kind=ContextKind.PANEL, name="gx_cabinet", override_volume=True)
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
                effects=(ParamEffect(plugin=self.plugin, symbol="c_model"),),
                context=panel_ctx,
            ),
            BindingDecl(
                control=ControlRef(cls=ControlClass.VOLUME, id=3),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=self.plugin, symbol="CLevel"),),
                context=volume_ctx,
            ),
        )

    def edit_symbol(self, symbol: str, rotations: int) -> bool:
        step = _KNOB_STEPS.get(symbol)
        if step is not None:
            p = self.plugin.parameters.get(symbol)
            if p is None or p.value is None:
                return False
            new_val = max(p.minimum, min(p.maximum, float(p.value) + rotations * step))
            if new_val == p.value:
                return False
            self.set_param(symbol, new_val)
        elif symbol == "c_model":
            p = self.plugin.parameters.get(symbol)
            if p is None or p.value is None:
                return False
            new_val = max(int(p.minimum), min(int(p.maximum), int(p.value) + int(rotations)))
            if new_val == p.value:
                return False
            self.set_param(symbol, float(new_val))
        elif not super().edit_symbol(symbol, rotations):
            return False
        self._sync_after_edit(symbol)
        return True

    def _sync_after_edit(self, symbol: str) -> None:
        knob = self._knobs_by_symbol.get(symbol)
        if knob is not None:
            knob.set_value(self._current(symbol))
        elif symbol == "c_model":
            self._mode_selector.set_value(int(self._current(symbol)))
        self._state = self.snapshot_state()
        self._update_readout()

    def tick(self) -> None:
        bypassed = self.plugin.is_bypassed()
        if bypassed != self._last_bypassed:
            self._last_bypassed = bypassed
            self._refresh_bypass_style()
        super().tick()

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        bypassed = self.plugin.is_bypassed()
        self._knob_level.set_bypassed(bypassed)
        self._knob_bass.set_bypassed(bypassed)
        self._knob_treble.set_bypassed(bypassed)
        self._update_readout()

    def _current(self, symbol: str) -> float:
        p = self.plugin.parameters.get(symbol)
        return float(p.value) if p is not None and p.value is not None else 0.0

    def _on_model_changed(self, new_model: int) -> None:
        """Wired as ModeSelectorWidget's on_change — fires from its own
        selection-dialog commit path, not the encoder/edit_symbol path."""
        self._state = self.snapshot_state()
        self._update_readout()

    def _reset_to_default(self, symbol: str) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is None or p.default is None:
            return
        self.set_param(symbol, float(p.default))
        self._sync_after_edit(symbol)

    def _update_readout(self) -> None:
        sel = self.sel_ref
        if isinstance(sel, ArcKnobWidget):
            val = self._current(sel.symbol)
            self._readout.set_text(f"{sel._label.capitalize()}: {sel.reading_text(val)}")
            self._readout.set_badge(_BADGE_TWEAK1)
        elif isinstance(sel, ModeSelectorWidget):
            self._readout.set_text("Select cabinet model")
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
            self._readout.set_text("GxCabinet")
            self._readout.set_badge(None)
        self._readout.set_subtitle("")

    def _select_widget_ref(self, w):
        super()._select_widget_ref(w)
        self._update_readout()
