"""Concrete fullscreen panel for the TAP Reverberator plugin.

Layout (320×240, content y=0..210, chrome y=210..240)::

    y=0  ┌────────────────────────────────────────────────┐
         │ TAP REVERB                                     │  readout (22 px)
    y=22 ├────────────────────────────────────────────────┤
         │ ‹ Hall (Large) - HD ›              15/42       │  mode strip (36 px)
         │ ────────●───────────────────────────            │  progress bar
    y=64 ├────────────────────────────────────────────────┤
         │                                                │
         │  ╭───────╮       ╭───────╮       ╭───────╮       │
         │  │ DECAY │       │  DRY  │       │  WET  │       │  3 arc rings
         │  │ 2.8s  │       │ -4 dB │       │-12 dB │       │  (y=70..190)
         │  ╰───────╯       ╰───────╯       ╰───────╯       │
         │                                                │
    y=210├────────────────────────────────────────────────┤
         │  [ Back ]   [ Bypass ]   [ Reset ]             │  chrome
    y=240┴────────────────────────────────────────────────┘

Encoder mapping:
    Tweak1 — edit the focused value (Decay / Dry / Wet / Mode)
    Tweak2 — cycle Mode ±1 (shortcut, regardless of focus)
    Tweak3 — edit Decay (shortcut, regardless of focus)
    Nav    — cycle Decay → Dry → Wet → Mode → chrome

CLICK on any value resets it to the plugin's ``lv2:default``.
The chrome ``Reset`` button restores all values to the pedalboard snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

from plugins.fullscreen import FullscreenPluginPanel
from plugins.tap_reverb.mode_selector import ModeSelectorWidget
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.arc_ring import ArcRingGlyph
from uilib.misc import InputEvent, get_text_size
from uilib.widget import Widget

# ── layout constants ───────────────────────────────────────────────────────

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
RING_SPACING = _W // 3  # 3 knobs, equal columns

# ── colours ─────────────────────────────────────────────────────────────────

_BG = (0, 0, 0)
_RING_EMPTY = (50, 50, 50)
_RING_TIP = (255, 255, 255)
_LABEL_FG = (180, 180, 180)
_VALUE_FG = (255, 255, 255)
_READOUT_COLOR = (200, 200, 200)

# Per-knob colours (warm ramp: orange=time, cyan=blend-in, purple=depth)
COLOR_DECAY = (255, 180, 80)
COLOR_DRY = (110, 200, 230)
COLOR_WET = (210, 130, 230)

# Ring colour shade when the plugin is bypassed (matches plugins/eq/parametric.py)
INACTIVE_SHADE = 0.45

# ── tweak step sizes ────────────────────────────────────────────────────────

_DECAY_STEP_MS = 100.0  # 0..10000 ms → 100 detents
_DB_STEP = 0.8  # -70..+10 dB → 100 detents
_MODE_STEP = 1.0  # enumeration: one detent per index


@dataclass(frozen=True)
class TapReverbState:
    decay: float  # ms, 0..10000
    drylevel: float  # dB, -70..+10
    wetlevel: float  # dB, -70..+10
    mode: int  # 0..42


# ── formatters ───────────────────────────────────────────────────────────────


def _fmt_decay(ms: float) -> str:
    if ms >= 1000.0:
        return f"{ms / 1000.0:.1f}s"
    return f"{int(ms)}ms"


def _fmt_db(db: float) -> str:
    return f"{db:+.0f}dB"


# ── KnobWidget ───────────────────────────────────────────────────────────────


class KnobWidget(Widget):
    """Arc-ring knob for a continuous parameter (decay / dry / wet).

    Nav-selectable leaf. Tweak1 (when focused) edits the value.
    CLICK resets to ``lv2:default``.
    """

    def __init__(
        self,
        box: Box,
        symbol: str,
        label: str,
        color: tuple[int, int, int],
        minimum: float,
        maximum: float,
        formatter,
        panel: "TapReverbPanel",
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", _BG)
        super().__init__(box=box, **kwargs)
        self.symbol = symbol
        self._label = label
        self._color = color
        self._minimum = minimum
        self._maximum = maximum
        self._formatter = formatter
        self._panel = panel
        self._value: float = minimum
        self._bypassed: bool = False
        self._ring = ArcRingGlyph(RING_RADIUS)

        cfg = Config()
        self._label_font = cfg.get_font("tiny")
        self._value_font = cfg.get_font("small")

    def set_value(self, value: float) -> None:
        value = max(self._minimum, min(self._maximum, value))
        if value == self._value:
            return
        self._value = value
        self.refresh()

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def _draw_erase(self, ctx) -> None:  # type: ignore[override]
        ctx.draw_rectangle(ctx.dirty_bounds, fill=_BG)

    def _draw(self, ctx) -> None:
        cx = ctx.width // 2
        cy = (ctx.height // 2) - 8

        # Arc ring — dimmed when the plugin is bypassed (matches parametric EQ)
        shade = INACTIVE_SHADE if self._bypassed else 1.0
        cr, cg, cb = self._color
        ring_color = (int(cr * shade), int(cg * shade), int(cb * shade))
        tr, tg, tb = _RING_TIP
        tip_color = (int(tr * shade), int(tg * shade), int(tb * shade))
        span = self._maximum - self._minimum
        t = (self._value - self._minimum) / span if span > 0 else 0.0
        t = max(0.0, min(1.0, t))
        ring = self._ring.render(t, ring_color, _RING_EMPTY, tip_color)
        hs = self._ring.half_size
        ctx.paste(ring, (cx - hs, cy - hs))

        # Value text — centered inside the ring
        val_text = self._formatter(self._value)
        vw, vh = get_text_size(val_text, self._value_font)
        ctx.draw_text((cx - vw // 2, cy - vh // 2), val_text, fill=_VALUE_FG, font=self._value_font)

        # Label — below the ring
        lw, lh = get_text_size(self._label, self._label_font)
        ctx.draw_text((cx - lw // 2, cy + hs + 2), self._label, fill=_LABEL_FG, font=self._label_font)

    def input_event(self, event) -> bool:  # type: ignore[override]
        if event == InputEvent.CLICK:
            self._panel._reset_to_default(self.symbol)
            return True
        return False


# ── ReadoutWidget ───────────────────────────────────────────────────────────


class ReadoutWidget(Widget):
    """Top-bar showing the plugin name or the focused control's description."""

    def __init__(self, box: Box, font, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", _BG)
        super().__init__(box=box, **kwargs)
        self._font = font
        self._text = ""
        self._subtitle = ""

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self.refresh()

    def set_subtitle(self, subtitle: str) -> None:
        if subtitle == self._subtitle:
            return
        self._subtitle = subtitle
        self.refresh()

    def _draw_erase(self, ctx) -> None:  # type: ignore[override]
        ctx.draw_rectangle(ctx.dirty_bounds, fill=_BG)

    def _draw(self, ctx) -> None:
        if self._text:
            ctx.draw_text((6, 1), self._text, fill=_READOUT_COLOR, font=self._font)
        if self._subtitle:
            sw, _ = get_text_size(self._subtitle, self._font)
            ctx.draw_text((ctx.width - sw - 6, 1), self._subtitle, fill=_READOUT_COLOR, font=self._font)


# ── TapReverbPanel ──────────────────────────────────────────────────────────


class TapReverbPanel(FullscreenPluginPanel[TapReverbState]):
    """Full-screen panel for editing a TAP Reverberator instance."""

    # ── PluginPanel subclass contract ────────────────────────────────────────

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

        # Readout bar
        self._readout = ReadoutWidget(
            box=Box.xywh(0, READOUT_Y0, _W, READOUT_Y1 - READOUT_Y0),
            font=btn_font,
            parent=self,
        )

        # Mode selector strip (4px L/R margin from screen edges)
        self._mode_selector = ModeSelectorWidget(
            box=Box.xywh(4, MODE_Y0, _W - 8, MODE_H),
            parent=self,
            panel=self,
        )
        mode_param = self.plugin.parameters.get("mode")
        if mode_param is not None and mode_param.enum_values:
            labels = [item[0] for item in mode_param.get_enum_value_list()]
            self._mode_selector.set_labels(labels)
        else:
            self._mode_selector.set_labels([str(i) for i in range(43)])
        self._mode_selector.set_value(self._state.mode)

        # 3 knobs — Decay | Dry | Wet
        col_w = _W // 3
        knob_w = RING_SPACING
        self._knob_decay = KnobWidget(
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
        self._knob_dry = KnobWidget(
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
        self._knob_wet = KnobWidget(
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

        # Register selectables: Mode → Decay → Dry → Wet (chrome appended after)
        self._knobs_by_symbol: dict[str, KnobWidget] = {
            "decay": self._knob_decay,
            "drylevel": self._knob_dry,
            "wetlevel": self._knob_wet,
        }
        self.add_sel_widget(self._mode_selector)
        self.add_sel_widget(self._knob_decay)
        self.add_sel_widget(self._knob_dry)
        self.add_sel_widget(self._knob_wet)

        # Apply initial state to widgets
        self.apply_state(self._state)
        self.sel_widget(self._mode_selector)

    # ── encoder dispatch ─────────────────────────────────────────────────────

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id not in (1, 2, 3) or rotations == 0:
            return False

        # Tweak2: always cycle Mode
        if encoder_id == 2:
            self._cycle_mode(rotations)
            return True

        # Tweak3: always edit Decay
        if encoder_id == 3:
            self._edit_knob("decay", rotations)
            return True

        # Tweak1: edit the focused widget's symbol
        sel = self.sel_ref
        if sel is None:
            return True
        if isinstance(sel, KnobWidget):
            self._edit_knob(sel.symbol, rotations)
            return True
        if isinstance(sel, ModeSelectorWidget):
            self._cycle_mode(rotations)
            return True
        # On chrome (Back/Bypass/Reset) — consume silently
        return True

    # ── tick ────────────────────────────────────────────────────────────────

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

    # ── state helpers ───────────────────────────────────────────────────────

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

    # ── reset to lv2:default ─────────────────────────────────────────────────

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

    # ── open parameter dialog for mode ──────────────────────────────────────

    def _open_mode_dialog(self) -> None:
        """Open a selection menu of all 43 mode labels, starting on the
        current value.

        Built directly (rather than via ``lcd.draw_parameter_dialog``) so the
        item action lands on ``_commit_mode`` — the generic dialog commits
        through ``handler.parameter_value_commit``, which updates only the
        cached ``Parameter.value`` and relies on mod-ui's WS echo to reach the
        panel; that leaves this widget showing the old mode until (or unless)
        the echo arrives. Nav/Tweak2 update it immediately, so the dialog
        should too.
        """
        p = self.plugin.parameters.get("mode")
        if p is None:
            return
        lcd = self.handler.lcd
        if lcd is None:
            return
        current_value = p.value
        default_item: str | None = None
        items = []
        for label, value in p.get_enum_value_list():
            selected = value == current_value
            if selected:
                default_item = f"✔ {label}"
            items.append((label, self._commit_mode, value, selected))
        title = f"{p.instance_id}:{p.name}"
        lcd.draw_selection_menu(items, title, auto_dismiss=True, default_item=default_item)

    def _commit_mode(self, value: float) -> None:
        new_mode = int(value)
        self.set_param("mode", float(new_mode))
        self._mode_selector.set_value(new_mode)
        self._state = TapReverbState(
            decay=self._current("decay"),
            drylevel=self._current("drylevel"),
            wetlevel=self._current("wetlevel"),
            mode=new_mode,
        )
        self._update_readout()

    # ── readout ─────────────────────────────────────────────────────────────

    def _update_readout(self) -> None:
        sel = self.sel_ref
        if isinstance(sel, KnobWidget):
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

    def _select_widget_ref(self, w):  # type: ignore[override]
        super()._select_widget_ref(w)
        self._update_readout()
