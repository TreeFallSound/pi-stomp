from __future__ import annotations

from dataclasses import dataclass

from plugins.fullscreen import FullscreenPluginPanel
from plugins.layouts.arc_knob import ArcKnobWidget
from plugins.layouts.mode_selector import ModeSelectorWidget
from plugins.layouts.readout_bar import ReadoutBar
from uilib.box import Box
from uilib.config import Config
from uilib.misc import get_text_size

_W = 320
_H = 240

READOUT_Y0 = 0
READOUT_Y1 = 22

MODE_Y0 = 24
MODE_H = 34

KNOB_Y0 = 62
KNOB_Y1 = 200
KNOB_H = KNOB_Y1 - KNOB_Y0

RING_RADIUS = 32
RING_SPACING = _W // 3

_BG = (0, 0, 0)

COLOR_DECAY = (255, 180, 80)
COLOR_DRY = (110, 200, 230)
COLOR_WET = (210, 130, 230)

_DECAY_STEP_MS = 100.0
_DB_STEP = 0.8
_MODE_STEP = 1.0


@dataclass(frozen=True)
class TapReverbState:
    decay: float
    drylevel: float
    wetlevel: float
    mode: int


def _fmt_decay(ms: float) -> str:
    if ms >= 1000.0:
        return f"{ms / 1000.0:.1f}s"
    return f"{int(ms)}ms"


def _fmt_db(db: float) -> str:
    return f"{db:+.0f}dB"


class TapReverbPanel(FullscreenPluginPanel[TapReverbState]):

    def snapshot_state(self) -> TapReverbState:
        params = self.plugin.parameters

        def _val(symbol: str, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None and p.value is not None else default

        return TapReverbState(
            decay=_val("decay", 2800.0),
            drylevel=_val("drylevel", -4.0),
            wetlevel=_val("wetlevel", -12.0),
            mode=int(_val("mode", 0.0)),
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

        mode_param = self.plugin.parameters.get("mode")
        self._mode_selector = ModeSelectorWidget(
            box=Box.xywh(4, MODE_Y0, _W - 8, MODE_H),
            param=mode_param,
            handler=self.handler,
            set_param=self.set_param,
            on_change=self._on_mode_changed,
            parent=self,
        )
        self._mode_selector.set_value(self._state.mode)

        col_w = _W // 3
        knob_w = RING_SPACING
        self._knob_decay = ArcKnobWidget(
            box=Box.xywh(0 * col_w, KNOB_Y0, knob_w, KNOB_H),
            symbol="decay",
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
            symbol="drylevel",
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
            symbol="wetlevel",
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
        self.add_sel_widget(self._mode_selector)
        self.add_sel_widget(self._knob_decay)
        self.add_sel_widget(self._knob_dry)
        self.add_sel_widget(self._knob_wet)

        self.apply_state(self._state)
        self.sel_widget(self._mode_selector)

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id not in (1, 2, 3) or rotations == 0:
            return False

        if encoder_id == 2:
            self._cycle_mode(rotations)
            return True

        if encoder_id == 3:
            self._edit_knob("decay", rotations)
            return True

        sel = self.sel_ref
        if sel is None:
            return True
        if isinstance(sel, ArcKnobWidget):
            self._edit_knob(sel.symbol, rotations)
            return True
        if isinstance(sel, ModeSelectorWidget):
            self._cycle_mode(rotations)
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
        self._knob_decay.set_bypassed(bypassed)
        self._knob_dry.set_bypassed(bypassed)
        self._knob_wet.set_bypassed(bypassed)
        self._update_readout()

    def _edit_knob(self, symbol: str, rotations: int) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is None:
            return
        current = float(p.value) if p.value is not None else 0.0
        if symbol == "decay":
            step = _DECAY_STEP_MS
        elif symbol in ("drylevel", "wetlevel"):
            step = _DB_STEP
        else:
            step = (p.maximum - p.minimum) / 100.0 if p.maximum and p.minimum else 1.0
        new_val = max(p.minimum, min(p.maximum, current + rotations * step))
        if new_val == current:
            return
        self.set_param(symbol, new_val)
        knob = self._knobs_by_symbol.get(symbol)
        if knob is not None:
            knob.set_value(new_val)
        self._state = TapReverbState(
            decay=self._current("decay"),
            drylevel=self._current("drylevel"),
            wetlevel=self._current("wetlevel"),
            mode=int(self._current("mode")),
        )
        self._update_readout()

    def _cycle_mode(self, rotations: int) -> None:
        p = self.plugin.parameters.get("mode")
        if p is None:
            return
        current = int(float(p.value) if p.value is not None else 0.0)
        new_mode = max(int(p.minimum), min(int(p.maximum), current + int(rotations)))
        if new_mode == current:
            return
        self.set_param("mode", float(new_mode))
        self._mode_selector.set_value(new_mode)
        self._state = TapReverbState(
            decay=self._current("decay"),
            drylevel=self._current("drylevel"),
            wetlevel=self._current("wetlevel"),
            mode=new_mode,
        )
        self._update_readout()

    def _current(self, symbol: str) -> float:
        p = self.plugin.parameters.get(symbol)
        return float(p.value) if p is not None and p.value is not None else 0.0

    def _on_mode_changed(self, new_mode: int) -> None:
        self._state = TapReverbState(
            decay=self._current("decay"),
            drylevel=self._current("drylevel"),
            wetlevel=self._current("wetlevel"),
            mode=new_mode,
        )
        self._update_readout()

    def _reset_to_default(self, symbol: str) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is None or p.default is None:
            return
        default_val = float(p.default)
        self.set_param(symbol, default_val)
        if symbol == "mode":
            self._mode_selector.set_value(int(default_val))
        else:
            knob = self._knobs_by_symbol.get(symbol)
            if knob is not None:
                knob.set_value(default_val)
        self._state = TapReverbState(
            decay=self._current("decay"),
            drylevel=self._current("drylevel"),
            wetlevel=self._current("wetlevel"),
            mode=int(self._current("mode")),
        )
        self._update_readout()

    def _update_readout(self) -> None:
        sel = self.sel_ref
        if isinstance(sel, ArcKnobWidget):
            val = self._current(sel.symbol)
            self._readout.set_text(f"{sel._label.capitalize()}: {sel._formatter(val)}")
        elif isinstance(sel, ModeSelectorWidget):
            self._readout.set_text("Select reverb mode")
            self._readout.set_subtitle(f"{self._mode_selector.value + 1} of {self._mode_selector.max_index + 1}")
            return
        elif sel is self._btn_bypass:
            self._readout.set_text("Plugin bypassed" if self.plugin.is_bypassed() else "Bypass plugin")
        elif sel is self._btn_back:
            self._readout.set_text("Close")
        elif sel is self._btn_reset:
            self._readout.set_text("Reset to pedalboard")
        else:
            self._readout.set_text("TAP Reverberator")
        self._readout.set_subtitle("")

    def _select_widget_ref(self, w):
        super()._select_widget_ref(w)
        self._update_readout()
