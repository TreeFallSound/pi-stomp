"""Audio & MIDI menu — the menu-idiom surface for the global EQ, input/output
levels, clock source, and VU calibration.

Composes the reactive ``PluginPanel`` core (via ``ModalDialog``) with a
synthetic ``AudioMidiParamSource`` (no backing ``Plugin``) so the EQ bands
and gain/volume reuse the same param/subscribe/step machinery as every
plugin panel. See ``docs/audio-midi-menu.md`` §5-6 for layout and the
declared-bindings table.

Layout (``DIMMED_WINDOW`` 304×208 body + title strip + Back footer):
- Left column: Input Gain + Output Volume arc dials (stacked).
- Right column: 5-band EQ bar curve (compact, sized to its box), then
  Clock Source and VU Calibration drill-in rows below it. The rows follow
  the menu system's padding (line-height spacing, h_margin=5, v_margin=1)
  so they read as-of-a-piece with the other menus.

No readout strip — this is a menu-idiom dialog, not a fullscreen panel;
the arcs and the EQ bars carry their own value readouts inline.

NAV reticule scans: Input → Output → Low → L-Mid → Mid → H-Mid → High →
Clock Source → VU Cal → Back. Tweak1 edits the selection; Tweak2 = Input
Gain; Tweak3/Vol = Output Volume (per §6). Clock Source opens a radio
submenu (Internal / Ableton Link / MIDI Clock Slave); VU Cal opens the
existing VU calibration dialog.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

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
from common.param_roles import ParamRole
from common.parameter import Parameter, Symbol
from modalapi.sync import SyncMode
from plugins.audio_midi.band_spec import BAND_SPECS
from plugins.audio_midi.source import AudioMidiParamSource
from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import (
    GraphicBandSelectable,
    GraphicBandParams,
    GraphicEqState,
    _fmt_freq,
)
from plugins.layouts.arc_knob import ArcKnobWidget
from plugins.modal_dialog import ModalDialog
from plugins.chrome import BTN_GAP, BTN_H
from uilib.arc_dial import DialVariant
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.badge import BadgeGlyph
from uilib.glyphs.bar import FILL_ACTIVE, FILL_INACTIVE, TRACK_COLOR, paint_bar
from uilib.glyphs.circle_handle import paint_circle_handle
from uilib.glyphs.pill import PillGlyph
from uilib.misc import INACTIVE_SHADE, InputEvent, get_text_size, shade_color
from uilib.rich_text import IconSeg, RichTextWidget, Segment, Spacer, TextSeg
from uilib.text import Button
from uilib.widget import Widget

if TYPE_CHECKING:
    from modalapi.modhandler import Modhandler

# ── layout (within the body, after footer) ───────────────────────────────────

_MARGIN = 4  # top/left/right inset for the arc column and the EQ top
_W = 244
_ARC_COL_W = 69  # left column for the two arc dials (dial_box_size r=26)
_ARC_COL_X = _MARGIN
_EQ_COL_X = _ARC_COL_X + _ARC_COL_W + _MARGIN
_EQ_COL_W = _W - _EQ_COL_X - _MARGIN
_ARC_RADIUS = 26
_ARC_H = 78
_ARC_GAP = 8  # extra spacing between the two arc-rings
_ARC_IN_Y = _MARGIN
_ARC_OUT_Y = _ARC_IN_Y + _ARC_H + _ARC_GAP
_EQ_Y = _MARGIN
_EQ_H = 112  # EQ bar widget height
_ROWS_Y = _EQ_Y + _EQ_H + 9  # 8px gap above the menu rows + the original 4, nudged up 3
_ROWS_X = _EQ_COL_X + 4  # indented 4px in from the EQ bar's left edge
_ROWS_W = _EQ_COL_W - 4  # four-px narrower than the EQ above it
_ROW_H = 24  # matches parameter_window's plugin-menu row height
_FREQ_LABEL_H = 11

_BADGE_TWEAK1 = BadgeGlyph("1")
_BADGE_TWEAK2 = BadgeGlyph("2")
_BADGE_TWEAK3 = BadgeGlyph("3")

_IN_COLOR = (120, 150, 255)
_OUT_COLOR = (255, 191, 63)
BG_BLACK = (0, 0, 0)
_BTN_MUTE_ACTIVE_COLOR = (140, 50, 0)  # matches pistomp/tuner/panel.py
FREQ_LABEL_COLOR = (110, 110, 110)
NODE_COLOR = (255, 255, 255)


def _fmt_vol(value: float) -> tuple[str, str]:
    return f"{value:+.1f}", "dB"


# ── state ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AudioMidiState:
    eq: GraphicEqState
    in_gain: float
    out_vol: float


# ── compact 5-band EQ bar widget ─────────────────────────────────────────────
#
# ``plugins.eq.graphic.BarWidget`` is hardcoded for the fullscreen 320×186
# geometry (BAR_Y0/Y1, COL_W, FREQ_LABEL_Y are module constants). Rather than
# parameterize it and risk the existing EQ panels, this is a compact fixed-5-band
# variant sized to its box — no scrolling, 0 dB line centred on the gain range.


class _CompactEqWidget(Widget):
    """5-band graphic EQ bars sized to the widget box. Each band gets an
    equal-width column; the 0 dB reference line, band nodes, and freq labels
    all derive from the box height so they fit any cell."""

    def __init__(self, box: Box, bands: tuple[GraphicBandSpec, ...], font, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._bands = bands
        self._font = font
        self._state: Optional[GraphicEqState] = None
        self._selected: Optional[str] = None

    def set_state(self, state: GraphicEqState) -> None:
        self._state = state
        self.refresh()

    def set_selected(self, name: Optional[str]) -> None:  # type: ignore[override]
        if name == self._selected:
            return
        self._selected = name
        self.refresh()

    def _draw_erase(self, ctx) -> None:
        pass

    def _draw(self, ctx) -> None:
        ctx.draw_rectangle(ctx.dirty_bounds, fill=BG_BLACK)
        if self._state is None:
            return
        n = len(self._bands)
        col_w = ctx.width // n
        label_h = _FREQ_LABEL_H
        bar_y0 = 2
        bar_y1 = ctx.height - label_h - 2
        bar_h = bar_y1 - bar_y0

        # 0 dB reference line — drawn first so the bars and nodes paint
        # over it. Faint grey; for the asymmetrical -10.5..+12 range, 0 dB
        # sits where (0 - gain_min)/span of the bar height.
        if self._bands:
            band0 = self._bands[0]
            span = band0.gain_max - band0.gain_min
            zero_frac = (0.0 - band0.gain_min) / span if span > 0 else 0.0
            zero_y = int(bar_y1 - zero_frac * bar_h)
            ctx.draw_line(
                [(0, zero_y), (ctx.width - 1, zero_y)],
                fill=(60, 60, 60),
                width=1,
            )

        for i, band in enumerate(self._bands):
            cx = i * col_w + col_w // 2
            p = self._state.bands.get(band.name)
            is_sel = band.name == self._selected
            span = band.gain_max - band.gain_min
            if p is None:
                frac = 0.0
            else:
                gain = p.gain_db if p.enabled else band.gain_min
                frac = 0.0 if span <= 0 else (gain - band.gain_min) / span
            fill_color = FILL_ACTIVE if is_sel else FILL_INACTIVE
            bar_x = cx - 1  # 3px-wide bar
            _, gain_y = paint_bar(
                ctx,
                box=Box(bar_x, bar_y0, bar_x + 3, bar_y1),
                orientation="vertical",
                frac=frac,
                track_color=TRACK_COLOR,
                fill_color=fill_color,
                thickness=3,
            )
            if p is not None:
                node_color = shade_color(band.color, 1.0)
                paint_circle_handle(ctx, cx, gain_y, node_color, is_sel)
            # freq label below bars
            if self._font is not None:
                label = _fmt_freq(band.freq_hz)
                tw, _ = get_text_size(label, self._font)
                ctx.draw_text((cx - tw // 2, bar_y1 + 1), label, fill=FREQ_LABEL_COLOR, font=self._font)


# ── discrete row selectables ─────────────────────────────────────────────────


class _DiscreteRow(RichTextWidget):
    """A drill-in row (Clock Source / VU Calibration). ``symbol_for`` returns
    None so ``SelectionEditEffect`` no-ops on it — the row is NAV-click-only,
    opening a submenu/dialog rather than editing a continuous value."""

    def __init__(self, *, box: Box, segments: list[Segment], action: Callable[[InputEvent], bool], font, parent: Widget) -> None:
        super().__init__(box=box, segments=segments, font=font, h_margin=5, v_margin=1, parent=parent, action=action)
        self._discrete_action = action

    def symbol_for(self, role: ParamRole) -> Symbol | None:  # noqa: ARG002
        return None

    def input_event(self, event) -> bool:  # type: ignore[override]
        return self._discrete_action(event)


# ── the panel ────────────────────────────────────────────────────────────────


class AudioMidiPanel(ModalDialog[AudioMidiState]):
    """The Audio & MIDI menu surface (§5-7 of audio-midi-menu.md)."""

    WIN_W = 244  # ~80% of the 304 plugin-window width — menu-idiom, not full-bleed
    WIN_H = 208

    def footer_buttons(self, btn_y: int, btn_v_margin: int) -> tuple[Button, ...]:
        w = self._win_w
        btn_w = (w - 4 * BTN_GAP) // 3

        def _btn(text: str, x: int, action: Callable[..., None]) -> Button:
            return Button(
                box=Box.xywh(x, btn_y, btn_w, BTN_H),
                text=text,
                font=self._btn_font,
                v_margin=btn_v_margin,
                outline_radius=4,
                parent=self,
                action=action,
            )

        mute_btn = _btn("Mute", BTN_GAP * 2 + btn_w, lambda *_: self._on_toggle_mute())
        self._mute_btn = mute_btn
        self._apply_mute_style()
        return (
            _btn("Back", BTN_GAP, lambda *_: self._on_dismiss()),
            mute_btn,
            _btn("Restart", BTN_GAP * 3 + btn_w * 2, lambda *_: self._on_restart()),
        )

    def title_text(self) -> str:
        sync = self._handler.sync_mode if hasattr(self, "_handler") else SyncMode.INTERNAL
        suffix = "LINK" if sync is SyncMode.LINK else ("MIDI" if sync is SyncMode.MIDI_CLOCK_SLAVE else "")
        return "Audio & MIDI" + (f" · {suffix}" if suffix else "")

    def scheme(self):
        return None  # default dialog scheme — menu-idiom, not plugin-coloured

    def __init__(self, *, handler: "Modhandler", on_dismiss: Callable[[], None]) -> None:
        self._handler: Modhandler = handler
        self._sync_row: Optional[_DiscreteRow] = None
        self._vu_row: Optional[_DiscreteRow] = None
        self._bar_widget: Optional[_CompactEqWidget] = None
        self._in_arc: Optional[ArcKnobWidget] = None
        self._out_arc: Optional[ArcKnobWidget] = None
        self._mute_btn: Optional[Button] = None
        self._band_sels: dict[str, GraphicBandSelectable] = {}
        self._readout = None  # no readout strip on a menu-idiom dialog
        source = AudioMidiParamSource(handler.audiocard, handler.hardware)
        self._has_eq = handler.audiocard.DAC_EQ is not None and bool(source.parameters)
        super().__init__(
            plugin=source,  # type: ignore[arg-type]  # ParamSource, not Plugin
            handler=handler,
            on_dismiss=on_dismiss,
            badge_fn=None,
        )
        self._build_rows()
        self._select_initial()

    # ── PluginPanel behaviour contract ─────────────────────────────────────

    def snapshot_state(self) -> AudioMidiState:
        params = self.plugin.parameters
        bands: dict[str, GraphicBandParams] = {}
        if self._has_eq:
            for band in BAND_SPECS:
                p = params.get(band.gain_sym)
                gain = float(p.value) if p is not None else 0.0
                bands[band.name] = GraphicBandParams(enabled=True, gain_db=gain)
        ac = self._handler.audiocard
        in_sym = Symbol(ac.CAPTURE_VOLUME) if ac.CAPTURE_VOLUME is not None else None
        out_sym = Symbol(ac.MASTER) if ac.MASTER is not None else None
        return AudioMidiState(
            eq=GraphicEqState(plugin_enabled=True, bands=bands),
            in_gain=float(params[in_sym].value) if in_sym is not None and in_sym in params else 0.0,
            out_vol=float(params[out_sym].value) if out_sym is not None and out_sym in params else 0.0,
        )

    def apply_state(self, state: AudioMidiState) -> None:
        self._state = state
        if self._bar_widget is not None:
            self._bar_widget.set_state(state.eq)
        if self._in_arc is not None:
            self._in_arc.set_value(state.in_gain)
        if self._out_arc is not None:
            self._out_arc.set_value(state.out_vol)

    def build_widgets(self) -> None:
        cfg = Config()
        self._tiny_font = cfg.get_font("tiny")
        self._row_font = cfg.get_font("default")

        cb = self.content_box
        ac = self._handler.audiocard

        # Left column: arc dials (4px margin on top/left/right).
        in_sym = Symbol(ac.CAPTURE_VOLUME) if ac.CAPTURE_VOLUME is not None else None
        out_sym = Symbol(ac.MASTER) if ac.MASTER is not None else None
        if in_sym is not None:
            self._in_arc = ArcKnobWidget(
                box=Box.xywh(cb.x0 + _ARC_COL_X, cb.y0 + _ARC_IN_Y, _ARC_COL_W, _ARC_H),
                symbol=in_sym,
                label="IN",
                color=_IN_COLOR,
                minimum=-19.75,
                maximum=12.0,
                formatter=_fmt_vol,
                radius=_ARC_RADIUS,
                panel=self,
                parent=self,
                variant=DialVariant.MEDIUM,
            )
            self._in_arc.set_value(self.snapshot_state().in_gain)
            self._in_arc.set_badge(_BADGE_TWEAK2)
        if out_sym is not None:
            self._out_arc = ArcKnobWidget(
                box=Box.xywh(cb.x0 + _ARC_COL_X, cb.y0 + _ARC_OUT_Y, _ARC_COL_W, _ARC_H),
                symbol=out_sym,
                label="OUT",
                color=_OUT_COLOR,
                minimum=-25.75,
                maximum=6.0,
                formatter=_fmt_vol,
                radius=_ARC_RADIUS,
                panel=self,
                parent=self,
                variant=DialVariant.MEDIUM,
            )
            self._out_arc.set_value(self.snapshot_state().out_vol)
            self._out_arc.set_badge(_BADGE_TWEAK3)

        # Right column: EQ bars (4px top margin).
        if self._has_eq:
            self._bar_widget = _CompactEqWidget(
                box=Box.xywh(cb.x0 + _EQ_COL_X, cb.y0 + _EQ_Y, _EQ_COL_W, _EQ_H),
                bands=BAND_SPECS,
                font=self._tiny_font,
                parent=self,
            )
            self._bar_widget.set_state(self.snapshot_state().eq)

        self.apply_state(self.snapshot_state())

    def _build_rows(self) -> None:
        cb = self.content_box
        y = cb.y0 + _ROWS_Y
        sync_segs = self._sync_row_segments()
        self._sync_row = _DiscreteRow(
            box=Box.xywh(cb.x0 + _ROWS_X, y, _ROWS_W, _ROW_H),
            segments=sync_segs,
            action=self._on_sync_row,
            font=self._row_font,
            parent=self,
        )
        y += _ROW_H
        vu_segs: list[Segment] = [TextSeg("VU Calibration"), Spacer(), TextSeg("▸")]
        self._vu_row = _DiscreteRow(
            box=Box.xywh(cb.x0 + _ROWS_X, y, _ROWS_W, _ROW_H),
            segments=vu_segs,
            action=self._on_vu_row,
            font=self._row_font,
            parent=self,
        )

    def _sync_row_segments(self) -> list[Segment]:
        from uilib.glyphs import DEFAULT_COLOR
        mode = self._handler.sync_mode
        label = "INT" if mode is SyncMode.INTERNAL else ("LINK" if mode is SyncMode.LINK else "MIDI")
        glyph_h = 12
        return [TextSeg("Clock Source"), Spacer(), IconSeg(PillGlyph(label, height=glyph_h, color=DEFAULT_COLOR)), TextSeg(" ▸")]

    def _select_initial(self) -> None:
        # NAV order per §6: Input arc → Output arc → EQ bands (Low..High) →
        # Clock Source → VU Cal → Back. Visual layout (arcs left, EQ right) is
        # independent of the selection cycle order.
        if self._in_arc is not None:
            self.add_sel_widget(self._in_arc)
        if self._out_arc is not None:
            self.add_sel_widget(self._out_arc)
        if self._has_eq:
            for band in BAND_SPECS:
                sel = GraphicBandSelectable(self, band)  # type: ignore[arg-type]
                self._band_sels[band.name] = sel
                self.add_sel_widget(sel)
        if self._sync_row is not None:
            self.add_sel_widget(self._sync_row)
        if self._vu_row is not None:
            self.add_sel_widget(self._vu_row)
        first = self._in_arc if self._in_arc is not None else (
            self._band_sels.get(BAND_SPECS[0].name) if self._has_eq else self._out_arc
        )
        if first is not None:
            self.sel_widget(first)

    # ── declared bindings (§6) ──────────────────────────────────────────────

    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        ctx = ContextRef(kind=ContextKind.PANEL, name="audio_midi")
        ac = self._handler.audiocard
        in_sym = Symbol(ac.CAPTURE_VOLUME) if ac.CAPTURE_VOLUME is not None else None
        out_sym = Symbol(ac.MASTER) if ac.MASTER is not None else None
        rows: list[BindingDecl] = [
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=1),
                event_kind=EventKind.ROTATE,
                effects=(SelectionEditEffect(role=ParamRole.GENERIC),),
                context=ctx,
            ),
        ]
        if in_sym is not None:
            rows.append(BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=2),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=self.plugin, symbol=in_sym),),
                context=ctx,
            ))
        if out_sym is not None:
            rows.append(BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=3),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=self.plugin, symbol=out_sym),),
                context=ctx,
            ))
        return tuple(rows)

    # ── no mod-host echo to send; the synthetic source already wrote the card ──

    def _send_param(self, instance_id: str, symbol: Symbol, value: float) -> None:
        pass

    # ── selection ─────────────────────────────────────────────────────────────

    def _select_widget_ref(self, w):  # type: ignore[override]
        super()._select_widget_ref(w)
        if self._bar_widget is not None:
            if isinstance(w, GraphicBandSelectable):
                self._bar_widget.set_selected(w.band.name)
            else:
                self._bar_widget.set_selected(None)

    # ── drill-in actions ─────────────────────────────────────────────────────

    def _on_sync_row(self, event: InputEvent) -> bool:
        if event != InputEvent.CLICK:
            return False
        self._open_clock_source_submenu()
        return True

    def _on_vu_row(self, event: InputEvent) -> bool:
        if event != InputEvent.CLICK:
            return False
        self._handler.system_menu_vu_calibration(None)
        return True

    def _open_clock_source_submenu(self) -> None:
        current = self._handler.sync_mode
        items = [
            ("Internal", self._set_sync, SyncMode.INTERNAL, current is SyncMode.INTERNAL),
            ("Ableton Link", self._set_sync, SyncMode.LINK, current is SyncMode.LINK),
            ("MIDI Clock Slave", self._set_sync, SyncMode.MIDI_CLOCK_SLAVE, current is SyncMode.MIDI_CLOCK_SLAVE),
        ]
        self._handler.lcd.draw_selection_menu(items, "Clock Source", auto_dismiss=True)

    def _set_sync(self, mode: SyncMode) -> None:
        self._handler.set_sync_mode(mode)

    # ── NAV-click on a band opens its gain dialog ─────────────────────────────

    def open_selection_dialog(self, parameter: Parameter) -> bool:
        def _commit(symbol: str, value: float) -> None:
            self.plugin.set_param_value(Symbol(symbol), value)
        self._handler.open_audio_parameter_dialog(parameter, _commit)
        return True

    # ── live sync-mode repaint hook (called by Lcd.update_sync_mode) ──────────

    def on_sync_mode_changed(self, mode: SyncMode) -> None:
        if self._sync_row is None:
            return
        self._sync_row.segments = self._sync_row_segments()
        self._sync_row.refresh()

    # ── EQ-band reset (LONG_CLICK on a band) ──────────────────────────────────

    def _reset_band_gain(self, band: GraphicBandSpec) -> None:
        p = self._state.eq.bands.get(band.name)
        if p is None or p.gain_db == 0.0:
            return
        self.set_param(band.gain_sym, 0.0)

    def _refresh_bypass_style(self) -> None:
        pass  # no bypass button

    # ── footer actions ──────────────────────────────────────────────────────

    def _apply_mute_style(self) -> None:
        # Tuner-style: label stays "Mute"; the background flags the state.
        if self._mute_btn is None:
            return
        jm = self._handler.jack_mute
        muted = jm is not None and jm.is_muted()
        self._mute_btn.set_background(_BTN_MUTE_ACTIVE_COLOR if muted else (0, 0, 0))

    def _on_toggle_mute(self) -> None:
        jm = self._handler.jack_mute
        if jm is None:
            return
        if jm.is_muted():
            jm.unmute()
        else:
            jm.mute()
        self._apply_mute_style()
        if self._mute_btn is not None:
            self._mute_btn.refresh()
        # Keep the home-screen tile in sync — the panel covers the tile while
        # open, but the next dismiss must show the post-toggle state.
        self._handler.lcd.update_audio_midi_tile()

    def _on_restart(self) -> None:
        # Mirrors handler.system_menu_restart_sound — restarts jack (which
        # cascades to mod-host/mod-ui). The splash covers the teardown.
        self._handler.system_menu_restart_sound(None)

    def wants_fast_tick(self) -> bool:
        return True