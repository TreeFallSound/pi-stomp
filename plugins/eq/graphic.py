"""Graphic EQ panel — vertical bar visualization.

``GraphicEqPanel`` is the abstract base; subclasses provide band specs via
``build_band_specs()``. ``BarWidget`` renders a 4 px wide track + fill bar
per band, centered in equal-width columns, with a coloured selection handle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from plugins.fullscreen import FullscreenPluginPanel
from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.parametric import paint_band_node, _fmt_freq as _fmt_freq_long
from uilib.box import Box
from uilib.config import Config
from uilib.misc import INACTIVE_SHADE, InputEvent, get_text_size
from uilib.widget import Widget

# ── layout constants ────────────────────────────────────────────────────────

_W = 320
_H = 240

VISIBLE_BANDS  = 10
COL_W          = _W // VISIBLE_BANDS   # 32 px per column
BAR_W          = 3                      # track + fill width (matches node diameter)

READOUT_H      = 22
FREQ_LABEL_H   = 14
BAR_Y0         = 6                      # bars start 6px from widget top (halo clearance from readout)
BAR_Y1         = 164                    # bar area ends 8px before freq labels (halo clearance)
BAR_H          = BAR_Y1 - BAR_Y0      # 158
FREQ_LABEL_Y   = BAR_Y1 + 8            # 172 — 6px halo + 2px padding below bars
WIDGET_H       = FREQ_LABEL_Y + FREQ_LABEL_H  # 186 — includes freq labels

# ── colours ──────────────────────────────────────────────────────────────────

BG_BLACK        = (0, 0, 0)
TRACK_COLOR     = (40, 40, 40)
FILL_INACTIVE   = (160, 160, 160)
FILL_ACTIVE     = (240, 240, 240)
READOUT_COLOR   = (200, 200, 200)
FREQ_LABEL_COLOR = (110, 110, 110)


# ── label helpers ────────────────────────────────────────────────────────────


def _fmt_freq(hz: float) -> str:
    """Format a frequency as ≤3 chars."""
    if hz >= 10_000:
        return f"{int(round(hz / 1000))}k"
    if hz >= 1_000:
        v = hz / 1000.0
        return f"{v:.3g}k"
    return f"{int(round(hz))}"


def _fmt_db(db: float) -> str:
    """Format a dB value as ≤3 chars (e.g. +6, -12, 0)."""
    v = int(round(db))
    if v == 0:
        return "0"
    return f"{v:+d}"


# ── coordinate helper ────────────────────────────────────────────────────────


def _gain_to_y(gain: float, band: GraphicBandSpec) -> int:
    """Map gain_db to a pixel row; gain_min → BAR_Y1 (bottom), gain_max → BAR_Y0 (top)."""
    span = band.gain_max - band.gain_min
    if span <= 0:
        return BAR_Y1
    norm = (gain - band.gain_min) / span
    norm = max(0.0, min(1.0, norm))
    return int(BAR_Y1 - norm * BAR_H)


# ── palette helper ──────────────────────────────────────────────────────────


def _graphic_palette(n: int) -> list[tuple[int, int, int]]:
    """Generate *n* RGB colours sweeping hue 0°→300°."""
    import colorsys

    out: list[tuple[int, int, int]] = []
    for i in range(n):
        hue = (i / max(n - 1, 1)) * 300.0 / 360.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
        out.append((int(r * 255), int(g * 255), int(b * 255)))
    return out


# ── BarWidget ────────────────────────────────────────────────────────────────


class BarWidget(Widget):
    """3 px-wide track+fill bars for graphic EQs, 10 bands visible at once.

    Each column is COL_W pixels wide. The track and fill bar are BAR_W=3 px,
    centred in the column. A coloured handle sits at the fill's top edge for
    the selected band. Bands scroll horizontally as selection moves.
    """

    def __init__(
        self,
        box: Box,
        bands: Sequence[GraphicBandSpec],
        font,
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._bands = bands
        self._font = font
        self._state: Optional[GraphicEqState] = None
        self._selected_band: Optional[str] = None
        self._bypassed: bool = False
        self._first_visible: int = 0

    @property
    def first_visible(self) -> int:
        return self._first_visible

    def set_first_visible(self, n: int) -> None:
        n = max(0, min(n, max(0, len(self._bands) - VISIBLE_BANDS)))
        if n != self._first_visible:
            self._first_visible = n
            self.refresh()

    def set_state(self, state: GraphicEqState) -> None:
        self._state = state
        self.refresh()

    def set_selected(self, band_name: Optional[str]) -> None:  # type: ignore[override]
        if band_name == self._selected_band:
            return
        self._selected_band = band_name
        self.refresh()

    def set_bypassed(self, bypassed: bool) -> None:
        if self._bypassed == bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    # ── paint ───────────────────────────────────────────────────────────────

    def _draw_erase(self, ctx) -> None:
        pass

    def _draw(self, ctx) -> None:
        ctx.draw_rectangle(ctx.dirty_bounds, fill=BG_BLACK)

        if self._state is None:
            return

        shade = INACTIVE_SHADE if self._bypassed else 1.0
        fv = self._first_visible
        visible = self._bands[fv : fv + VISIBLE_BANDS]

        # 0 dB reference line — faint grey across full width
        zero_y = _gain_to_y(0.0, visible[0]) if visible else BAR_Y0
        ctx.draw_line(
            [(ctx.dirty_bounds.x0, zero_y), (ctx.dirty_bounds.x1 - 1, zero_y)],
            fill=(60, 60, 60),
            width=1,
        )

        for col, band in enumerate(visible):
            cx = col * COL_W + COL_W // 2
            bar_x = cx - BAR_W // 2

            # Track — full height
            ctx.draw_rectangle(Box(bar_x, BAR_Y0, bar_x + BAR_W, BAR_Y1), fill=TRACK_COLOR)

            p = self._state.bands.get(band.name)
            if p is None:
                continue

            gain = p.gain_db if p.enabled else band.gain_min
            gain_y = _gain_to_y(gain, band)

            is_sel = band.name == self._selected_band

            fill_color: tuple[int, int, int] = FILL_ACTIVE if is_sel else FILL_INACTIVE
            if shade < 1.0:
                fill_color = tuple(int(c * shade) for c in fill_color)  # type: ignore[assignment]

            # Fill — bottom to gain position
            if gain_y < BAR_Y1:
                ctx.draw_rectangle(Box(bar_x, gain_y, bar_x + BAR_W, BAR_Y1), fill=fill_color)

            # Node — same circle style as parametric EQ
            node_color: tuple[int, int, int] = band.color
            if shade < 1.0:
                node_color = tuple(int(c * shade) for c in node_color)  # type: ignore[assignment]
            paint_band_node(ctx, cx, gain_y, node_color, is_sel)

            # Frequency label — below bars, above chrome
            if self._font is not None:
                label = _fmt_freq(band.freq_hz)
                tw, th = get_text_size(label, self._font)
                tx = cx - tw // 2
                ctx.draw_text((tx, FREQ_LABEL_Y), label, fill=FREQ_LABEL_COLOR, font=self._font)


# ── ReadoutWidget ────────────────────────────────────────────────────────────


class GraphicReadoutWidget(Widget):
    """Top-bar with band-number / frequency / dB, left/center/right aligned."""

    def __init__(self, box: Box, font, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._font = font
        self._band_idx: int = 0
        self._band_total: int = 0
        self._freq: str = ""
        self._gain: str = ""
        self._message: Optional[str] = None

    def set_fields(self, band_idx: int, band_total: int, freq: str, gain: str) -> None:
        if self._message is None and band_idx == self._band_idx and band_total == self._band_total and freq == self._freq and gain == self._gain:
            return
        self._band_idx = band_idx
        self._band_total = band_total
        self._freq = freq
        self._gain = gain
        self._message = None
        self.refresh()

    def set_message(self, text: str) -> None:
        if self._message == text:
            return
        self._message = text
        self.refresh()

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.bounds, fill=BG_BLACK)

    def _draw(self, ctx) -> None:
        if self._message is not None:
            ctx.draw_text((6, 1), self._message, fill=READOUT_COLOR, font=self._font)
            return
        # Left: band number
        band_str = f"Band {self._band_idx + 1}/{self._band_total}"
        ctx.draw_text((6, 1), band_str, fill=READOUT_COLOR, font=self._font)
        # Center: frequency
        if self._freq:
            tw, _ = get_text_size(self._freq, self._font)
            ctx.draw_text((_W // 2 - tw // 2, 1), self._freq, fill=READOUT_COLOR, font=self._font)
        # Right: gain
        if self._gain:
            tw, _ = get_text_size(self._gain, self._font)
            ctx.draw_text((_W - 6 - tw, 1), self._gain, fill=READOUT_COLOR, font=self._font)


# ── GraphicEqState ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GraphicBandParams:
    enabled: bool
    gain_db: float = 0.0


@dataclass(frozen=True)
class GraphicEqState:
    """State for graphic EQ panels — gain per band."""

    plugin_enabled: bool
    bands: dict[str, GraphicBandParams]  # keyed by GraphicBandSpec.name


# ── GraphicBandSelectable ────────────────────────────────────────────────────


class GraphicBandSelectable(Widget):
    """Nav-cycle target for graphic EQ bands.

    CLICK is a no-op (returns False so the event falls through).
    LONG_CLICK resets the band to the pedalboard snapshot.
    """

    def __init__(self, panel: GraphicEqPanel, band: GraphicBandSpec) -> None:
        super().__init__(box=Box.xywh(0, 0, 1, 1), parent=panel, visible=True)
        self._panel: GraphicEqPanel = panel
        self.band = band

    def set_selected(self, selected: bool) -> None:  # type: ignore[override]
        self.selected = selected

    def input_event(self, event) -> bool:  # type: ignore[override]
        if event == InputEvent.CLICK:
            self._panel._reset_band_gain(self.band)
            return True
        if event == InputEvent.LONG_CLICK:
            self._panel._reset_band_to_snapshot(self.band)
            return True
        return False

    def scroll_into_view(self) -> bool:
        return False

    def _draw(self, ctx) -> None:
        pass

    def _draw_erase(self, ctx) -> None:
        pass

    def _draw_selection(self, ctx) -> None:
        pass


# ── GraphicEqPanel (ABC) ─────────────────────────────────────────────────────


class GraphicEqPanel(FullscreenPluginPanel[GraphicEqState]):
    """Abstract base for graphic EQ panels.

    Subclasses provide ``build_band_specs()`` returning the list of
    ``GraphicBandSpec`` for this plugin.
    """

    # ── subclass contract ──────────────────────────────────────────────────

    def build_band_specs(self) -> Sequence[GraphicBandSpec]:
        raise NotImplementedError

    # ── PluginPanel subclass contract ────────────────────────────────────────

    def snapshot_state(self) -> GraphicEqState:
        params = self.plugin.parameters

        def _val(symbol: str, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None and p.value is not None else default

        bands: dict[str, GraphicBandParams] = {}
        for band in self.bands:
            bands[band.name] = GraphicBandParams(
                enabled=True,
                gain_db=_val(band.gain_sym, 0.0),
            )
        return GraphicEqState(
            plugin_enabled=bool(_val("enable", 1.0)),
            bands=bands,
        )

    def apply_state(self, state: GraphicEqState) -> None:
        self._state = state
        self._bar_widget.set_state(state)
        self._update_readout()

    def build_widgets(self) -> None:
        self.bands = self.build_band_specs()
        self._state = self.snapshot_state()
        cfg = Config()
        font = cfg.get_font("tiny") or cfg.get_font("default")
        btn_font = cfg.get_font("default")

        self._readout = GraphicReadoutWidget(
            box=Box.xywh(0, 0, _W, READOUT_H),
            font=btn_font,
            parent=self,
        )
        self._bar_widget = BarWidget(
            box=Box.xywh(0, READOUT_H, _W, WIDGET_H),
            bands=self.bands,
            font=font,
            parent=self,
        )

        self._band_sels: dict[str, GraphicBandSelectable] = {}
        for band in self.bands:
            sel = GraphicBandSelectable(self, band)
            self._band_sels[band.name] = sel
            self.add_sel_widget(sel)

        self._bar_widget.set_bypassed(self.plugin.is_bypassed())
        self.apply_state(self.snapshot_state())
        self.sel_widget(self._band_sels[self.bands[0].name])

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id not in (1, 2, 3) or rotations == 0:
            return False
        band = self.selected_band
        if band is None:
            return encoder_id != 3
        delta = rotations
        p = self._state.bands[band.name]
        if encoder_id == 1:
            new_gain = max(band.gain_min, min(band.gain_max, p.gain_db + delta * 0.5))
            if new_gain == p.gain_db:
                return True
            self.set_param(band.gain_sym, new_gain)
            self._replace_band(band, gain_db=new_gain)
            return True
        elif encoder_id in (2, 3):
            return True  # consume but no-op
        return False

    def tick(self) -> None:
        bypassed = self.plugin.is_bypassed()
        if bypassed != getattr(self, "_last_bypassed", None):
            self._last_bypassed = bypassed
            self._bar_widget.set_bypassed(bypassed)
            self._update_readout()
        super().tick()

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        self._bar_widget.set_bypassed(self.plugin.is_bypassed())
        self._update_readout()

    # ── state helpers ───────────────────────────────────────────────────────

    @property
    def selected_band(self) -> Optional[GraphicBandSpec]:
        if self.sel_ref is None:
            return None
        w = self.sel_ref
        return w.band if isinstance(w, GraphicBandSelectable) else None

    def _replace_band(self, band: GraphicBandSpec, **changes) -> None:
        old = self._state.bands[band.name]
        new = type(old)(**{**old.__dict__, **changes})
        new_bands = dict(self._state.bands)
        new_bands[band.name] = new
        self._state = type(self._state)(
            plugin_enabled=self._state.plugin_enabled,
            bands=new_bands,
        )
        self._bar_widget.set_state(self._state)
        self._update_readout()

    def _update_readout(self) -> None:
        sel_w = self.sel_ref
        if isinstance(sel_w, GraphicBandSelectable):
            p = self._state.bands.get(sel_w.band.name)
            if p is None:
                self._readout.set_message("")
            else:
                idx = next((i for i, b in enumerate(self.bands) if b.name == sel_w.band.name), 0)
                freq = _fmt_freq_long(sel_w.band.freq_hz)
                if not p.enabled:
                    gain = "disabled"
                else:
                    gain = f"{p.gain_db:+.1f} dB"
                self._readout.set_fields(idx, len(self.bands), freq, gain)
        elif sel_w is self._btn_bypass:
            self._readout.set_message("Plugin bypassed" if self.plugin.is_bypassed() else "Bypass plugin")
        elif sel_w is self._btn_back:
            self._readout.set_message("Close EQ")
        elif sel_w is self._btn_reset:
            self._readout.set_message("Reset to pedalboard")
        else:
            self._readout.set_message("")

    def _select_widget_ref(self, w):  # type: ignore[override]
        super()._select_widget_ref(w)
        if isinstance(w, GraphicBandSelectable):
            band_name = w.band.name
            self._bar_widget.set_selected(band_name)
            # Scroll to keep selected band in view
            idx = next((i for i, b in enumerate(self.bands) if b.name == band_name), 0)
            fv = self._bar_widget.first_visible
            if idx < fv:
                self._bar_widget.set_first_visible(idx)
            elif idx >= fv + VISIBLE_BANDS:
                self._bar_widget.set_first_visible(idx - VISIBLE_BANDS + 1)
        else:
            self._bar_widget.set_selected(None)
        self._update_readout()

    # ── band-selectable callbacks ───────────────────────────────────────────

    def _reset_band_gain(self, band: GraphicBandSpec) -> None:
        """Reset the band's gain to 0 dB."""
        p = self._state.bands.get(band.name)
        if p is None or p.gain_db == 0.0:
            return
        self.set_param(band.gain_sym, 0.0)
        self._replace_band(band, gain_db=0.0)

    def _reset_band_to_snapshot(self, band: GraphicBandSpec) -> None:
        snap = self.plugin.pedalboard_snapshot
        if band.gain_sym in snap and not self._is_symbol_locked(self.plugin.instance_id, band.gain_sym):
            self.set_param(band.gain_sym, snap[band.gain_sym])
        self.apply_state(self.snapshot_state())
