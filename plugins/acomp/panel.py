"""DISTRHO a-comp: a windowed compressor panel with a live gain-reduction meter.

Left: a vertical column of arc-ring controls (threshold, ratio, knee, makeup).
Right: the compression transfer curve plus a live GR bar driven by a JACK
subprocess (``pistomp.compmeter``) that taps the compressor's in/out audio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from modalapi.plugin import Plugin
from pistomp.compmeter.client import GrMeterClient
from plugins.multiband_menu import ParamSlot, ParamSlotWidget
from plugins.window import PluginWindow
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.arc_ring import ArcRingGlyph
from uilib.misc import get_text_size
from uilib.widget import Widget

# LV2 port symbols (see docs/lv2-ttl-guide.md finder).
_THR = "thr"  # threshold dB (-60..0)
_RAT = "rat"  # ratio (1..20)
_KN = "kn"  # knee dB (0..8)
_MAK = "mak"  # makeup dB (0..30)

# Column arcs, top to bottom.
_SLOTS = (
    ParamSlot(_THR, "Thr", (255, 180, 80), display_fn=lambda v: f"{v:+.0f}"),
    ParamSlot(_RAT, "Ratio", (130, 220, 110), display_fn=lambda v: f"{v:.1f}:1"),
    ParamSlot(_KN, "Knee", (110, 200, 230), display_fn=lambda v: f"{v:.0f}"),
    ParamSlot(_MAK, "Makeup", (210, 130, 230), display_fn=lambda v: f"+{v:.0f}"),
)

_COL_W = 96  # left arc column width
_ARC_RADIUS = 16  # small rings so four stack in the column
_GR_MAX_DB = 24.0  # full-scale of the GR bar / curve headroom


@dataclass(frozen=True)
class AcompState:
    thr: float
    rat: float
    kn: float
    mak: float


def _comp_output_db(x_db: float, thr: float, ratio: float, knee: float, makeup: float) -> float:
    """Soft-knee downward-compressor transfer function (DAFX), plus makeup."""
    if ratio <= 0:
        ratio = 1.0
    over = x_db - thr
    if knee > 0.0 and 2.0 * over < -knee:
        y = x_db
    elif knee > 0.0 and 2.0 * abs(over) <= knee:
        y = x_db + (1.0 / ratio - 1.0) * (over + knee / 2.0) ** 2 / (2.0 * knee)
    else:
        y = thr + over / ratio
    return y + makeup


class AcompWindow(PluginWindow[AcompState]):
    """Compressor window: arc column + transfer curve + live GR meter."""

    WIN_W = 316
    WIN_H = 236

    def build_widgets(self) -> None:
        cfg = Config()
        value_font = cfg.get_font("small") or cfg.get_font("default")
        label_font = cfg.get_font("tiny") or value_font
        assert value_font is not None and label_font is not None

        cb = self.content_box
        self._ring = ArcRingGlyph(radius=_ARC_RADIUS)
        ring_wh = self._ring.size + 4

        # Left column: one arc slot per parameter, evenly stacked.
        n = len(_SLOTS)
        cell_h = cb.height // n
        col_cx = cb.x0 + _COL_W // 2
        self._slots: list[ParamSlotWidget] = []
        for i, slot in enumerate(_SLOTS):
            cy = cb.y0 + i * cell_h + cell_h // 2
            box = Box.xywh(col_cx - ring_wh // 2, cy - ring_wh // 2, ring_wh, ring_wh)
            w = ParamSlotWidget(
                box=box, slot=slot, owner=self, ring=self._ring,
                value_font=value_font, label_font=label_font, parent=self,
            )
            self._slots.append(w)
            self.add_sel_widget(w)

        # Right: transfer curve + GR bar.
        self._curve = CompCurveWidget(
            box=Box.xywh(cb.x0 + _COL_W, cb.y0, cb.width - _COL_W, cb.height),
            font=label_font,
            parent=self,
        )
        self._curve.set_state(self.snapshot_state())

        self._meter: GrMeterClient | None = None
        self._start_meter()

    # ── PluginPanel contract ────────────────────────────────────────────────

    def snapshot_state(self) -> AcompState:
        def _v(sym: str, default: float) -> float:
            p = self.plugin.parameters.get(sym)
            return float(p.value) if p is not None and p.value is not None else default

        return AcompState(thr=_v(_THR, 0.0), rat=_v(_RAT, 4.0), kn=_v(_KN, 0.0), mak=_v(_MAK, 0.0))

    def apply_state(self, state: AcompState) -> None:
        for w in self._slots:
            w.sync()
        self._curve.set_state(state)

    def set_param(self, symbol: str, value: float) -> None:
        super().set_param(symbol, value)
        self._curve.set_state(self.snapshot_state())
        if symbol == _MAK and self._meter is not None:
            self._meter.set_makeup(value)

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id == 1 and isinstance(self.sel_ref, ParamSlotWidget):
            return self.sel_ref.on_encoder_rotation(rotations)
        return False

    def tick(self) -> None:
        super().tick()
        if self._meter is not None:
            reading = self._meter.get_reading()
            self._curve.set_gr(reading.gr_db if reading is not None and reading.valid else 0.0)

    def destroy(self) -> None:
        self._stop_meter()
        super().destroy()

    # ── GR meter lifecycle ──────────────────────────────────────────────────

    def _start_meter(self) -> None:
        n = self.plugin.instance_number
        if n is None:
            return  # can't address the JACK ports (headless / tests)
        try:
            meter = GrMeterClient()
            meter.start(f"effect_{n}:in_1", f"effect_{n}:out_1", self.snapshot_state().mak)
            self._meter = meter
        except Exception as exc:  # spawn/SHM failure must not take down the panel
            logging.warning("a-comp GR meter failed to start: %s", exc)
            self._meter = None

    def _stop_meter(self) -> None:
        if self._meter is not None:
            try:
                self._meter.stop()
            except Exception:
                pass
            self._meter = None


class CompCurveWidget(Widget):
    """Draws the compression transfer curve and a live gain-reduction bar."""

    _X_MIN = -60.0
    _X_MAX = 0.0
    _Y_MIN = -60.0
    _Y_MAX = 6.0
    _BAR_W = 16

    def __init__(self, *, box: Box, font, parent: Widget) -> None:
        super().__init__(box=box, parent=parent, visible=True)
        self._font = font
        self._state = AcompState(0.0, 4.0, 0.0, 0.0)
        self._gr_db = 0.0

    def set_state(self, state: AcompState) -> None:
        self._state = state
        self.refresh()

    def set_gr(self, gr_db: float) -> None:
        if abs(gr_db - self._gr_db) < 0.25:
            return
        self._gr_db = gr_db
        self.refresh()

    def _x_to_px(self, x_db: float, plot_w: int) -> int:
        return int((x_db - self._X_MIN) / (self._X_MAX - self._X_MIN) * (plot_w - 1))

    def _y_to_py(self, y_db: float, h: int) -> int:
        y = max(self._Y_MIN, min(self._Y_MAX, y_db))
        return int((self._Y_MAX - y) / (self._Y_MAX - self._Y_MIN) * (h - 1))

    def _draw(self, ctx) -> None:
        w, h = ctx.width, ctx.height
        plot_w = w - self._BAR_W - 4

        # Unity reference (dashed-ish light line) and the transfer curve.
        unity = [(self._x_to_px(x, plot_w), self._y_to_py(x, h)) for x in range(-60, 1, 6)]
        ctx.draw_line(unity, fill=(70, 70, 70), width=1)

        s = self._state
        curve = [
            (self._x_to_px(x, plot_w), self._y_to_py(_comp_output_db(x, s.thr, s.rat, s.kn, s.mak), h))
            for x in range(-60, 1, 2)
        ]
        ctx.draw_line(curve, fill=(120, 220, 140), width=2)

        # GR bar on the right edge, filling downward from the top.
        bar_x = w - self._BAR_W
        ctx.draw_rectangle(Box.xywh(bar_x, 0, self._BAR_W, h), fill=(30, 30, 30))
        fill_h = int(min(self._gr_db, _GR_MAX_DB) / _GR_MAX_DB * h)
        if fill_h > 0:
            ctx.draw_rectangle(Box.xywh(bar_x, 0, self._BAR_W, fill_h), fill=(230, 90, 60))
        label = f"{self._gr_db:.0f}"
        lw, lh = get_text_size(label, self._font)
        ctx.draw_text((bar_x + (self._BAR_W - lw) // 2, h - lh - 1), label, fill=(220, 220, 220), font=self._font)
