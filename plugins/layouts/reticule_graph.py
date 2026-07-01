from __future__ import annotations

import numpy as np
import pygame

from uilib.box import Box
from uilib.glyphs.circle import RingGlyph
from uilib.misc import INACTIVE_SHADE, get_text_size, shade_color
from uilib.widget import Widget

_GRAPH_SIDE = 188
_A_MIN = -60.0
_A_MAX = 0.0
_SPAN = _A_MAX - _A_MIN

_BG = (0, 0, 0)
_GRID = (46, 64, 54)
_FRAME = (52, 78, 64)
_UNITY = (74, 104, 84)
_CURVE = (120, 240, 150)
_RETICULE = (255, 200, 90)
_RETICULE_DIM = (150, 118, 58)
_LABEL = (150, 168, 156)
_CURVE_THICKNESS = 1.4

_GRID_DBS = tuple(range(-54, 0, 6))
_GRID_LABEL_DBS = tuple(range(-48, 0, 12))


def comp_output_db(x_db: float, thr: float, ratio: float, knee: float, makeup: float) -> float:
    if ratio <= 0:
        ratio = 1.0
    over = x_db - thr
    if knee > 0.0 and 2.0 * abs(over) <= knee:
        y = x_db + (1.0 / ratio - 1.0) * (over + knee / 2.0) ** 2 / (2.0 * knee)
    elif over <= 0.0:
        y = x_db
    else:
        y = thr + over / ratio
    return y + makeup


def _x_px(db: float) -> float:
    return (db - _A_MIN) / _SPAN * (_GRAPH_SIDE - 1)


def _y_px(db: float) -> float:
    d = max(_A_MIN, min(_A_MAX, db))
    return (_A_MAX - d) / _SPAN * (_GRAPH_SIDE - 1)


class ReticuleGraphWidget(Widget):
    def __init__(self, *, box: Box, font, parent: Widget) -> None:
        super().__init__(box=box, bkgnd_color=_BG, parent=parent, visible=True)
        self._font = font
        self._bypassed = False
        self._y_f: np.ndarray | None = None
        self._y_lo: np.ndarray | None = None
        self._y_hi: np.ndarray | None = None
        self._ret_x: int | None = None
        self._ret_y: int | None = None
        self._ret_valid = False

    def set_state(self, thr: float, ratio: float, knee: float, makeup: float) -> None:
        xs_db = _A_MIN + np.arange(_GRAPH_SIDE) / (_GRAPH_SIDE - 1) * _SPAN
        outs = np.array([comp_output_db(float(x), thr, ratio, knee, makeup) for x in xs_db])
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
        self._ret_x = int(round(_x_px(thr)))
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
        self._ret_x, self._ret_y, self._ret_valid = new_x, new_y, valid
        for x in (old_x, new_x):
            if x is not None:
                self._refresh_strip(x)

    def _refresh_strip(self, x: int) -> None:
        bx = self.box
        assert bx is not None
        self.refresh(Box(bx.x0 + x - 9, bx.y0, bx.x0 + x + 10, bx.y1))

    def _draw(self, ctx) -> None:
        shade = INACTIVE_SHADE if self._bypassed else 1.0
        db = ctx.dirty_bounds
        rx0, rx1 = db.x0, db.x1
        self._draw_grid(ctx, shade)
        self._draw_unity(ctx, shade)
        self._draw_curve(ctx, rx0, rx1, shade)
        self._draw_crosshair(ctx, shade)

    def _draw_grid(self, ctx, shade: float) -> None:
        grid = shade_color(_GRID, shade)
        label = shade_color(_LABEL, shade)
        s = _GRAPH_SIDE - 1
        for xd in _GRID_DBS:
            gx = int(round(_x_px(xd)))
            ctx.draw_line([(gx, 0), (gx, s)], fill=grid, width=1)
        for yd in _GRID_DBS:
            gy = int(round(_y_px(yd)))
            ctx.draw_line([(0, gy), (s, gy)], fill=grid, width=1)
        for xd in _GRID_LABEL_DBS:
            gx = int(round(_x_px(xd)))
            txt = f"{xd:.0f}"
            tw, _th = get_text_size(txt, self._font)
            ctx.draw_text((gx - tw // 2, s - 12), txt, fill=label, font=self._font)
        for yd in _GRID_LABEL_DBS:
            gy = int(round(_y_px(yd)))
            ctx.draw_text((2, gy - 6), f"{yd:.0f}", fill=label, font=self._font)
        frame = shade_color(_FRAME, shade)
        ctx.draw_line([(0, 0), (s, 0), (s, s), (0, s), (0, 0)], fill=shade_color(_GRID, shade), width=1)
        for cx, cy, dx, dy in ((0, 0, 1, 1), (s, 0, -1, 1), (0, s, 1, -1), (s, s, -1, -1)):
            ctx.draw_line([(cx, cy), (cx + dx * 8, cy)], fill=frame, width=1)
            ctx.draw_line([(cx, cy), (cx, cy + dy * 8)], fill=frame, width=1)

    def _draw_unity(self, ctx, shade: float) -> None:
        col = shade_color(_UNITY, shade)
        s = _GRAPH_SIDE - 1
        for x in range(0, _GRAPH_SIDE, 6):
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
            cc = np.array(shade_color(_CURVE, shade), dtype=np.float32)
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
        col = shade_color(_RETICULE if active else _RETICULE_DIM, shade)
        unity_y = int(round(_y_px(_A_MIN + x / (_GRAPH_SIDE - 1) * _SPAN)))
        if y != unity_y:
            ctx.draw_line([(x, min(unity_y, y)), (x, max(unity_y, y))], fill=shade_color(_UNITY, shade), width=1)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ctx.draw_line([(x + dx * 3, y + dy * 3), (x + dx * 8, y + dy * 8)], fill=col, width=1)
        ring = RingGlyph(6, ring_half=0.9).render()
        tinted = ring.copy()
        cs = pygame.Surface(ring.get_size(), pygame.SRCALPHA)
        cs.fill(col)
        tinted.blit(cs, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        ctx.paste(tinted, (x - 7, y - 7))
