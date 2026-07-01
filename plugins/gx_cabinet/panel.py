from __future__ import annotations

from dataclasses import dataclass

from plugins.fullscreen import FullscreenPluginPanel
from plugins.layouts.arc_knob import ArcKnobWidget
from plugins.layouts.mode_selector import ModeSelectorWidget
from plugins.layouts.readout_bar import ReadoutBar
from uilib.box import Box
from uilib.config import Config

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
_MODE_STEP = 1.0


@dataclass(frozen=True)
class GxCabinetState:
    level: float
    bass: float
    treble: float
    model: int


def _fmt_level(v: float) -> str:
    return f"{v:.2f}x"


def _fmt_tone(v: float) -> str:
    return f"{v:+.1f}"


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
        self.add_sel_widget(self._mode_selector)
        self.add_sel_widget(self._knob_level)
        self.add_sel_widget(self._knob_bass)
        self.add_sel_widget(self._knob_treble)

        self.apply_state(self._state)
        self.sel_widget(self._mode_selector)

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id not in (1, 2, 3) or rotations == 0:
            return False

        if encoder_id == 2:
            self._cycle_model(rotations)
            return True

        if encoder_id == 3:
            self._edit_knob("CLevel", rotations)
            return True

        sel = self.sel_ref
        if sel is None:
            return True
        if isinstance(sel, ArcKnobWidget):
            self._edit_knob(sel.symbol, rotations)
            return True
        if isinstance(sel, ModeSelectorWidget):
            self._cycle_model(rotations)
            return True
        return True

    def tick(self) -> None:
        bypassed = self.plugin.is_bypassed()
        if bypassed != getattr(self, "_last_bypassed", None):
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

    def _edit_knob(self, symbol: str, rotations: int) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is None:
            return
        current = float(p.value) if p.value is not None else 0.0
        step = _LEVEL_STEP if symbol == "CLevel" else _TONE_STEP
        new_val = max(p.minimum, min(p.maximum, current + rotations * step))
        if new_val == current:
            return
        self.set_param(symbol, new_val)
        knob = self._knobs_by_symbol.get(symbol)
        if knob is not None:
            knob.set_value(new_val)
        self._state = GxCabinetState(
            level=self._current("CLevel"),
            bass=self._current("CBass"),
            treble=self._current("CTreble"),
            model=int(self._current("c_model")),
        )
        self._update_readout()

    def _cycle_model(self, rotations: int) -> None:
        p = self.plugin.parameters.get("c_model")
        if p is None:
            return
        current = int(float(p.value) if p.value is not None else 0.0)
        new_model = max(int(p.minimum), min(int(p.maximum), current + int(rotations)))
        if new_model == current:
            return
        self.set_param("c_model", float(new_model))
        self._mode_selector.set_value(new_model)
        self._state = GxCabinetState(
            level=self._current("CLevel"),
            bass=self._current("CBass"),
            treble=self._current("CTreble"),
            model=new_model,
        )
        self._update_readout()

    def _current(self, symbol: str) -> float:
        p = self.plugin.parameters.get(symbol)
        return float(p.value) if p is not None and p.value is not None else 0.0

    def _on_model_changed(self, new_model: int) -> None:
        self._state = GxCabinetState(
            level=self._current("CLevel"),
            bass=self._current("CBass"),
            treble=self._current("CTreble"),
            model=new_model,
        )
        self._update_readout()

    def _reset_to_default(self, symbol: str) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is None or p.default is None:
            return
        default_val = float(p.default)
        self.set_param(symbol, default_val)
        if symbol == "c_model":
            self._mode_selector.set_value(int(default_val))
        else:
            knob = self._knobs_by_symbol.get(symbol)
            if knob is not None:
                knob.set_value(default_val)
        self._state = GxCabinetState(
            level=self._current("CLevel"),
            bass=self._current("CBass"),
            treble=self._current("CTreble"),
            model=int(self._current("c_model")),
        )
        self._update_readout()

    def _update_readout(self) -> None:
        sel = self.sel_ref
        if isinstance(sel, ArcKnobWidget):
            val = self._current(sel.symbol)
            self._readout.set_text(f"{sel._label.capitalize()}: {sel._formatter(val)}")
        elif isinstance(sel, ModeSelectorWidget):
            self._readout.set_text("Select cabinet model")
            self._readout.set_subtitle(f"{self._mode_selector.value + 1} of {self._mode_selector.max_index + 1}")
            return
        elif sel is self._btn_bypass:
            self._readout.set_text("Plugin bypassed" if self.plugin.is_bypassed() else "Bypass plugin")
        elif sel is self._btn_back:
            self._readout.set_text("Close")
        elif sel is self._btn_reset:
            self._readout.set_text("Reset to pedalboard")
        else:
            self._readout.set_text("GxCabinet")
        self._readout.set_subtitle("")

    def _select_widget_ref(self, w):
        super()._select_widget_ref(w)
        self._update_readout()
