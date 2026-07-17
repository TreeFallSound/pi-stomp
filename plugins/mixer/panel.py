"""Full-screen mixer panel: fader columns + Master/Alt arc rings.

Four 56px channel zones — each a volume fader, S/M/A toggles and a pan bar —
share the left 224px; the Master/Alt arc rings fill the right 96px. A flat
selection model (22 controls + 3 chrome buttons) cycles under NAV; TWEAK1 edits
the selection, TWEAK2 edits pan when a fader is selected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextRef,
    ControlClass,
    ControlRef,
    EventKind,
    SelectionEditEffect,
)
from common.param_roles import ParamRole
from common.parameter import Symbol
from plugins.fullscreen import FullscreenPluginPanel
from plugins.layouts.arc_knob import ArcKnobWidget
from plugins.layouts.readout_bar import ReadoutBar
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.badge import BadgeGlyph
from uilib.glyphs.bar import FILL_ACTIVE, READOUT_COLOR, TRACK_COLOR, paint_bar
from uilib.glyphs.node import paint_band_node
from uilib.glyphs.toggle import ToggleGlyph
from uilib.misc import InputEvent, get_text_size
from uilib.widget import Widget

# ── layout ────────────────────────────────────────────────────────────────────

_W = 320
_H = 240

READOUT_H = 22

CH_ZONE_W = 56           # 4 zones = 224px; the right 96px holds the arc rings
VOL_COL_W = 28

CH_LABEL_Y = 24          # channel header row, just under the readout bar
BAR_W = 3                # track+fill width — identical to the graphic-EQ bar
BAR_Y0 = 40              # fader/pan track top, in panel coords
BAR_Y1 = 186            # track bottom; nodes and fill live between the two
LABEL_ROOM = 16         # space under a track for its bottom readout

VOL_TRACK_H = BAR_Y1 - BAR_Y0
VOL_DB_Y = VOL_TRACK_H + 2       # dB readout, in the fader widget's local coords
VOL_COL_H = VOL_TRACK_H + LABEL_ROOM

TOGGLE_SIZE = 18         # S/M/A toggles are square
TOGGLE_RADIUS = 4        # chip corner radius; the selection reticule matches it
TOGGLE_X = 32            # relative to the zone
TOGGLE_Y0 = 44
TOGGLE_PITCH = 21

CTRL_CX = TOGGLE_X + TOGGLE_SIZE // 2   # pan shares the S/M/A column, centred under it
PAN_Y0 = TOGGLE_Y0 + 3 * TOGGLE_PITCH + 4   # just below the A toggle
PAN_TRACK_H = BAR_Y1 - PAN_Y0
PAN_LABEL_Y = PAN_TRACK_H + 2    # pan readout, in the pan widget's local coords
PAN_COL_W = 26           # wide enough for the pan label
PAN_COL_H = PAN_TRACK_H + LABEL_ROOM

ARC_X = 224
ARC_W = 96
MASTER_ARC_Y = 24
ALT_ARC_Y = 114
ARC_H = 86

# ── colours ───────────────────────────────────────────────────────────────────

BG_BLACK = (0, 0, 0)
SEPARATOR_COLOR = (50, 50, 50)
PAN_NODE_COLOR = (255, 255, 255)

CHANNEL_COLORS: tuple[tuple[int, int, int], ...] = (
    (0, 180, 200),    # Ch1 — cyan
    (0, 200, 80),     # Ch2 — green
    (200, 180, 0),    # Ch3 — yellow
    (180, 0, 200),    # Ch4 — magenta
    (160, 160, 160),  # Master — grey
    (120, 120, 120),  # Alt — darker grey
)

S_ACCENT = (200, 180, 40)
M_ACCENT = (180, 40, 40)
A_ACCENT = (60, 60, 160)

TOGGLE_OFF_OUTLINE = (80, 80, 80)
TOGGLE_OFF_TEXT = (80, 80, 80)
TOGGLE_ON_TEXT = (255, 255, 255)

_BADGE_TWEAK1 = BadgeGlyph("1")  # enc1 edits the selection — shown in the readout only

# ── formatters ─────────────────────────────────────────────────────────────────


def _coeff_to_db(coeff: float) -> str:
    if coeff <= 0.0:
        return "-inf"
    return f"{20.0 * math.log10(coeff):.1f}"


def _fmt_volume(coeff: float) -> tuple[str, str]:
    """DialFormatter for the arc rings; also feeds the readout dB strings."""
    return _coeff_to_db(coeff), "dB"


def _pan_str(value: float) -> str:
    if value < -0.01:
        return f"L {int(round(abs(value) * 100))}%"
    if value > 0.01:
        return f"R {int(round(value * 100))}%"
    return "C"


def _pan_label(value: float) -> str:
    """Compact form for the narrow under-bar label — no space, no percent."""
    if value < -0.01:
        return f"L{int(round(abs(value) * 100))}"
    if value > 0.01:
        return f"R{int(round(value * 100))}"
    return "C"


# ── state ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChannelState:
    volume: float = 0.75
    pan: float = 0.0
    solo: bool = False
    mute: bool = False
    alt: bool = False


@dataclass(frozen=True)
class MixerState:
    channels: tuple[ChannelState, ...]
    master_vol: float = 0.75
    alt_vol: float = 0.75


# ── column widgets ─────────────────────────────────────────────────────────────


class ColumnVolumeBar(Widget):
    """Vertical volume fader with a channel-coloured node and dB readout.
    TWEAK1 edits volume, TWEAK2 edits the channel's pan, LONG_CLICK resets."""

    def __init__(
        self,
        *,
        box: Box,
        panel: MixerPanel,
        channel: int,
        volume_sym: Symbol,
        pan_sym: Symbol,
        color: tuple[int, int, int],
        font,
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._panel = panel
        self.channel = channel
        self.volume_sym = volume_sym
        self.pan_sym = pan_sym
        self._color = color
        self._font = font
        self._value: float = 0.75

    def set_value(self, value: float) -> None:
        if value == self._value:
            return
        self._value = value
        self.refresh()

    def symbol_for(self, role: ParamRole) -> Symbol | None:
        if role == ParamRole.PAN:
            return self.pan_sym
        return self.volume_sym

    def input_event(self, event) -> bool:
        if event == InputEvent.LONG_CLICK:
            self._panel._reset_to_default(self.volume_sym)
            return True
        return False

    def _draw(self, ctx) -> None:
        cx = ctx.width // 2
        cx, node_y = paint_bar(
            ctx,
            box=Box(cx, 0, cx, VOL_TRACK_H),
            orientation="vertical",
            frac=max(0.0, min(1.0, self._value)),
            track_color=TRACK_COLOR,
            fill_color=FILL_ACTIVE,
            thickness=BAR_W,
        )
        paint_band_node(ctx, cx, node_y, self._color, self.selected)

        db_str = _coeff_to_db(self._value)
        tw, _ = get_text_size(db_str, self._font)
        ctx.draw_text((cx - tw // 2, VOL_DB_Y), db_str, fill=READOUT_COLOR, font=self._font)


class SmallToggle(Widget):
    """Rounded S/M/A toggle: outline-only when off, filled accent when on.
    CLICK flips the parameter, LONG_CLICK opens its dialog."""

    def __init__(
        self,
        *,
        box: Box,
        panel: MixerPanel,
        channel: int,
        symbol: Symbol,
        label: str,
        role_label: str,
        accent: tuple[int, int, int],
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        kwargs.setdefault("sel_radius", TOGGLE_RADIUS)
        super().__init__(box=box, **kwargs)
        self._panel = panel
        self.channel = channel
        self.symbol = symbol
        self.role_label = role_label
        self._label = label
        self._accent = accent
        self._value: bool = False

    def set_value(self, value: bool) -> None:
        if value == self._value:
            return
        self._value = value
        self.refresh()

    def symbol_for(self, role: ParamRole) -> Symbol | None:
        if role == ParamRole.GENERIC:
            return self.symbol
        return None

    def input_event(self, event) -> bool:
        p = self._panel.plugin.parameters.get(self.symbol)
        if p is None:
            return False
        if event == InputEvent.CLICK:
            self._panel.set_param(self.symbol, 0.0 if p.value > 0.5 else 1.0)
            return True
        if event == InputEvent.LONG_CLICK:
            self._panel.handler.open_parameter_dialog(p)
            return True
        return False

    def _draw(self, ctx) -> None:
        if self._value:
            glyph = ToggleGlyph(
                self._label, width=ctx.width, height=ctx.height, radius=TOGGLE_RADIUS,
                fill=self._accent, text_color=TOGGLE_ON_TEXT,
            )
        else:
            glyph = ToggleGlyph(
                self._label, width=ctx.width, height=ctx.height, radius=TOGGLE_RADIUS,
                fill=BG_BLACK, text_color=TOGGLE_OFF_TEXT, outline=TOGGLE_OFF_OUTLINE,
            )
        ctx.paste(glyph.render(), (0, 0))


class ColumnPanBar(Widget):
    """Thin pan bar with a white node and a compact position label below it.
    TWEAK1 edits pan, LONG_CLICK resets to centre."""

    def __init__(
        self,
        *,
        box: Box,
        panel: MixerPanel,
        channel: int,
        pan_sym: Symbol,
        font,
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._panel = panel
        self.channel = channel
        self.pan_sym = pan_sym
        self._font = font
        self._value: float = 0.0

    def set_value(self, value: float) -> None:
        if value == self._value:
            return
        self._value = value
        self.refresh()

    def symbol_for(self, role: ParamRole) -> Symbol | None:
        if role == ParamRole.GENERIC:
            return self.pan_sym
        return None

    def input_event(self, event) -> bool:
        if event == InputEvent.LONG_CLICK:
            self._panel._reset_to_default(self.pan_sym)
            return True
        return False

    def _draw(self, ctx) -> None:
        cx = ctx.width // 2
        _, node_y = paint_bar(
            ctx,
            box=Box(cx, 0, cx, PAN_TRACK_H),
            orientation="vertical",
            frac=(max(-1.0, min(1.0, self._value)) + 1.0) / 2.0,
            track_color=TRACK_COLOR,
            fill_color=TRACK_COLOR,
            thickness=BAR_W,
        )
        paint_band_node(ctx, cx, node_y, PAN_NODE_COLOR, self.selected)

        label = _pan_label(self._value)
        tw, _ = get_text_size(label, self._font)
        ctx.draw_text((cx - tw // 2, PAN_LABEL_Y), label, fill=READOUT_COLOR, font=self._font)


class MasterAltArcKnob(ArcKnobWidget):
    """Arc knob for Master/Alt volume. PAN role returns None so TWEAK2 is a no-op."""

    def symbol_for(self, role: ParamRole) -> Symbol | None:
        if role == ParamRole.PAN:
            return None
        return self.symbol


# ── MixerPanel ─────────────────────────────────────────────────────────────────


class MixerPanel(FullscreenPluginPanel[MixerState]):
    """Full-screen mixer with 4 channel columns + Master/Alt arc rings."""

    def __init__(self, **kwargs) -> None:
        self._vol_bars: list[ColumnVolumeBar] = []
        self._s_toggles: list[SmallToggle] = []
        self._m_toggles: list[SmallToggle] = []
        self._a_toggles: list[SmallToggle] = []
        self._pan_bars: list[ColumnPanBar] = []
        self._master_arc: Optional[MasterAltArcKnob] = None
        self._alt_arc: Optional[MasterAltArcKnob] = None
        self._readout: Optional[ReadoutBar] = None
        super().__init__(**kwargs)

    # ── PluginPanel contract ─────────────────────────────────────────────────

    def snapshot_state(self) -> MixerState:
        channels = tuple(
            ChannelState(
                volume=self._current(Symbol(f"Volume{n}"), 0.75),
                pan=self._current(Symbol(f"Panning{n}"), 0.0),
                solo=self._current(Symbol(f"Solo{n}")) > 0.5,
                mute=self._current(Symbol(f"Mute{n}")) > 0.5,
                alt=self._current(Symbol(f"Alt{n}")) > 0.5,
            )
            for n in range(1, 5)
        )
        return MixerState(
            channels=channels,
            master_vol=self._current(Symbol("MasterVolume"), 0.75),
            alt_vol=self._current(Symbol("AltVolume"), 0.75),
        )

    def apply_state(self, state: MixerState) -> None:
        for i, ch in enumerate(state.channels):
            self._vol_bars[i].set_value(ch.volume)
            self._pan_bars[i].set_value(ch.pan)
            self._s_toggles[i].set_value(ch.solo)
            self._m_toggles[i].set_value(ch.mute)
            self._a_toggles[i].set_value(ch.alt)
        if self._master_arc is not None:
            self._master_arc.set_value(state.master_vol)
        if self._alt_arc is not None:
            self._alt_arc.set_value(state.alt_vol)
        self._update_readout()

    def build_widgets(self) -> None:
        cfg = Config()
        self._tiny_font = cfg.get_font("tiny")

        self._readout = ReadoutBar(
            box=Box.xywh(0, 0, _W, READOUT_H),
            font=cfg.get_font("default"),
            parent=self,
        )

        for i in range(4):
            n = i + 1
            zone_x = i * CH_ZONE_W

            self._vol_bars.append(ColumnVolumeBar(
                box=Box.xywh(zone_x, BAR_Y0, VOL_COL_W, VOL_COL_H),
                panel=self,
                channel=n,
                volume_sym=Symbol(f"Volume{n}"),
                pan_sym=Symbol(f"Panning{n}"),
                color=CHANNEL_COLORS[i],
                font=self._tiny_font,
                parent=self,
            ))

            for j, (sym, label, role_label, accent) in enumerate((
                (Symbol(f"Solo{n}"), "S", "Solo", S_ACCENT),
                (Symbol(f"Mute{n}"), "M", "Mute", M_ACCENT),
                (Symbol(f"Alt{n}"), "A", "Alt", A_ACCENT),
            )):
                toggle = SmallToggle(
                    box=Box.xywh(zone_x + TOGGLE_X, TOGGLE_Y0 + j * TOGGLE_PITCH, TOGGLE_SIZE, TOGGLE_SIZE),
                    panel=self,
                    channel=n,
                    symbol=sym,
                    label=label,
                    role_label=role_label,
                    accent=accent,
                    parent=self,
                )
                (self._s_toggles, self._m_toggles, self._a_toggles)[j].append(toggle)

            self._pan_bars.append(ColumnPanBar(
                box=Box.xywh(zone_x + CTRL_CX - PAN_COL_W // 2, PAN_Y0, PAN_COL_W, PAN_COL_H),
                panel=self,
                channel=n,
                pan_sym=Symbol(f"Panning{n}"),
                font=self._tiny_font,
                parent=self,
            ))

        self._master_arc = MasterAltArcKnob(
            box=Box.xywh(ARC_X, MASTER_ARC_Y, ARC_W, ARC_H),
            symbol=Symbol("MasterVolume"),
            label="Master",
            color=CHANNEL_COLORS[4],
            minimum=0.0,
            maximum=1.0,
            formatter=_fmt_volume,
            panel=self,
            parent=self,
        )
        self._alt_arc = MasterAltArcKnob(
            box=Box.xywh(ARC_X, ALT_ARC_Y, ARC_W, ARC_H),
            symbol=Symbol("AltVolume"),
            label="Alt",
            color=CHANNEL_COLORS[5],
            minimum=0.0,
            maximum=1.0,
            formatter=_fmt_volume,
            panel=self,
            parent=self,
        )

        # NAV order: Ch1_Vol → Ch1_S → Ch1_M → Ch1_A → Ch1_Pan → Ch2… → Master → Alt.
        for i in range(4):
            self.add_sel_widget(self._vol_bars[i])
            self.add_sel_widget(self._s_toggles[i])
            self.add_sel_widget(self._m_toggles[i])
            self.add_sel_widget(self._a_toggles[i])
            self.add_sel_widget(self._pan_bars[i])
        self.add_sel_widget(self._master_arc)
        self.add_sel_widget(self._alt_arc)

        self.apply_state(self.snapshot_state())

    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        ctx = ContextRef(kind=ContextKind.PANEL, name="mixer")
        return (
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=1),
                event_kind=EventKind.ROTATE,
                effects=(SelectionEditEffect(role=ParamRole.GENERIC),),
                context=ctx,
            ),
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=2),
                event_kind=EventKind.ROTATE,
                effects=(SelectionEditEffect(role=ParamRole.PAN),),
                context=ctx,
            ),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _current(self, symbol: Symbol, default: float = 0.0) -> float:
        p = self.plugin.parameters.get(symbol)
        return float(p.value) if p is not None else default

    def _reset_to_default(self, symbol: Symbol) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is not None:
            self.set_param(symbol, p.default)

    # ── selection + readout ───────────────────────────────────────────────────

    def _select_widget_ref(self, w):
        super()._select_widget_ref(w)
        self._update_readout()

    def _update_readout(self) -> None:
        sel = self.sel_ref
        r = self._readout
        if r is None:
            return

        if isinstance(sel, ColumnVolumeBar):
            r.set_text(f"Ch {sel.channel}   {_coeff_to_db(self._current(sel.volume_sym))} dB")
            r.set_subtitle(f"Pan {_pan_str(self._current(sel.pan_sym))}")
            r.set_badge(_BADGE_TWEAK1)
        elif isinstance(sel, SmallToggle):
            r.set_text(f"{sel.role_label} Ch {sel.channel}")
            r.set_subtitle("on" if self._current(sel.symbol) > 0.5 else "off")
            r.set_badge(None)
        elif isinstance(sel, ColumnPanBar):
            r.set_text(f"Pan Ch {sel.channel}   {_pan_str(self._current(sel.pan_sym))}")
            r.set_subtitle("")
            r.set_badge(_BADGE_TWEAK1)
        elif isinstance(sel, MasterAltArcKnob):
            r.set_text(f"{sel._label}   {_coeff_to_db(self._current(sel.symbol))} dB")
            r.set_subtitle("")
            r.set_badge(_BADGE_TWEAK1)
        elif sel is self._btn_bypass:
            r.set_text("Plugin bypassed" if self.plugin.is_bypassed() else "Bypass plugin")
            r.set_subtitle("")
            r.set_badge(None)
        elif sel is self._btn_back:
            r.set_text("Close mixer")
            r.set_subtitle("")
            r.set_badge(None)
        elif sel is self._btn_reset:
            r.set_text("Reset to pedalboard")
            r.set_subtitle("")
            r.set_badge(None)
        else:
            r.set_text("")
            r.set_subtitle("")
            r.set_badge(None)

    # ── chrome ────────────────────────────────────────────────────────────────

    def _draw(self, ctx) -> None:
        for x in (56, 112, 168, 224):
            ctx.draw_rectangle(Box(x, CH_LABEL_Y, x + 1, BAR_Y1), fill=SEPARATOR_COLOR)
        for i in range(4):
            cx = i * CH_ZONE_W + CH_ZONE_W // 2
            label = f"CH{i + 1}"
            tw, _ = get_text_size(label, self._tiny_font)
            ctx.draw_text((cx - tw // 2, CH_LABEL_Y), label, fill=READOUT_COLOR, font=self._tiny_font)
