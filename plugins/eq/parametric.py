"""Abstract parametric EQ panel — frequency-response curve visualization.

Subclasses provide band specs via ``build_band_specs()``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Optional

import numpy as np
import pygame

from plugins.base import PluginPanel
from plugins.eq.band_spec import BandSpec
from plugins.eq.curve import (
    GRAPH_W,
    BandParams,
    CurveCache,
    EqState,
    db_to_y,
    db_to_y_float,
    freq_to_x,
)
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.circle import CircleGlyph, RingGlyph
from uilib.misc import InputEvent, get_text_size
from uilib.widget import Widget


# Type alias for the per-band geometry we cache for diff-paint
# (image_x, image_y, color_rgb, enabled).
_NodePos = tuple[int, int, tuple[int, int, int], bool]


# ── layout constants ────────────────────────────────────────────────────────

_W = 320
_H = 240

READOUT_Y0 = 0
READOUT_Y1 = 22

GRAPH_Y0 = 22
GRAPH_Y1 = 200
GRAPH_H = GRAPH_Y1 - GRAPH_Y0

DB_MAX = 18.0

# ── colours ──────────────────────────────────────────────────────────────────

BG_BLACK = (0, 0, 0)
GRID_DIM = (45, 45, 45)
GRID_0DB = (140, 140, 140)
CURVE_COLOR = (220, 220, 220)
CURVE_THICKNESS = 1.3
HALO_COLOR = (255, 255, 255)
READOUT_COLOR = (200, 200, 200)
INACTIVE_SHADE = 0.45

NODE_R = 4
HALO_R = 6


def _tint_mask(mask: pygame.Surface, color: tuple[int, int, int]) -> pygame.Surface:
    tinted = mask.copy()
    color_surf = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
    color_surf.fill(color)
    tinted.blit(color_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return tinted


def paint_band_node(ctx, cx: int, cy: int, color: tuple[int, int, int], selected: bool) -> None:
    """Paint the parametric-EQ node circle (black eraser, coloured fill, optional halo)."""
    eraser = CircleGlyph(NODE_R + 2)
    ctx.paste(_tint_mask(eraser.render(), BG_BLACK), (cx - eraser.radius, cy - eraser.radius))
    node = CircleGlyph(NODE_R)
    ctx.paste(_tint_mask(node.render(), color), (cx - node.radius, cy - node.radius))
    if selected:
        halo = RingGlyph(HALO_R)
        ctx.paste(_tint_mask(halo.render(), HALO_COLOR), (cx - halo.half_size, cy - halo.half_size))

SMEAR_ALPHA = 0.65
SMEAR_LENGTH_MAX = 60


# ── grid helpers ─────────────────────────────────────────────────────────────

_FREQ_MAJOR_STEP_PX = 80
_FREQ_MINOR_STEP_PX = 40
_DB_GRID = (-18.0, -12.0, -6.0, 6.0, 12.0, 18.0)


def _x_to_freq(x: int) -> float:
    import math as _m

    norm = x / (GRAPH_W - 1)
    log_min = _m.log10(20.0)
    log_max = _m.log10(20000.0)
    return 10.0 ** (log_min + norm * (log_max - log_min))


def _fmt_axis_freq(hz: float, with_unit: bool = False) -> str:
    if hz < 1000.0:
        s = f"{int(round(hz))}"
        return f"{s}Hz" if with_unit else s
    k = hz / 1000.0
    if k >= 10.0:
        return f"{int(round(k))}k"
    return f"{k:.1f}k"


_FREQ_MAJORS_X: tuple[int, ...] = (0,) + tuple(x for x in range(_FREQ_MAJOR_STEP_PX, GRAPH_W, _FREQ_MAJOR_STEP_PX))
_FREQ_MINORS_X: tuple[int, ...] = tuple(
    x for x in range(_FREQ_MINOR_STEP_PX, GRAPH_W, _FREQ_MINOR_STEP_PX) if x not in _FREQ_MAJORS_X
)
_FREQ_GRID_X: frozenset[int] = frozenset(_FREQ_MAJORS_X) | frozenset(_FREQ_MINORS_X)

_FREQ_LABELS: tuple[tuple[str, int], ...] = tuple(
    (_fmt_axis_freq(_x_to_freq(x), with_unit=(x == 0)), x) for x in sorted(_FREQ_GRID_X)
)
_DB_LABELS: tuple[tuple[str, float], ...] = (("+18dB", 18.0),)
_AXIS_LABEL_COLOR = (110, 110, 110)


def _db_to_y_scalar(db: float) -> int:
    return int(db_to_y(np.array([db]), GRAPH_Y0, GRAPH_Y1, DB_MAX)[0])


_ZERO_DB_Y: int = _db_to_y_scalar(0.0)
_DB_GRID_Y: frozenset[int] = frozenset(_db_to_y_scalar(db) for db in _DB_GRID)


def bg_color(x: int, y: int) -> tuple[int, int, int]:
    if y == _ZERO_DB_Y:
        return GRID_0DB
    if y in _DB_GRID_Y:
        return GRID_DIM
    if x in _FREQ_GRID_X:
        return GRID_DIM
    return BG_BLACK


_BG_ZERO_Y = _ZERO_DB_Y - GRAPH_Y0
_BG_DB_GRID_Y = frozenset(y - GRAPH_Y0 for y in _DB_GRID_Y)
_BG_ARRAY: np.ndarray = np.zeros((GRAPH_W, GRAPH_H, 3), dtype=np.uint8)
_BG_ARRAY[:] = BG_BLACK
for _y in _BG_DB_GRID_Y:
    if 0 <= _y < GRAPH_H:
        _BG_ARRAY[:, _y, :] = GRID_DIM
for _x in _FREQ_GRID_X:
    if 0 <= _x < GRAPH_W:
        _BG_ARRAY[_x, :, :] = GRID_DIM
if 0 <= _BG_ZERO_Y < GRAPH_H:
    _BG_ARRAY[:, _BG_ZERO_Y, :] = GRID_0DB


# ── smear (comet-tail) helpers ──────────────────────────────────────────────


def _smear_colors_for_state(state: EqState, bands: Sequence[BandSpec]) -> Optional[np.ndarray]:
    """RGB color per graph column, ease-in-out interpolated across the x
    positions of currently-enabled bands. Returns (GRAPH_W, 3) float array,
    or None if no bands are enabled (no smear)."""
    anchors: list[tuple[int, tuple[int, int, int]]] = []
    for band in bands:
        p = state.bands.get(band.name)
        if p is None or not p.enabled:
            continue
        anchors.append((int(freq_to_x(p.freq)), band.color))
    if not anchors:
        return None
    anchors.sort(key=lambda t: t[0])
    xs = np.array([a[0] for a in anchors], dtype=int)
    cs = np.array([a[1] for a in anchors], dtype=float)
    all_x = np.arange(GRAPH_W)
    if len(xs) == 1:
        out = np.broadcast_to(cs[0], (GRAPH_W, 3)).copy()
        return out
    idx = np.clip(np.searchsorted(xs, all_x, side="right"), 1, len(xs) - 1)
    x0 = xs[idx - 1]
    x1 = xs[idx]
    span = np.maximum(x1 - x0, 1)
    t = np.clip((all_x - x0) / span, 0.0, 1.0)
    t_s = t * t * (3.0 - 2.0 * t)
    out = cs[idx - 1] + (cs[idx] - cs[idx - 1]) * t_s[:, None]
    out[all_x <= xs[0]] = cs[0]
    out[all_x >= xs[-1]] = cs[-1]
    return out


def _smear_intensity_from_db(curve_db: np.ndarray) -> np.ndarray:
    return np.clip(np.abs(curve_db) / DB_MAX, 0.0, 1.0)


# ── GraphWidget ──────────────────────────────────────────────────────────────


class GraphWidget(Widget):
    """Owns the curve, grid and band nodes.

    State-change setters (`set_state`, `set_selected`, `set_bypassed`) compute
    the dirty x-extent against cached previous state and call `self.refresh`
    with only that sub-box; `_draw` paints from-scratch but clips work to the
    requested `real_box` so only changed columns are touched.

    Assumes the widget spans the full panel width with image x == local x.
    """

    def __init__(self, box: Box, bands: Sequence[BandSpec], axis_font=None, show_axis_labels: bool = True, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._bands = bands
        self._axis_font = axis_font
        self._show_axis_labels = show_axis_labels
        self._cache = CurveCache()
        self._state: Optional[EqState] = None
        self._selected_band: Optional[str] = None
        self._curve_y: Optional[np.ndarray] = None
        self._curve_y_float: Optional[np.ndarray] = None
        self._curve_y_lo: Optional[np.ndarray] = None
        self._curve_y_hi: Optional[np.ndarray] = None
        self._node_positions: dict[str, _NodePos] = {}
        self._bypassed: bool = False
        self._smear_colors: Optional[np.ndarray] = None
        self._smear_intensity: Optional[np.ndarray] = None

    # ── state setters (self-refresh with surgical sub-box) ──────────────────

    def set_state(self, state: EqState) -> None:
        new_curve_db = self._cache.compute(self._bands, state)
        new_curve_y_float = db_to_y_float(new_curve_db, GRAPH_Y0, GRAPH_Y1, DB_MAX)
        new_curve_y = np.round(new_curve_y_float).astype(int)
        new_y_lo, new_y_hi = self._neighbor_extents(new_curve_y_float)
        new_nodes = self._compute_nodes(state)
        new_smear_colors = _smear_colors_for_state(state, self._bands)
        new_smear_intensity = _smear_intensity_from_db(new_curve_db)

        old_curve = self._curve_y
        old_nodes = self._node_positions
        old_smear_colors = self._smear_colors
        old_smear_intensity = self._smear_intensity

        self._state = state

        if old_curve is None:
            self._curve_y = new_curve_y
            self._curve_y_float = new_curve_y_float
            self._curve_y_lo = new_y_lo
            self._curve_y_hi = new_y_hi
            self._node_positions = new_nodes
            self._smear_colors = new_smear_colors
            self._smear_intensity = new_smear_intensity
            return

        x_min, x_max = self._dirty_extent_for_curve(old_curve, new_curve_y, self._curve_y_float, new_curve_y_float)
        x_min, x_max = self._extend_extent_for_smear(
            x_min,
            x_max,
            old_smear_colors,
            new_smear_colors,
            old_smear_intensity,
            new_smear_intensity,
        )
        x_min, x_max = self._extend_extent_for_nodes(x_min, x_max, old_nodes, new_nodes)

        if x_min is None or x_max is None:
            return

        assert self._curve_y is not None
        assert self._curve_y_float is not None
        assert self._curve_y_lo is not None
        assert self._curve_y_hi is not None
        self._curve_y[x_min:x_max] = new_curve_y[x_min:x_max]
        self._curve_y_float[x_min:x_max] = new_curve_y_float[x_min:x_max]
        self._curve_y_lo[x_min:x_max] = new_y_lo[x_min:x_max]
        self._curve_y_hi[x_min:x_max] = new_y_hi[x_min:x_max]
        if new_smear_colors is not None and self._smear_colors is not None:
            self._smear_colors[x_min:x_max] = new_smear_colors[x_min:x_max]
        else:
            self._smear_colors = new_smear_colors
        if new_smear_intensity is not None and self._smear_intensity is not None:
            self._smear_intensity[x_min:x_max] = new_smear_intensity[x_min:x_max]
        else:
            self._smear_intensity = new_smear_intensity
        self._node_positions = new_nodes
        self._refresh_x_range(x_min, x_max)

    def set_selected(self, band_name: Optional[str]) -> None:  # type: ignore[override]
        if band_name == self._selected_band:
            return
        old = self._selected_band
        self._selected_band = band_name
        for name in (old, band_name):
            self._refresh_node_bbox(name)

    def _refresh_node_bbox(self, name: Optional[str]) -> None:
        if name is None:
            return
        pos = self._node_positions.get(name)
        if pos is None:
            return
        cx, cy, _, _ = pos
        r = HALO_R + 1
        bx = self.box
        if bx is None:
            return
        x0 = max(bx.x0, cx - r)
        x1 = min(bx.x1, cx + r + 1)
        y0 = max(bx.y0, cy - r)
        y1 = min(bx.y1, cy + r + 1)
        if x0 < x1 and y0 < y1:
            self.refresh(Box(x0, y0, x1, y1))

    def set_bypassed(self, bypassed: bool) -> None:
        if self._bypassed == bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    # ── dirty-extent helpers ────────────────────────────────────────────────

    @staticmethod
    def _dirty_extent_for_curve(
        old_int: np.ndarray,
        new_int: np.ndarray,
        old_f: Optional[np.ndarray] = None,
        new_f: Optional[np.ndarray] = None,
    ) -> tuple[Optional[int], Optional[int]]:
        diff = np.flatnonzero(old_int != new_int)
        if old_f is not None and new_f is not None:
            f_eps = 0.1
            float_diff = np.flatnonzero(np.abs(old_f - new_f) > f_eps)
            diff = np.union1d(diff, float_diff)
        if diff.size == 0:
            return None, None
        return int(diff[0]), int(diff[-1]) + 1

    @staticmethod
    def _extend_extent_for_smear(
        x_min: Optional[int],
        x_max: Optional[int],
        old_colors: Optional[np.ndarray],
        new_colors: Optional[np.ndarray],
        old_intensity: Optional[np.ndarray],
        new_intensity: Optional[np.ndarray],
    ) -> tuple[Optional[int], Optional[int]]:
        I_EPS = 1.0 / 255.0
        C_EPS = 2.0
        diffs: list[np.ndarray] = []
        if (old_colors is None) != (new_colors is None):
            diffs.append(np.arange(GRAPH_W))
        elif old_colors is not None and new_colors is not None:
            diffs.append(np.flatnonzero(np.any(np.abs(old_colors - new_colors) > C_EPS, axis=1)))
        if (old_intensity is None) != (new_intensity is None):
            diffs.append(np.arange(GRAPH_W))
        elif old_intensity is not None and new_intensity is not None:
            diffs.append(np.flatnonzero(np.abs(old_intensity - new_intensity) > I_EPS))
        combined = np.concatenate(diffs) if diffs else np.array([], dtype=int)
        if combined.size == 0:
            return x_min, x_max
        cmin = int(combined.min())
        cmax = int(combined.max()) + 1
        x_min = cmin if x_min is None else min(x_min, cmin)
        x_max = cmax if x_max is None else max(x_max, cmax)
        return x_min, x_max

    def _extend_extent_for_nodes(
        self,
        x_min: Optional[int],
        x_max: Optional[int],
        old_nodes: dict[str, _NodePos],
        new_nodes: dict[str, _NodePos],
    ) -> tuple[Optional[int], Optional[int]]:
        node_r = HALO_R + 1
        names = set(old_nodes) | set(new_nodes)
        for name in names:
            if old_nodes.get(name) == new_nodes.get(name):
                continue
            for n in (old_nodes.get(name), new_nodes.get(name)):
                if n is None:
                    continue
                cx, _, _, _ = n
                nx0, nx1 = cx - node_r, cx + node_r + 1
                x_min = nx0 if x_min is None else min(x_min, nx0)
                x_max = nx1 if x_max is None else max(x_max, nx1)
        return x_min, x_max

    def _node_x_extent(self, name: Optional[str]) -> Optional[tuple[int, int]]:
        if name is None:
            return None
        pos = self._node_positions.get(name)
        if pos is None:
            return None
        cx = pos[0]
        node_r = HALO_R + 1
        return cx - node_r, cx + node_r + 1

    def _refresh_x_range(self, x_min: Optional[int], x_max: Optional[int]) -> None:
        if x_min is None or x_max is None:
            return
        bx = self.box
        if bx is None:
            return
        x_min = max(bx.x0, x_min)
        x_max = min(bx.x1, x_max)
        if x_min >= x_max:
            return
        self.refresh(Box(x_min, bx.y0, x_max, bx.y1))

    @staticmethod
    def _neighbor_extents(ys_f: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mids = (ys_f[:-1] + ys_f[1:]) * 0.5
        y_left = np.empty_like(ys_f)
        y_right = np.empty_like(ys_f)
        y_left[0] = ys_f[0]
        y_left[1:] = mids
        y_right[:-1] = mids
        y_right[-1] = ys_f[-1]
        return np.minimum(y_left, y_right), np.maximum(y_left, y_right)

    def _compute_nodes(self, state: EqState) -> dict[str, _NodePos]:
        out: dict[str, _NodePos] = {}
        for band in self._bands:
            p = state.bands.get(band.name)
            if p is None:
                continue
            cx = int(freq_to_x(p.freq))
            cy = _ZERO_DB_Y if band.gain_sym is None else _db_to_y_scalar(p.gain_db)
            color: tuple[int, int, int] = band.color if p.enabled else (80, 80, 80)
            out[band.name] = (cx, cy, color, p.enabled)
        return out

    # ── paint ───────────────────────────────────────────────────────────────

    def _draw_erase(self, ctx) -> None:
        pass

    def _draw(self, ctx) -> None:
        db = ctx.dirty_bounds
        rx0, ry0 = db.x0, db.y0
        rx1, ry1 = db.x1, db.y1

        ctx.draw_rectangle(db, fill=BG_BLACK)

        for x in _FREQ_GRID_X:
            if rx0 <= x < rx1:
                ctx.draw_line([(x, max(ry0, 0)), (x, min(ry1, GRAPH_H) - 1)], fill=GRID_DIM, width=1)

        hx0 = max(rx0, 0)
        hx1 = min(rx1, _W)
        hy0 = max(ry0, 0)
        hy1 = min(ry1, GRAPH_H)
        zero_y = _ZERO_DB_Y - GRAPH_Y0
        if hx0 < hx1 and hy0 < hy1:
            for db_val in _DB_GRID:
                y = _db_to_y_scalar(db_val) - GRAPH_Y0
                if hy0 <= y < hy1:
                    ctx.draw_line([(hx0, y), (hx1 - 1, y)], fill=GRID_DIM, width=1)
            if hy0 <= zero_y < hy1:
                ctx.draw_line([(hx0, zero_y), (hx1 - 1, zero_y)], fill=GRID_0DB, width=1)

        if self._curve_y is not None:
            shade = INACTIVE_SHADE if self._bypassed else 1.0
            curve_color = tuple(int(c * shade) for c in CURVE_COLOR)
            cx0 = max(rx0, 0)
            cx1 = min(rx1, GRAPH_W)
            cy0 = max(ry0, 0)
            cy1 = min(ry1, GRAPH_H)
            if cx1 > cx0 and cy1 > cy0:
                ox, oy = ctx._f().topleft
                surf = ctx.surface
                px = None
                sub = None
                try:
                    px = pygame.surfarray.pixels3d(surf)
                    sub = px[ox + cx0 : ox + cx1, oy + cy0 : oy + cy1, :]
                    bg = _BG_ARRAY[cx0:cx1, cy0:cy1].astype(np.float32)
                    result = bg.copy()

                    ys_f = self._curve_y_float
                    smear_colors = self._smear_colors
                    smear_intensity = self._smear_intensity
                    if smear_colors is not None and smear_intensity is not None and ys_f is not None:
                        yf = ys_f[cx0:cx1].astype(np.float32) - GRAPH_Y0
                        yz_f = float(_ZERO_DB_Y - GRAPH_Y0)
                        raw_len = np.abs(yz_f - yf)
                        length = np.minimum(raw_len, float(SMEAR_LENGTH_MAX))
                        intensity = smear_intensity[cx0:cx1].astype(np.float32)
                        top_alpha = SMEAR_ALPHA * intensity
                        valid = (length >= 0.5) & (intensity > 0.0)
                        down = yf <= yz_f
                        y_top = np.where(down, yf, yf - length)
                        y_bot = np.where(down, yf + length, yf)
                        inv_2len = 0.5 / np.where(length > 0, length, 1.0)
                        rows = np.arange(cy0, cy1, dtype=np.float32)
                        a = np.maximum(rows[None, :], y_top[:, None])
                        b = np.minimum(rows[None, :] + 1.0, y_bot[:, None])
                        pix_valid = (b > a) & valid[:, None]
                        u_a = np.where(down[:, None], a - yf[:, None], yf[:, None] - b)
                        u_b = np.where(down[:, None], b - yf[:, None], yf[:, None] - a)
                        smear_alpha = top_alpha[:, None] * (
                            (u_b - u_a) - (u_b * u_b - u_a * u_a) * inv_2len[:, None]
                        )
                        smear_alpha = np.where(pix_valid & (smear_alpha > 0.0), smear_alpha, 0.0)
                        sc = smear_colors[cx0:cx1].astype(np.float32) * shade
                        smear_blend = bg + (sc[:, None, :] - bg) * smear_alpha[:, :, None]
                        smear_mask = smear_alpha > 0.0
                        result[smear_mask] = smear_blend[smear_mask]

                    y_lo = self._curve_y_lo
                    y_hi = self._curve_y_hi
                    if y_lo is not None and y_hi is not None:
                        yl = y_lo[cx0:cx1].astype(np.float32) - GRAPH_Y0
                        yh = y_hi[cx0:cx1].astype(np.float32) - GRAPH_Y0
                        mid = (yl + yh) * 0.5
                        half_extent = np.sqrt(1.0 + (yh - yl) ** 2) * (CURVE_THICKNESS * 0.5)
                        y_lo_ext = mid - half_extent
                        y_hi_ext = mid + half_extent
                        rows = np.arange(cy0, cy1, dtype=np.float32)
                        overlap = np.minimum(rows[None, :] + 1.0, y_hi_ext[:, None]) - np.maximum(
                            rows[None, :], y_lo_ext[:, None]
                        )
                        curve_alpha = np.clip(overlap, 0.0, 1.0)
                        cc = np.array(curve_color, dtype=np.float32)
                        curve_blend = bg + (cc - bg) * curve_alpha[:, :, None]
                        curve_mask = curve_alpha > 0.0
                        result[curve_mask] = curve_blend[curve_mask]
                    else:
                        ys = self._curve_y
                        base_y = ys[cx0:cx1].astype(np.int32) - GRAPH_Y0
                        in_range = (base_y >= cy0) & (base_y < cy1)
                        xs_idx = np.where(in_range)[0]
                        if xs_idx.size > 0:
                            result[xs_idx, base_y[xs_idx] - cy0, :] = curve_color

                    np.clip(result, 0, 255, out=result)
                    sub[:] = result.astype(np.uint8)
                finally:
                    del sub
                    del px

        if self._state is not None and self._node_positions:
            node_r = HALO_R + 1
            ordered: list[BandSpec] = [b for b in self._bands if b.name != self._selected_band]
            sel = next((b for b in self._bands if b.name == self._selected_band), None)
            if sel is not None:
                ordered.append(sel)
            for band in ordered:
                pos = self._node_positions.get(band.name)
                if pos is None:
                    continue
                cx, cy, color, _enabled = pos
                if cx + node_r <= rx0 or cx - node_r >= rx1:
                    continue
                self._paint_node(ctx, cx, cy - GRAPH_Y0, color, band.name == self._selected_band)

        if self._axis_font is not None and self._show_axis_labels:
            self._paint_axis_labels(ctx, rx0, rx1)

    def _paint_axis_labels(self, ctx, rx0: int, rx1: int) -> None:
        font = self._axis_font
        for text, db_val in _DB_LABELS:
            tw, th = get_text_size(text, font)
            x = 2
            if x + tw <= rx0 or x >= rx1:
                continue
            y = _db_to_y_scalar(db_val) - GRAPH_Y0
            if db_val > 0:
                ty = y + 1
            else:
                ty = y - th - 1
            ctx.draw_text((x, ty), text, fill=_AXIS_LABEL_COLOR, font=font)
        for text, fx in _FREQ_LABELS:
            tw, th = get_text_size(text, font)
            tx = fx + 2
            if tx + tw <= rx0 or tx >= rx1:
                continue
            ty = GRAPH_H - th - 1
            ctx.draw_text((tx, ty), text, fill=_AXIS_LABEL_COLOR, font=font)

    def _paint_node(self, ctx, cx: int, cy: int, color: tuple[int, int, int], selected: bool) -> None:
        paint_band_node(ctx, cx, cy, color, selected)


# ── ReadoutWidget ────────────────────────────────────────────────────────────


_READOUT_COLS_LEFT: tuple[tuple[str, int], ...] = (
    ("name", 6),
    ("freq", 60),
    ("q", 160),
)
_READOUT_GAIN_RIGHT: int = _W - 6


class ReadoutWidget(Widget):
    """Top-bar with statically-positioned name / freq / Q / gain columns."""

    def __init__(self, box: Box, font, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._font = font
        self._fields: dict[str, str] = {k: "" for k, _ in _READOUT_COLS_LEFT}
        self._fields["gain"] = ""
        self._message: Optional[str] = None

    def set_fields(self, name: str, freq: str, q: str, gain: str) -> None:
        new = {"name": name, "freq": freq, "q": q, "gain": gain}
        if self._message is None and new == self._fields:
            return
        self._fields = new
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
        for key, x in _READOUT_COLS_LEFT:
            text = self._fields.get(key, "")
            if text:
                ctx.draw_text((x, 1), text, fill=READOUT_COLOR, font=self._font)
        gain = self._fields.get("gain", "")
        if gain:
            tw, _ = get_text_size(gain, self._font)
            x = _READOUT_GAIN_RIGHT - tw
            ctx.draw_text((x, 1), gain, fill=READOUT_COLOR, font=self._font)


# ── invisible band selectable ────────────────────────────────────────────────


class BandSelectable(Widget):
    """Nav-cycle target with no visual presence of its own — the band's
    coloured circle on the graph is the indicator (halo when selected)."""

    def __init__(self, panel: ParametricEqPanel, band: BandSpec) -> None:
        super().__init__(box=Box.xywh(0, 0, 1, 1), parent=panel, visible=True)
        self._panel: ParametricEqPanel = panel
        self.band = band

    def set_selected(self, selected: bool) -> None:  # type: ignore[override]
        self.selected = selected

    def input_event(self, event) -> bool:  # type: ignore[override]
        if event == InputEvent.CLICK:
            self._panel._toggle_band_enable(self.band)
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


# ── readout formatting ──────────────────────────────────────────────────────


def _fmt_freq(hz: float) -> str:
    if hz >= 1000.0:
        return f"{hz / 1000.0:.2f} kHz"
    return f"{hz:.0f} Hz"


def band_readout_fields(band: BandSpec, p: BandParams) -> tuple[str, str, str, str]:
    """Format readout fields for a parametric band. Returns (name, freq, q, gain)."""
    name = band.name
    freq = _fmt_freq(p.freq)
    q = f"Q {p.q:.2f}"
    if not p.enabled:
        gain = "disabled"
    elif band.gain_sym is None:
        gain = "\u2014"
    else:
        gain = f"{p.gain_db:+.1f} dB"
    return name, freq, q, gain


# ── tweak step sizes ────────────────────────────────────────────────────────

_GAIN_STEP_DB = 0.5
_FREQ_STEP = 2.0 ** (1.0 / 12.0)
_Q_STEP = 0.05


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── ParametricEqPanel (ABC) ──────────────────────────────────────────────────


class ParametricEqPanel(PluginPanel[EqState]):
    """Abstract base for parametric EQ panels with frequency-response curve.

    Subclasses must implement ``build_band_specs()`` returning the list of
    ``BandSpec`` for this plugin.
    """

    _show_axis_labels: bool = True

    # ── subclass contract ──────────────────────────────────────────────────

    def build_band_specs(self) -> Sequence[BandSpec]:
        raise NotImplementedError

    # ── PluginPanel subclass contract ────────────────────────────────────────

    def snapshot_state(self) -> EqState:
        params = self.plugin.parameters

        def _val(symbol: str, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None and p.value is not None else default

        bands: dict[str, BandParams] = {}
        for band in self.bands:
            enable_val = _val(band.enable_sym, 0.0) if band.enable_sym is not None else 1.0
            bands[band.name] = BandParams(
                enabled=bool(enable_val),
                freq=_val(band.freq_sym, 0.5 * (band.freq_min + band.freq_max)),
                q=_val(band.q_sym, 0.7) if band.q_sym is not None else 1.0,
                gain_db=_val(band.gain_sym, 0.0) if band.gain_sym else 0.0,
            )
        return EqState(
            plugin_enabled=bool(_val("enable", 1.0)),
            global_gain_db=_val("gain", 0.0),
            bands=bands,
        )

    def apply_state(self, state: EqState) -> None:
        self._state = state
        self._graph.set_state(state)
        self._update_readout()

    def build_widgets(self) -> None:
        self.bands = self.build_band_specs()
        self._state = self.snapshot_state()
        cfg = Config()
        btn_font = cfg.get_font("default")
        axis_font = cfg.get_font("tiny")

        self._readout = ReadoutWidget(
            box=Box.xywh(0, READOUT_Y0, _W, READOUT_Y1 - READOUT_Y0),
            font=btn_font,
            parent=self,
        )
        self._graph = GraphWidget(
            box=Box.xywh(0, GRAPH_Y0, _W, GRAPH_H),
            bands=self.bands,
            axis_font=axis_font,
            show_axis_labels=self._show_axis_labels,
            parent=self,
        )

        self._band_sels: dict[str, BandSelectable] = {}
        for band in self.bands:
            sel = BandSelectable(self, band)
            self._band_sels[band.name] = sel
            self.add_sel_widget(sel)

        self._graph.set_bypassed(self.plugin.is_bypassed())
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
            if band.gain_sym is None:
                return True
            new_gain = _clip(p.gain_db + delta * _GAIN_STEP_DB, band.gain_min, band.gain_max)
            if new_gain == p.gain_db:
                return True
            self.set_param(band.gain_sym, new_gain)
            self._replace_band(band, gain_db=new_gain)
            return True
        elif encoder_id == 2:
            new_freq = _clip(p.freq * (_FREQ_STEP**delta), band.freq_min, band.freq_max)
            if new_freq == p.freq:
                return True
            self.set_param(band.freq_sym, new_freq)
            self._replace_band(band, freq=new_freq)
            return True
        elif encoder_id == 3:
            if band.q_sym is None:
                return True
            new_q = _clip(p.q + delta * _Q_STEP, band.q_min, band.q_max)
            if new_q == p.q:
                return True
            self.set_param(band.q_sym, new_q)
            self._replace_band(band, q=new_q)
            return True
        return False

    def tick(self) -> None:
        bypassed = self.plugin.is_bypassed()
        if bypassed != getattr(self, "_last_bypassed", None):
            self._last_bypassed = bypassed
            self._graph.set_bypassed(bypassed)
            self._update_readout()
        super().tick()

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        self._graph.set_bypassed(self.plugin.is_bypassed())
        self._update_readout()

    # ── state helpers ───────────────────────────────────────────────────────

    @property
    def selected_band(self) -> Optional[BandSpec]:
        if self.sel_ref is None:
            return None
        w = self.sel_ref
        return w.band if isinstance(w, BandSelectable) else None

    def _replace_band(self, band: BandSpec, **changes) -> None:
        old = self._state.bands[band.name]
        new = replace(old, **changes)
        new_bands = dict(self._state.bands)
        new_bands[band.name] = new
        self._state = replace(self._state, bands=new_bands)
        self._graph.set_state(self._state)
        self._update_readout()

    def _update_readout(self) -> None:
        sel_w = self.sel_ref
        if isinstance(sel_w, BandSelectable):
            p = self._state.bands.get(sel_w.band.name)
            if p is None:
                self._readout.set_message("")
            else:
                name, freq, q, gain = band_readout_fields(sel_w.band, p)
                self._readout.set_fields(name, freq, q, gain)
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
        band_name = w.band.name if isinstance(w, BandSelectable) else None
        self._graph.set_selected(band_name)
        self._update_readout()

    # ── band-selectable callbacks ───────────────────────────────────────────

    def _toggle_band_enable(self, band: BandSpec) -> None:
        if band.enable_sym is None:
            return
        p = self._state.bands[band.name]
        new_enabled = not p.enabled
        self.set_param(band.enable_sym, 1.0 if new_enabled else 0.0)
        self._replace_band(band, enabled=new_enabled)

    def _reset_band_to_snapshot(self, band: BandSpec) -> None:
        snap = self.plugin.pedalboard_snapshot
        for symbol in (band.enable_sym, band.freq_sym, band.q_sym):
            if symbol is None:
                continue
            if symbol in snap and not self._is_symbol_locked(self.plugin.instance_id, symbol):
                self.set_param(symbol, snap[symbol])
        if band.gain_sym is not None and band.gain_sym in snap:
            if not self._is_symbol_locked(self.plugin.instance_id, band.gain_sym):
                self.set_param(band.gain_sym, snap[band.gain_sym])
        self.apply_state(self.snapshot_state())
