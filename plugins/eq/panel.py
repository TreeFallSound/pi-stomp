"""Full-screen EQ panel for fil4 / x42-eq.

Built on top of PluginPanel[EqState]; the base class provides the chrome
row (Back / Bypass / Reset), param coalescing, and InputSink wiring.
The subclass owns the graph, readout, band selectables, and tweak mapping.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Optional

import numpy as np

from plugins.base import PluginPanel
from plugins import register_panel
from plugins.eq import FIL4_URIS
from plugins.eq.bands import BANDS, BAND_COLORS, Band, PLUGIN_ENABLE_SYM
from plugins.eq.curve import (
    GRAPH_FREQS,
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
from uilib.misc import InputEvent, get_text_size
from uilib.panel import Panel
from uilib.text import Button
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
# Line thickness in pixels, measured PERPENDICULAR to the curve. The vertical
# extent painted at each column is CURVE_THICKNESS * sqrt(1 + slope²), so the
# perceived weight stays constant regardless of slope.
CURVE_THICKNESS = 1.3
HALO_COLOR = (255, 255, 255)
READOUT_COLOR = (200, 200, 200)
INACTIVE_SHADE = 0.45

# "Comet tail" smear under the curve.
# Per-column intensity = clip(|db| / DB_MAX, 0, 1). The tail extends from the
# curve toward the 0 dB line — so it always points at zero — and its on-screen
# length equals the distance from the curve to that line (which is itself
# proportional to |db|). Top-pixel opacity scales with intensity, fading
# linearly to 0 at the zero line.
SMEAR_ALPHA = 0.65
# Visual cap on tail length in pixels. HP/LP curves park entire spans near
# ±DB_MAX where the full curve-to-zero distance is half the graph height —
# uncapped that's ~28k Python-level pixel writes per frame. Capping at 60 px
# clips the perceptually-uninteresting middle of the tail without changing
# the apparent intensity at the curve.
SMEAR_LENGTH_MAX = 60


# ── grid helpers ─────────────────────────────────────────────────────────────

# Gridlines are linearly evenly spaced in pixel x. The graph's mapping
# from x to frequency is logarithmic (see freq_to_x), so each major x
# corresponds to whatever frequency lands there — we label that value
# rather than picking round Hz numbers.
_FREQ_MAJOR_STEP_PX = 80  # majors at x = 80, 160, 240
_FREQ_MINOR_STEP_PX = 40  # minors at x = 40, 120, 200, 280
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

# (label, x_of_gridline) for every vertical gridline. Only the leftmost
# (20 Hz) carries the "Hz" suffix; the rest read as bare numbers / "Xk".
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


# ── smear (comet-tail) helpers ──────────────────────────────────────────────


def _smear_colors_for_state(state: EqState) -> Optional[np.ndarray]:
    """RGB color per graph column, ease-in-out interpolated across the x
    positions of currently-enabled bands. Returns (GRAPH_W, 3) float array,
    or None if no bands are enabled (no smear)."""
    anchors: list[tuple[int, tuple[int, int, int]]] = []
    for band in BANDS:
        p = state.bands.get(band.name)
        if p is None or not p.enabled:
            continue
        anchors.append((int(freq_to_x(p.freq)), BAND_COLORS[band.name]))
    if not anchors:
        return None
    anchors.sort(key=lambda t: t[0])
    xs = np.array([a[0] for a in anchors], dtype=int)
    cs = np.array([a[1] for a in anchors], dtype=float)
    all_x = np.arange(GRAPH_W)
    if len(xs) == 1:
        out = np.broadcast_to(cs[0], (GRAPH_W, 3)).copy()
        return out
    # For each column, find the bracketing pair [xs[i-1], xs[i]] and smoothstep
    # between their colors. Outside the anchor range, clamp to the edge color.
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
    """Per-column intensity in [0, 1] = clip(|db| / DB_MAX). Drives both
    tail opacity and (via the curve-to-zero distance) length."""
    return np.clip(np.abs(curve_db) / DB_MAX, 0.0, 1.0)


# ── GraphWidget ──────────────────────────────────────────────────────────────


class GraphWidget(Widget):
    """Owns the curve, grid and band nodes.

    State-change setters (`set_state`, `set_selected`, `set_bypassed`) compute
    the dirty x-extent against cached previous state and call `self.refresh`
    with only that sub-box; `_draw` paints from-scratch but clips work to the
    requested `real_box` so only changed columns are touched (and only those
    columns are flushed over SPI by the panel stack).

    Assumes the widget spans the full panel width with image x == local x
    (same convention used by TunerPanel's widgets).
    """

    NODE_R = 3
    HALO_R = 6

    def __init__(self, box: Box, axis_font=None, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._axis_font = axis_font
        self._cache = CurveCache()
        self._state: Optional[EqState] = None
        self._selected_band: Optional[str] = None
        self._curve_y: Optional[np.ndarray] = None
        self._curve_y_float: Optional[np.ndarray] = None
        # Per-column y range covered by the polyline's half-segments to each
        # neighbour — used by the AA rasterizer to spread ink across rows
        # in proportion to the slope at that column.
        self._curve_y_lo: Optional[np.ndarray] = None
        self._curve_y_hi: Optional[np.ndarray] = None
        self._node_positions: dict[str, _NodePos] = {}
        self._bypassed: bool = False
        self._smear_colors: Optional[np.ndarray] = None  # (GRAPH_W, 3) or None
        self._smear_intensity: Optional[np.ndarray] = None  # (GRAPH_W,) floats in [0, 1]

    # ── state setters (self-refresh with surgical sub-box) ──────────────────

    def set_state(self, state: EqState) -> None:
        new_curve_db = self._cache.compute(state)
        new_curve_y_float = db_to_y_float(new_curve_db, GRAPH_Y0, GRAPH_Y1, DB_MAX)
        new_curve_y = np.round(new_curve_y_float).astype(int)
        new_y_lo, new_y_hi = self._neighbor_extents(new_curve_y_float)
        new_nodes = self._compute_nodes(state)
        new_smear_colors = _smear_colors_for_state(state)
        new_smear_intensity = _smear_intensity_from_db(new_curve_db)

        old_curve = self._curve_y
        old_nodes = self._node_positions
        old_smear_colors = self._smear_colors
        old_smear_intensity = self._smear_intensity

        self._state = state

        if old_curve is None:
            # First paint: commit everything, refresh handled by panel.refresh().
            self._curve_y = new_curve_y
            self._curve_y_float = new_curve_y_float
            self._curve_y_lo = new_y_lo
            self._curve_y_hi = new_y_hi
            self._node_positions = new_nodes
            self._smear_colors = new_smear_colors
            self._smear_intensity = new_smear_intensity
            return

        x_min, x_max = self._dirty_extent_for_curve(old_curve, new_curve_y)
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
            # No dirty columns — keep the committed/displayed arrays as-is so
            # the next diff compares against what's actually on screen. This
            # lets sub-threshold smear drift accumulate over many tweaks
            # until it eventually crosses the visibility threshold.
            return

        self._curve_y = new_curve_y
        self._curve_y_float = new_curve_y_float
        self._curve_y_lo = new_y_lo
        self._curve_y_hi = new_y_hi
        self._node_positions = new_nodes
        self._smear_colors = new_smear_colors
        self._smear_intensity = new_smear_intensity
        self._refresh_x_range(x_min, x_max)

    def set_selected(self, band_name: Optional[str]) -> None:  # type: ignore[override]
        if band_name == self._selected_band:
            return
        old = self._selected_band
        self._selected_band = band_name

        x_min: Optional[int] = None
        x_max: Optional[int] = None
        for name in (old, band_name):
            ext = self._node_x_extent(name)
            if ext is None:
                continue
            nx0, nx1 = ext
            x_min = nx0 if x_min is None else min(x_min, nx0)
            x_max = nx1 if x_max is None else max(x_max, nx1)
        self._refresh_x_range(x_min, x_max)

    def set_bypassed(self, bypassed: bool) -> None:
        if self._bypassed == bypassed:
            return
        self._bypassed = bypassed
        self.refresh()  # curve colour shifts globally — repaint everything

    # ── dirty-extent helpers ────────────────────────────────────────────────

    @staticmethod
    def _dirty_extent_for_curve(
        old: np.ndarray,
        new: np.ndarray,
    ) -> tuple[Optional[int], Optional[int]]:
        diff = np.flatnonzero(old != new)
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
        # Sub-perceptual tolerances. Threshold intensity at ~1 LSB of a
        # blended 8-bit channel (≈ 1/255 of top alpha) and ~2 LSBs of an
        # 8-bit colour channel.
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
        node_r = self.HALO_R + 1
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
        node_r = self.HALO_R + 1
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
        """For each column, the y range covered by the polyline's two
        half-segments to the immediate neighbours (column-centre to
        midpoint with the next/prev column). Returns (y_lo, y_hi)."""
        mids = (ys_f[:-1] + ys_f[1:]) * 0.5
        y_left = np.empty_like(ys_f)
        y_right = np.empty_like(ys_f)
        y_left[0] = ys_f[0]
        y_left[1:] = mids
        y_right[:-1] = mids
        y_right[-1] = ys_f[-1]
        return np.minimum(y_left, y_right), np.maximum(y_left, y_right)

    @staticmethod
    def _compute_nodes(state: EqState) -> dict[str, _NodePos]:
        out: dict[str, _NodePos] = {}
        for band in BANDS:
            p = state.bands.get(band.name)
            if p is None:
                continue
            cx = int(freq_to_x(p.freq))
            cy = _ZERO_DB_Y if band.gain_sym is None else _db_to_y_scalar(p.gain_db)
            color: tuple[int, int, int] = BAND_COLORS[band.name] if p.enabled else (80, 80, 80)
            out[band.name] = (cx, cy, color, p.enabled)
        return out

    # ── paint ───────────────────────────────────────────────────────────────

    def _draw_erase(self, ctx) -> None:
        pass  # _draw handles its own background, clipped to dirty_bounds

    def _draw(self, ctx) -> None:
        # Widget box: Box.xywh(0, GRAPH_Y0, _W, GRAPH_H).
        # ctx coords are widget-relative: (0,0) = (0, GRAPH_Y0) in image space.
        # All image-space y values (GRAPH_Y0, _ZERO_DB_Y, etc.) must be shifted
        # by -GRAPH_Y0 to become widget-relative.
        db = ctx.dirty_bounds  # widget-relative dirty rect
        rx0, ry0 = db.x0, db.y0
        rx1, ry1 = db.x1, db.y1

        # Background fill — only the dirty rect
        ctx.draw_rectangle(db, fill=BG_BLACK)

        # Vertical grid lines that fall in [rx0, rx1)
        for x in _FREQ_GRID_X:
            if rx0 <= x < rx1:
                ctx.draw_line([(x, max(ry0, 0)), (x, min(ry1, GRAPH_H) - 1)], fill=GRID_DIM, width=1)

        # Horizontal grid lines — clip x extent to the dirty rect.
        hx0 = max(rx0, 0)
        hx1 = min(rx1, _W)
        zero_y = _ZERO_DB_Y - GRAPH_Y0  # widget-relative 0 dB line
        if hx0 < hx1:
            for db_val in _DB_GRID:
                y = _db_to_y_scalar(db_val) - GRAPH_Y0
                ctx.draw_line([(hx0, y), (hx1 - 1, y)], fill=GRID_DIM, width=1)
            ctx.draw_line([(hx0, zero_y), (hx1 - 1, zero_y)], fill=GRID_0DB, width=1)

        # Curve + comet-tail smear — only columns within the dirty rect.
        # Smear paints first (so curve and nodes land on top); each smear
        # pixel is alpha-blended against bg_color(x, y) so grid lines bleed
        # through the tail rather than getting erased.
        if self._curve_y is not None:
            shade = INACTIVE_SHADE if self._bypassed else 1.0
            curve_color = tuple(int(c * shade) for c in CURVE_COLOR)
            cx0 = max(rx0, 0)
            cx1 = min(rx1, GRAPH_W)
            ys = self._curve_y
            ys_f = self._curve_y_float
            y_lo = self._curve_y_lo
            y_hi = self._curve_y_hi
            smear_colors = self._smear_colors
            smear_intensity = self._smear_intensity
            has_smear = smear_colors is not None and smear_intensity is not None
            cr, cg, cb = curve_color
            # _ZERO_DB_Y is in image space; convert to widget-relative float
            yz = float(_ZERO_DB_Y - GRAPH_Y0)
            ox, oy = ctx._f().topleft
            surf = ctx.surface
            for x in range(cx0, cx1):
                # ys[x] is in image-space; widget-relative = ys[x] - GRAPH_Y0
                base_y = int(ys[x]) - GRAPH_Y0
                if has_smear and ys_f is not None:
                    # ys_f[x] is image-space float; convert to widget-relative
                    yf = float(ys_f[x]) - GRAPH_Y0
                    raw_length = abs(yz - yf)
                    # Cap the on-screen tail so HP/LP doesn't blow up the per-
                    # frame pixel-write count. The opacity ramp still falls
                    # linearly to 0 over `length` — we just truncate the tail
                    # before it reaches zero when the curve sits far away.
                    length = raw_length if raw_length < SMEAR_LENGTH_MAX else float(SMEAR_LENGTH_MAX)
                    intensity = float(smear_intensity[x])  # type: ignore[index]
                    if length >= 0.5 and intensity > 0.0:
                        sr, sg, sb = smear_colors[x]  # type: ignore[index]
                        sr *= shade
                        sg *= shade
                        sb *= shade
                        top_alpha = SMEAR_ALPHA * intensity
                        # Linear opacity ramp from top_alpha at the curve to 0
                        # at distance `length` from the curve, in the
                        # direction of the 0 dB line (boost: downward; cut:
                        # upward). Per-row alpha is the integral over [R, R+1]
                        # of α(u) = top_alpha · (1 − u/length).
                        if yf <= yz:
                            y_top = yf
                            y_bot = yf + length
                        else:
                            y_top = yf - length
                            y_bot = yf
                        inv_2len = 0.5 / length
                        R = int(math.floor(y_top))
                        R_end = int(math.floor(y_bot))
                        while R <= R_end and R < GRAPH_H:
                            a = float(R) if float(R) > y_top else y_top
                            b = float(R + 1) if float(R + 1) < y_bot else y_bot
                            if b > a and R >= 0:
                                if yf <= yz:
                                    u_a = a - yf
                                    u_b = b - yf
                                else:
                                    u_a = yf - b
                                    u_b = yf - a
                                alpha = top_alpha * ((u_b - u_a) - (u_b * u_b - u_a * u_a) * inv_2len)
                                if alpha > 0.0:
                                    # bg_color uses image-space x,y
                                    br, bg_, bb = bg_color(x, R + GRAPH_Y0)
                                    surf.set_at(
                                        (x + ox, R + oy),
                                        (
                                            int(br + (sr - br) * alpha),
                                            int(bg_ + (sg - bg_) * alpha),
                                            int(bb + (sb - bb) * alpha),
                                        ),
                                    )
                            R += 1
                # Analytical line rasterization for column x. The line is
                # treated as having unit thickness PERPENDICULAR to its
                # direction; projected onto the column that's a vertical
                # extent of sqrt(1 + slope²) centred on the column's mean y.
                # Each row's coverage is its overlap with that extent (capped
                # at 1), so fully-crossed rows always sit at full alpha and
                # steep slopes don't visually thin out. Each pixel is then
                # alpha-blended against bg_color so the grid bleeds through.
                if y_lo is not None and y_hi is not None:
                    # y_lo/y_hi are image-space floats; convert to widget-relative
                    yl = float(y_lo[x]) - GRAPH_Y0
                    yh = float(y_hi[x]) - GRAPH_Y0
                    mid = (yl + yh) * 0.5
                    half_extent = math.sqrt(1.0 + (yh - yl) ** 2) * (CURVE_THICKNESS * 0.5)
                    y_lo_ext = mid - half_extent
                    y_hi_ext = mid + half_extent
                    r_lo = int(math.floor(y_lo_ext))
                    r_hi = int(math.floor(y_hi_ext))
                    for ry in range(r_lo, r_hi + 1):
                        if ry < 0 or ry >= GRAPH_H:
                            continue
                        overlap = min(ry + 1, y_hi_ext) - max(ry, y_lo_ext)
                        if overlap <= 0.0:
                            continue
                        a = overlap if overlap < 1.0 else 1.0
                        # bg_color uses image-space coords
                        br, bg_, bb = bg_color(x, ry + GRAPH_Y0)
                        surf.set_at(
                            (x + ox, ry + oy),
                            (
                                int(br + (cr - br) * a),
                                int(bg_ + (cg - bg_) * a),
                                int(bb + (cb - bb) * a),
                            ),
                        )
                else:
                    surf.set_at((x + ox, base_y + oy), curve_color)

        # Band nodes — skip those whose bbox misses the dirty rect.
        # Draw selected last so the halo lands on top.
        if self._state is not None and self._node_positions:
            node_r = self.HALO_R + 1
            ordered: list[Band] = [b for b in BANDS if b.name != self._selected_band]
            sel = next((b for b in BANDS if b.name == self._selected_band), None)
            if sel is not None:
                ordered.append(sel)
            for band in ordered:
                pos = self._node_positions.get(band.name)
                if pos is None:
                    continue
                cx, cy, color, _enabled = pos
                if cx + node_r <= rx0 or cx - node_r >= rx1:
                    continue
                # cx, cy are image-space; convert cy to widget-relative
                self._paint_node(ctx, cx, cy - GRAPH_Y0, color, band.name == self._selected_band)

        # Axis labels (small font). Clipped to the dirty rect so they only
        # repaint when their columns are part of the refresh.
        if self._axis_font is not None:
            self._paint_axis_labels(ctx, rx0, rx1)

    def _paint_axis_labels(self, ctx, rx0: int, rx1: int) -> None:
        font = self._axis_font
        # dB labels at the left edge (widget-relative y coords).
        for text, db_val in _DB_LABELS:
            tw, th = get_text_size(text, font)
            x = 2
            if x + tw <= rx0 or x >= rx1:
                continue
            y = _db_to_y_scalar(db_val) - GRAPH_Y0  # widget-relative
            if db_val > 0:
                ty = y + 1
            else:
                ty = y - th - 1
            ctx.draw_text((x, ty), text, fill=_AXIS_LABEL_COLOR, font=font)
        # Freq labels along the bottom, placed to the right of each major
        # gridline so the line itself stays unobscured.
        for text, fx in _FREQ_LABELS:
            tw, th = get_text_size(text, font)
            tx = fx + 2
            if tx + tw <= rx0 or tx >= rx1:
                continue
            ty = GRAPH_H - th - 1  # widget-relative bottom
            ctx.draw_text((tx, ty), text, fill=_AXIS_LABEL_COLOR, font=font)

    def _paint_node(self, ctx, cx: int, cy: int, color: tuple[int, int, int], selected: bool) -> None:
        r = self.NODE_R
        # 2px black ring sits between the coloured node (r=3) and the halo
        # (inner edge r=5). Painting it for every band turns the previously
        # transparent gap into a solid outline; for the selected band the
        # halo lands flush on top of it.
        ctx.draw_ellipse(Box(cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=BG_BLACK)
        ctx.draw_ellipse(Box(cx - r, cy - r, cx + r, cy + r), fill=color)
        if selected:
            hr = self.HALO_R
            ctx.draw_ellipse(Box(cx - hr, cy - hr, cx + hr, cy + hr), outline=HALO_COLOR, width=1)


# ── ReadoutWidget ────────────────────────────────────────────────────────────


# Top-row column anchors. Left-anchored columns (name/freq/Q) place their
# left edge at the given x; the gain column is right-anchored — its right
# edge sits at `_READOUT_GAIN_RIGHT` (px from panel left), so values like
# "+18.0 dB" / "disabled" line up flush with the right side of the LCD.
_READOUT_COLS_LEFT: tuple[tuple[str, int], ...] = (
    ("name", 6),
    ("freq", 60),
    ("q", 160),
)
_READOUT_GAIN_RIGHT: int = _W - 6  # 6 px from the right edge


class ReadoutWidget(Widget):
    """Top-bar with statically-positioned name / freq / Q / gain columns.
    Each column is independently set via `set_field`; only changed columns
    re-render. Free-form text (chrome hints) uses `set_message` instead."""

    def __init__(self, box: Box, font, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", BG_BLACK)
        super().__init__(box=box, **kwargs)
        self._font = font
        self._fields: dict[str, str] = {k: "" for k, _ in _READOUT_COLS_LEFT}
        self._fields["gain"] = ""
        self._message: Optional[str] = None  # if set, replaces field layout

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


class _BandSelectable(Widget):
    """Nav-cycle target with no visual presence of its own — the band's
    coloured circle on the graph is the indicator (halo when selected)."""

    def __init__(self, panel: "EqPanel", band: Band) -> None:
        super().__init__(box=Box.xywh(0, 0, 1, 1), parent=panel, visible=True)
        self._panel = panel
        self.band = band

    def set_selected(self, selected: bool) -> None:  # type: ignore[override]
        self.selected = selected
        # Halo and readout updates are driven by EqPanel._select_widget_idx
        # so chrome focus correctly clears the previously-selected band.

    def input_event(self, event) -> bool:  # type: ignore[override]
        if event == InputEvent.CLICK:
            self._panel._on_band_click(self.band)
            return True
        if event == InputEvent.LONG_CLICK:
            self._panel._on_band_long(self.band)
            return True
        return False

    def scroll_into_view(self) -> bool:
        return False

    def _draw(self, ctx) -> None:
        pass

    def _draw_erase(self, ctx) -> None:
        pass

    def _draw_selection(self, ctx) -> None:
        # Suppress the base Widget's selection rectangle — our visual is the
        # halo painted by the GraphWidget on the band's node. Without this
        # override, the 1×1 widget box would paint a tiny selection square at
        # (0,0) on first paint.
        pass


# ── readout formatting ──────────────────────────────────────────────────────


def _fmt_freq(hz: float) -> str:
    if hz >= 1000.0:
        return f"{hz / 1000.0:.2f} kHz"
    return f"{hz:.0f} Hz"


def _band_readout_fields(band: Band, p: BandParams) -> tuple[str, str, str, str]:
    name = band.name
    freq = _fmt_freq(p.freq)
    q = f"Q {p.q:.2f}"
    if not p.enabled:
        gain = "disabled"
    elif band.gain_sym is None:
        gain = "—"
    else:
        gain = f"{p.gain_db:+.1f} dB"
    return name, freq, q, gain


# ── tweak step sizes ────────────────────────────────────────────────────────

_GAIN_STEP_DB = 0.5
_FREQ_STEP = 2.0 ** (1.0 / 12.0)  # one semitone per click
_Q_STEP = 0.05

# Speed multipliers mirror EncoderController.refresh — keep behaviour
# consistent between MIDI-bound use and panel-bound use.
_FAST_THRESHOLD = 4
_MEDIUM_THRESHOLD = 2
_FAST_MULT = 8
_MEDIUM_MULT = 4


def _speed_multiplier(rotations: int) -> int:
    n = abs(rotations)
    if n >= _FAST_THRESHOLD:
        return _FAST_MULT
    if n >= _MEDIUM_THRESHOLD:
        return _MEDIUM_MULT
    return 1


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── EqPanel ──────────────────────────────────────────────────────────────────


@register_panel(*FIL4_URIS)
class EqPanel(PluginPanel[EqState]):
    """Full-screen panel for editing an x42-eq instance."""

    # ── PluginPanel subclass contract ────────────────────────────────────────

    def snapshot_state(self) -> EqState:
        """Construct EqState from the current plugin.parameters values."""
        params = self.plugin.parameters

        def _val(symbol: str, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None and p.value is not None else default

        bands: dict[str, BandParams] = {}
        for band in BANDS:
            bands[band.name] = BandParams(
                enabled=bool(_val(band.enable_sym, 0.0)),
                freq=_val(band.freq_sym, 0.5 * (band.freq_min + band.freq_max)),
                q=_val(band.q_sym, 0.7),
                gain_db=_val(band.gain_sym, 0.0) if band.gain_sym else 0.0,
            )
        return EqState(
            plugin_enabled=bool(_val(PLUGIN_ENABLE_SYM, 1.0)),
            global_gain_db=_val("gain", 0.0),
            bands=bands,
        )

    def apply_state(self, state: EqState) -> None:
        self._state = state
        self._graph.set_state(state)
        self._update_readout()

    def build_widgets(self) -> None:
        # Snapshot state early so add_sel_widget → _select_widget_idx → _update_readout
        # can read it when the first band selectable is registered.
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
            axis_font=axis_font,
            parent=self,
        )

        # Band selectables first (Nav cycles bands → chrome → bands → ...)
        self._band_sels: dict[str, _BandSelectable] = {}
        for band in BANDS:
            sel = _BandSelectable(self, band)
            self._band_sels[band.name] = sel
            self.add_sel_widget(sel)

        # Initial paint: apply starting state and select first band.
        # set_bypassed must run before set_state so the very first curve
        # render uses the dimmed shade when we open already-bypassed.
        self._graph.set_bypassed(self.plugin.is_bypassed())
        self.apply_state(self.snapshot_state())
        self.sel_widget(self._band_sels[BANDS[0].name])

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id not in (1, 2, 3) or rotations == 0:
            return False
        band = self.selected_band
        if band is None:
            # Chrome selected: consume Tweak1/2 silently, let Tweak3 (volume)
            # fall through to normal handler dispatch.
            return encoder_id != 3
        delta = rotations * _speed_multiplier(rotations)
        p = self._state.bands[band.name]
        if encoder_id == 1:
            if band.gain_sym is None:
                return True  # HP/LP: consume but no-op
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
            new_q = _clip(p.q + delta * _Q_STEP, band.q_min, band.q_max)
            if new_q == p.q:
                return True
            self.set_param(band.q_sym, new_q)
            self._replace_band(band, q=new_q)
            return True
        return False

    # ── tick: drain coalesce queue + react to external bypass changes ──────

    def tick(self) -> None:
        # Mirror external bypass changes (footswitch, MOD-UI) into the graph.
        bypassed = self.plugin.is_bypassed()
        if bypassed != getattr(self, "_last_bypassed", None):
            self._last_bypassed = bypassed
            self._graph.set_bypassed(bypassed)
            self._update_readout()
        super().tick()

    # ── bypass style override (base calls this on toggle) ────────────────────

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        self._graph.set_bypassed(self.plugin.is_bypassed())
        self._update_readout()

    # ── state helpers ───────────────────────────────────────────────────────

    @property
    def selected_band(self) -> Optional[Band]:
        if self.sel_ref is None:
            return None
        w = self.sel_ref
        return w.band if isinstance(w, _BandSelectable) else None

    def _replace_band(self, band: Band, **changes) -> None:
        old = self._state.bands[band.name]
        new = replace(old, **changes)
        new_bands = dict(self._state.bands)
        new_bands[band.name] = new
        self._state = replace(self._state, bands=new_bands)
        self._graph.set_state(self._state)
        self._update_readout()

    def _update_readout(self) -> None:
        sel_w = self.sel_ref
        if isinstance(sel_w, _BandSelectable):
            p = self._state.bands.get(sel_w.band.name)
            if p is None:
                self._readout.set_message("")
            else:
                name, freq, q, gain = _band_readout_fields(sel_w.band, p)
                self._readout.set_fields(name, freq, q, gain)
        elif sel_w is self._btn_bypass:
            self._readout.set_message("Plugin bypassed" if self.plugin.is_bypassed() else "Bypass plugin")
        elif sel_w is self._btn_back:
            self._readout.set_message("Close EQ")
        elif sel_w is self._btn_reset:
            self._readout.set_message("Reset to pedalboard")
        else:
            self._readout.set_message("")

    # ── selection routing ───────────────────────────────────────────────────

    def _select_widget_ref(self, w):  # type: ignore[override]
        super()._select_widget_ref(w)
        band_name = w.band.name if isinstance(w, _BandSelectable) else None
        self._graph.set_selected(band_name)
        self._update_readout()

    # ── band-selectable callbacks ───────────────────────────────────────────

    def _on_band_click(self, band: Band) -> None:
        p = self._state.bands[band.name]
        new_enabled = not p.enabled
        self.set_param(band.enable_sym, 1.0 if new_enabled else 0.0)
        self._replace_band(band, enabled=new_enabled)

    def _on_band_long(self, band: Band) -> None:
        """Reset this band to the pedalboard snapshot, skipping locked symbols."""
        snap = self.plugin.pedalboard_snapshot
        for symbol in (band.enable_sym, band.freq_sym, band.q_sym):
            if symbol in snap and not self._is_symbol_locked(self.plugin.instance_id, symbol):
                self.set_param(symbol, snap[symbol])
        if band.gain_sym is not None and band.gain_sym in snap:
            if not self._is_symbol_locked(self.plugin.instance_id, band.gain_sym):
                self.set_param(band.gain_sym, snap[band.gain_sym])
        self.apply_state(self.snapshot_state())

    # ── EqState from flat snapshot (used by _on_band_long fallback) ────────

    def _band_params_from_snapshot(self, band: Band) -> BandParams | None:
        snap = self.plugin.pedalboard_snapshot
        en = snap.get(band.enable_sym)
        fr = snap.get(band.freq_sym)
        qv = snap.get(band.q_sym)
        if en is None or fr is None or qv is None:
            return None
        gain = snap.get(band.gain_sym, 0.0) if band.gain_sym else 0.0
        return BandParams(
            enabled=bool(en),
            freq=float(fr),
            q=float(qv),
            gain_db=float(gain),
        )
