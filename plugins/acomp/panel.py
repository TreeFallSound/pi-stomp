"""DISTRHO a-comp: a full-screen compressor panel with a vector-instrument feel.

Left: a staggered column of thin arc-ring controls (threshold, ratio, knee,
makeup), the selected one framed by a targeting reticule.

Right: a square (1:1) transfer-curve plot rendered as bright anti-aliased
vectors over a dim reticule grid, with a dashed unity diagonal for reference. A
live crosshair rides the curve at the current input level — the vertical gap
between the unity line and the curve *is* the gain reduction — driven by a JACK
subprocess (``pistomp.compmeter``) that taps the compressor's in/out audio.

The analytic curve compositing mirrors ``plugins/eq/parametric.py``; the arc
column mirrors the EQ's invisible-selectable + single-drawing-widget split so
the staggered rings never clobber one another through opaque erase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pygame

from common.parameter import Parameter, Type
from pistomp.compmeter.client import GrMeterClient
from plugins.fullscreen import FullscreenPluginPanel
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.arc_ring import ArcRingGlyph
from uilib.glyphs.circle import RingGlyph
from uilib.misc import InputEvent, get_text_size
from uilib.widget import Widget

# ── LV2 port symbols (see docs/lv2-ttl-guide.md finder) ─────────────────────

_THR = "thr"  # threshold dB (-60..0)
_RAT = "rat"  # ratio (1..20)
_KN = "kn"  # knee dB (0..8)
_MAK = "mak"  # makeup dB (0..30)


@dataclass(frozen=True)
class _ArcSpec:
    symbol: str
    label: str
    color: tuple[int, int, int]
    display_fn: object  # Callable[[float], str]


# Column arcs, top to bottom (zigzag left/right — see _ARC_CENTERS).
_ARCS: tuple[_ArcSpec, ...] = (
    _ArcSpec(_THR, "THRESH", (255, 180, 80), lambda v: f"{v:+.0f}"),
    _ArcSpec(_RAT, "RATIO", (130, 220, 110), lambda v: f"{v:.1f}:1"),
    _ArcSpec(_KN, "KNEE", (110, 200, 230), lambda v: f"{v:.0f}"),
    _ArcSpec(_MAK, "MAKEUP", (210, 130, 230), lambda v: f"+{v:.0f}"),
)

# ── layout ──────────────────────────────────────────────────────────────────

_W = 320
_CONTENT_H = 210  # chrome (Back/Bypass/Reset) lives below this

_COL_W = 112  # left arc column width
_ARC_RADIUS = 26
_ARC_RING_HALF = 3.0  # thin vector stroke (default is 4.5 → looks like a donut)
_ARC_TIP = 3.0

# Zigzag centres inside the column: even arcs left, odd arcs right. Boxes may
# overlap; the circles never do (same-column pairs are 92 px apart vertically).
_ARC_CENTERS: tuple[tuple[int, int], ...] = ((36, 30), (76, 76), (36, 122), (76, 168))

_GRAPH_SIDE = 206  # 1:1 square
_GRAPH_X0 = _W - _GRAPH_SIDE  # 114
_GRAPH_Y0 = 2

# ── colours (phosphor-vector palette) ───────────────────────────────────────

_BG = (0, 0, 0)
_GRID = (26, 36, 30)
_FRAME = (52, 78, 64)
_UNITY = (74, 104, 84)
_CURVE = (120, 240, 150)
_RETICULE = (255, 200, 90)
_RETICULE_DIM = (150, 118, 58)
_TEXT = (200, 224, 206)
_LABEL = (150, 168, 156)

_INACTIVE_SHADE = 0.45  # matches plugins/eq/parametric.py
_CURVE_THICKNESS = 1.4

# ── transfer-curve dB range (both axes share it → unity is a true 45°) ──────

_A_MIN = -60.0
_A_MAX = 0.0
_SPAN = _A_MAX - _A_MIN


@dataclass(frozen=True)
class AcompState:
    thr: float
    rat: float
    kn: float
    mak: float


def _shade(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


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


def _step_for(param: Parameter) -> float:
    """One-detent step for a parameter, by type (mirrors multiband_menu)."""
    t = param.type
    if t in (Type.ENUMERATION, Type.INTEGER, Type.TOGGLED):
        return 1.0
    if t == Type.LOGARITHMIC:
        ratio = 2.0 ** (1.0 / 12.0)
        return max(0.01, (param.value or param.minimum) * (ratio - 1.0))
    return max(0.01, (param.maximum - param.minimum) / 100.0)


class AcompPanel(FullscreenPluginPanel[AcompState]):
    """Full-screen compressor: staggered arc column + reticule transfer plot."""

    # ── PluginPanel contract ────────────────────────────────────────────────

    def snapshot_state(self) -> AcompState:
        def _v(sym: str, default: float) -> float:
            p = self.plugin.parameters.get(sym)
            return float(p.value) if p is not None and p.value is not None else default

        return AcompState(thr=_v(_THR, 0.0), rat=_v(_RAT, 4.0), kn=_v(_KN, 0.0), mak=_v(_MAK, 0.0))

    def apply_state(self, state: AcompState) -> None:
        self._column.sync()
        self._graph.set_state(state)

    def build_widgets(self) -> None:
        cfg = Config()
        value_font: pygame._freetype.Font = cfg.get_font("small") or cfg.get_font("default")  # type: ignore[type-arg]
        label_font: pygame._freetype.Font = cfg.get_font("tiny") or value_font  # type: ignore[type-arg]
        axis_font: pygame._freetype.Font = cfg.get_font("tiny") or value_font  # type: ignore[type-arg]
        assert value_font is not None and label_font is not None and axis_font is not None

        # Reticule transfer plot (right).
        self._graph = ReticuleGraphWidget(
            box=Box.xywh(_GRAPH_X0, _GRAPH_Y0, _GRAPH_SIDE, _GRAPH_SIDE),
            font=axis_font,
            parent=self,
        )
        self._graph.set_state(self.snapshot_state())

        # Arc column (left): one drawing widget + N invisible Nav selectables.
        self._column = ArcColumnWidget(
            box=Box.xywh(0, 0, _COL_W, _CONTENT_H),
            owner=self,
            value_font=value_font,
            label_font=label_font,
            parent=self,
        )
        self._selectables: list[_ArcSelectable] = []
        for i, spec in enumerate(_ARCS):
            sel = _ArcSelectable(self, i, spec.symbol)
            self._selectables.append(sel)
            self.add_sel_widget(sel)

        self._last_bypassed = self.plugin.is_bypassed()
        self._refresh_bypass_style()
        self.sel_widget(self._selectables[0])

        self._meter: GrMeterClient | None = None

    # ── encoder dispatch: Tweak1 = selected, Tweak2 = thr, Tweak3 = rat ──────

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id not in (1, 2, 3) or rotations == 0:
            return True  # consume so tweaks never leak to volume while open
        if encoder_id == 2:
            self._edit_symbol(_THR, rotations)
        elif encoder_id == 3:
            self._edit_symbol(_RAT, rotations)
        else:
            sel = self.sel_ref
            if isinstance(sel, _ArcSelectable):
                self._edit_symbol(sel.symbol, rotations)
        return True

    def _edit_symbol(self, symbol: str, rotations: int) -> None:
        p = self.plugin.parameters.get(symbol)
        if p is None or p.value is None:
            return
        new_val = max(p.minimum, min(p.maximum, float(p.value) + rotations * _step_for(p)))
        if new_val == p.value:
            return
        self.set_param(symbol, new_val)
        self._column.sync_symbol(symbol)
        self._graph.set_state(self.snapshot_state())

    def _reset_symbol(self, symbol: str) -> None:
        snap = self.plugin.pedalboard_snapshot
        if symbol not in snap or self._is_symbol_locked(self.plugin.instance_id, symbol):
            return
        self.set_param(symbol, snap[symbol])
        self._column.sync_symbol(symbol)
        self._graph.set_state(self.snapshot_state())

    def set_param(self, symbol: str, value: float) -> None:
        super().set_param(symbol, value)
        if symbol == _MAK and self._meter is not None:
            self._meter.set_makeup(value)

    def _select_widget_ref(self, w) -> None:  # type: ignore[override]
        super()._select_widget_ref(w)
        idx = w.index if isinstance(w, _ArcSelectable) else None
        self._column.set_active_arc(idx)

    # ── tick / bypass ────────────────────────────────────────────────────────

    def tick(self) -> None:
        bypassed = self.plugin.is_bypassed()
        if bypassed != self._last_bypassed:
            self._last_bypassed = bypassed
            self._refresh_bypass_style()
        if self._meter is None:
            self._start_meter()
        if self._meter is not None:
            reading = self._meter.get_reading()
            if reading is not None and reading.valid:
                self._graph.set_reticule(reading.in_db, reading.out_db, reading.gr_db, True)
            else:
                self._graph.set_reticule(0.0, 0.0, 0.0, False)
        super().tick()

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        bypassed = self.plugin.is_bypassed()
        self._graph.set_bypassed(bypassed)
        self._column.set_bypassed(bypassed)

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


# ── invisible Nav selectable (the arc's ring is the visual) ─────────────────


class _ArcSelectable(Widget):
    """Zero-footprint Nav target; ``ArcColumnWidget`` paints the ring."""

    def __init__(self, panel: AcompPanel, index: int, symbol: str) -> None:
        super().__init__(box=Box.xywh(0, 0, 1, 1), parent=panel, visible=True)
        self._panel = panel
        self.index = index
        self.symbol = symbol

    def set_selected(self, selected: bool) -> None:  # type: ignore[override]
        self.selected = selected

    def input_event(self, event) -> bool:  # type: ignore[override]
        if event == InputEvent.LONG_CLICK:
            self._panel._reset_symbol(self.symbol)
            return True
        if event == InputEvent.CLICK:
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


# ── arc column ───────────────────────────────────────────────────────────────


class ArcColumnWidget(Widget):
    """Draws all four staggered arc rings; frames the selected one in a reticule."""

    def __init__(self, *, box: Box, owner: AcompPanel, value_font, label_font, parent: Widget) -> None:
        super().__init__(box=box, bkgnd_color=_BG, parent=parent, visible=True)
        self._owner = owner
        self._value_font = value_font
        self._label_font = label_font
        self._ring = ArcRingGlyph(_ARC_RADIUS, ring_half=_ARC_RING_HALF, tip_radius=_ARC_TIP)
        self._selected: int | None = None
        self._bypassed = False
        self._values: list[float | None] = [None] * len(_ARCS)
        self.sync()

    def _param(self, symbol: str) -> Parameter | None:
        return self._owner.plugin.parameters.get(symbol)

    def sync(self) -> None:
        for i, spec in enumerate(_ARCS):
            p = self._param(spec.symbol)
            self._values[i] = p.value if p is not None else None
        self.refresh()

    def sync_symbol(self, symbol: str) -> None:
        for i, spec in enumerate(_ARCS):
            if spec.symbol == symbol:
                p = self._param(symbol)
                self._values[i] = p.value if p is not None else None
                self._refresh_cell(i)
                return

    def set_active_arc(self, index: int | None) -> None:
        if index == self._selected:
            return
        old = self._selected
        self._selected = index
        for i in (old, index):
            if i is not None:
                self._refresh_cell(i)

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def _refresh_cell(self, index: int) -> None:
        cx, cy = _ARC_CENTERS[index]
        r = _ARC_RADIUS + 12  # ring + reticule brackets + a little label room
        bx = self.box
        assert bx is not None
        self.refresh(Box(bx.x0 + cx - r, bx.y0 + cy - r, bx.x0 + cx + r, bx.y0 + cy + r + 12))

    def _value_t(self, index: int) -> float:
        p = self._param(_ARCS[index].symbol)
        v = self._values[index]
        if p is None or v is None or p.maximum == p.minimum:
            return 0.0
        return max(0.0, min(1.0, (v - p.minimum) / (p.maximum - p.minimum)))

    def _format(self, index: int) -> str:
        v = self._values[index]
        if v is None:
            return "--"
        return _ARCS[index].display_fn(v)  # type: ignore[operator]

    def _draw(self, ctx) -> None:
        shade = _INACTIVE_SHADE if self._bypassed else 1.0
        half = self._ring.half_size
        for i, spec in enumerate(_ARCS):
            cx, cy = _ARC_CENTERS[i]
            ring = self._ring.render(
                self._value_t(i),
                filled_color=_shade(spec.color, shade),
                empty_color=_shade((56, 56, 56), shade),
                tip_color=_shade((255, 255, 255), shade),
            )
            ctx.paste(ring, (cx - half, cy - half))

            val = self._format(i)
            vw, vh = get_text_size(val, self._value_font)
            ctx.draw_text((cx - vw // 2, cy - vh // 2), val, fill=_shade(_TEXT, shade), font=self._value_font)

            lw, _lh = get_text_size(spec.label, self._label_font)
            ctx.draw_text((cx - lw // 2, cy + half - 1), spec.label, fill=_shade(_LABEL, shade), font=self._label_font)

            if i == self._selected:
                self._draw_reticule(ctx, cx, cy, _RETICULE if not self._bypassed else _RETICULE_DIM)

    def _draw_reticule(self, ctx, cx: int, cy: int, color: tuple[int, int, int]) -> None:
        """Four corner brackets framing the selected ring — a targeting reticule."""
        e = _ARC_RADIUS + 5  # bracket offset from centre
        a = 6  # arm length
        for sx in (-1, 1):
            for sy in (-1, 1):
                x = cx + sx * e
                y = cy + sy * e
                ctx.draw_line([(x, y), (x - sx * a, y)], fill=color, width=1)
                ctx.draw_line([(x, y), (x, y - sy * a)], fill=color, width=1)


# ── reticule transfer plot ───────────────────────────────────────────────────


def _x_px(db: float) -> float:
    return (db - _A_MIN) / _SPAN * (_GRAPH_SIDE - 1)


def _y_px(db: float) -> float:
    d = max(_A_MIN, min(_A_MAX, db))
    return (_A_MAX - d) / _SPAN * (_GRAPH_SIDE - 1)


class ReticuleGraphWidget(Widget):
    """Square transfer-curve plot with analytic-AA vectors and a live crosshair.

    The curve is recomputed only on ``set_state`` (parameter edits). The live
    crosshair moves via ``set_reticule``, which refreshes only a narrow vertical
    strip, so the meter animation never tears down the whole curve.
    """

    _GRID_DBS = tuple(range(-54, 0, 6))  # dim grid dots, both axes

    def __init__(self, *, box: Box, font, parent: Widget) -> None:
        super().__init__(box=box, bkgnd_color=_BG, parent=parent, visible=True)
        self._font = font
        self._bypassed = False
        # Curve caches (local pixel space, length _GRAPH_SIDE).
        self._y_f: np.ndarray | None = None
        self._y_lo: np.ndarray | None = None
        self._y_hi: np.ndarray | None = None
        # Live crosshair, in pixels (or None when parked/idle).
        self._ret_x: int | None = None
        self._ret_y: int | None = None
        self._ret_gr: float = 0.0
        self._ret_valid = False

    # ── state ────────────────────────────────────────────────────────────────

    def set_state(self, state: AcompState) -> None:
        xs_db = _A_MIN + np.arange(_GRAPH_SIDE) / (_GRAPH_SIDE - 1) * _SPAN
        outs = np.array([_comp_output_db(float(x), state.thr, state.rat, state.kn, state.mak) for x in xs_db])
        outs = np.clip(outs, _A_MIN, _A_MAX)
        self._y_f = (_A_MAX - outs) / _SPAN * (_GRAPH_SIDE - 1)
        mids = (self._y_f[:-1] + self._y_f[1:]) * 0.5
        y_left = np.empty_like(self._y_f)
        y_right = np.empty_like(self._y_f)
        y_left[0] = self._y_f[0]
        y_left[1:] = mids
        y_right[:-1] = mids
        y_right[-1] = self._y_f[-1]
        self._y_lo = np.minimum(y_left, y_right)
        self._y_hi = np.maximum(y_left, y_right)
        # Park the idle crosshair at the threshold knee.
        self._ret_x = int(round(_x_px(state.thr)))
        self._ret_y = int(round(self._y_f[max(0, min(_GRAPH_SIDE - 1, self._ret_x))]))
        self.refresh()

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def set_reticule(self, in_db: float, out_db: float, gr_db: float, valid: bool) -> None:
        if self._y_f is None:
            return
        new_x = int(round(max(0.0, min(_GRAPH_SIDE - 1.0, _x_px(in_db)))))
        new_y = int(round(_y_px(out_db))) if valid else int(round(self._y_f[new_x]))
        if valid == self._ret_valid and new_x == self._ret_x and new_y == self._ret_y:
            return
        old_x = self._ret_x
        old_valid, old_gr = self._ret_valid, self._ret_gr
        self._ret_x, self._ret_y, self._ret_gr, self._ret_valid = new_x, new_y, gr_db, valid
        for x in (old_x, new_x):
            if x is not None:
                self._refresh_strip(x)
        if valid != old_valid or (valid and f"{gr_db:.1f}" != f"{old_gr:.1f}"):
            self._refresh_readout()

    def _refresh_strip(self, x: int) -> None:
        bx = self.box
        assert bx is not None
        self.refresh(Box(bx.x0 + x - 9, bx.y0, bx.x0 + x + 10, bx.y1))

    def _refresh_readout(self) -> None:
        bx = self.box
        assert bx is not None
        self.refresh(Box(bx.x0 + 2, bx.y0 + 1, bx.x0 + 74, bx.y0 + 17))

    # ── paint ────────────────────────────────────────────────────────────────

    def _draw(self, ctx) -> None:
        shade = _INACTIVE_SHADE if self._bypassed else 1.0
        db = ctx.dirty_bounds
        rx0, rx1 = db.x0, db.x1

        self._draw_grid(ctx, shade)
        self._draw_unity(ctx, shade)
        self._draw_curve(ctx, rx0, rx1, shade)
        self._draw_crosshair(ctx, shade)

    def _draw_grid(self, ctx, shade: float) -> None:
        grid = _shade(_GRID, shade)
        for xd in self._GRID_DBS:
            gx = int(round(_x_px(xd)))
            for yd in self._GRID_DBS:
                gy = int(round(_y_px(yd)))
                ctx.draw_rectangle(Box.xywh(gx, gy, 1, 1), fill=grid)
        # Frame border + corner ticks.
        frame = _shade(_FRAME, shade)
        s = _GRAPH_SIDE - 1
        ctx.draw_line([(0, 0), (s, 0), (s, s), (0, s), (0, 0)], fill=_shade(_GRID, shade), width=1)
        for cx, cy, dx, dy in ((0, 0, 1, 1), (s, 0, -1, 1), (0, s, 1, -1), (s, s, -1, -1)):
            ctx.draw_line([(cx, cy), (cx + dx * 8, cy)], fill=frame, width=1)
            ctx.draw_line([(cx, cy), (cx, cy + dy * 8)], fill=frame, width=1)

    def _draw_unity(self, ctx, shade: float) -> None:
        col = _shade(_UNITY, shade)
        s = _GRAPH_SIDE - 1
        for x in range(0, _GRAPH_SIDE, 6):  # dashed
            ctx.draw_line([(x, s - x), (min(x + 3, s), s - min(x + 3, s))], fill=col, width=1)

    def _draw_curve(self, ctx, rx0: int, rx1: int, shade: float) -> None:
        if self._y_f is None or self._y_lo is None or self._y_hi is None:
            return
        cx0 = max(0, rx0)
        cx1 = min(_GRAPH_SIDE, rx1)
        if cx1 <= cx0:
            return
        ox, oy = ctx._f().topleft
        surf = ctx.surface
        px = None
        sub = None
        try:
            px = pygame.surfarray.pixels3d(surf)
            sub = px[ox + cx0 : ox + cx1, oy : oy + _GRAPH_SIDE, :]
            bg = sub.astype(np.float32)
            yl = self._y_lo[cx0:cx1].astype(np.float32)
            yh = self._y_hi[cx0:cx1].astype(np.float32)
            mid = (yl + yh) * 0.5
            half_extent = np.sqrt(1.0 + (yh - yl) ** 2) * (_CURVE_THICKNESS * 0.5)
            lo = mid - half_extent
            hi = mid + half_extent
            rows = np.arange(_GRAPH_SIDE, dtype=np.float32)
            overlap = np.minimum(rows[None, :] + 1.0, hi[:, None]) - np.maximum(rows[None, :], lo[:, None])
            alpha = np.clip(overlap, 0.0, 1.0)
            cc = np.array(_shade(_CURVE, shade), dtype=np.float32)
            blended = bg + (cc - bg) * alpha[:, :, None]
            mask = alpha > 0.0
            result = np.where(mask[:, :, None], blended, bg)
            np.clip(result, 0, 255, out=result)
            sub[:] = result.astype(np.uint8)
        finally:
            del sub
            del px

    def _draw_crosshair(self, ctx, shade: float) -> None:
        if self._ret_x is None or self._ret_y is None:
            return
        x, y = self._ret_x, self._ret_y
        active = self._ret_valid and not self._bypassed
        col = _shade(_RETICULE if active else _RETICULE_DIM, shade)
        # Drop line: unity (input on the diagonal) down to the curve output.
        unity_y = int(round(_y_px(_A_MIN + x / (_GRAPH_SIDE - 1) * _SPAN)))
        if y != unity_y:
            ctx.draw_line([(x, min(unity_y, y)), (x, max(unity_y, y))], fill=_shade(_UNITY, shade), width=1)
        # Crosshair arms (gapped centre) + reticule ring.
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ctx.draw_line([(x + dx * 3, y + dy * 3), (x + dx * 8, y + dy * 8)], fill=col, width=1)
        ring = RingGlyph(6, ring_half=0.9).render()
        tinted = ring.copy()
        cs = pygame.Surface(ring.get_size(), pygame.SRCALPHA)
        cs.fill(col)
        tinted.blit(cs, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        ctx.paste(tinted, (x - 7, y - 7))
        # GR readout, fixed at the top-left so it isn't part of the moving strip.
        if active:
            ctx.draw_text((4, 3), f"GR {self._ret_gr:.1f}", fill=_shade(_TEXT, shade), font=self._font)
