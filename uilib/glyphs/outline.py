"""Corner-tile blitters for rounded-rect outlines and fills.

Renders one small AA rounded-rect per distinct corner radius and slices the
quadrants; the cache key is per (radius, border, color), not per panel size,
so the many dialog sizes share a handful of small tiles instead of each
caching a full-size SRCALPHA mask.
"""

from __future__ import annotations

from functools import lru_cache

import pygame

from common.color import ColorRGB, RectBorder
from uilib.glyphs.rounded_rect import RoundedRectGlyph, _to_rgb
from uilib.paint import ColorLike
from uilib.radius import Radius


def _tile_size(rc: int, border_width: int) -> int:
    """Corner tile extent: the corner radius plus the border width plus 1px AA halo."""
    return max(rc, border_width) + 1


@lru_cache(maxsize=256)
def _corner_outline_tile(rc: int, border_width: int, color: ColorRGB, corner: str) -> pygame.Surface:
    """One AA corner of a border ring, for blitting at the matching panel corner.

    Renders a ``2(r+w+1)``-square uniform-radius rounded rect and slices the
    quadrant for *corner* (``"tl"``/``"tr"``/``"bl"``/``"br"``): two straight
    edges (abut the edge lines) + one AA arc.
    """
    if rc <= 0 and border_width <= 0:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    half = _tile_size(rc, border_width)
    full = half * 2
    border = RectBorder(top=color, right=color, bottom=color, left=color)
    glyph = RoundedRectGlyph(full, full, Radius.uniform(rc), fill=None, border=border, border_width=border_width)
    rendered = glyph.render()
    rects = {
        "tl": (0, 0, half, half),
        "tr": (half, 0, half, half),
        "bl": (0, half, half, half),
        "br": (half, half, half, half),
    }
    return rendered.subsurface(rects[corner]).copy()


def render_rounded_outline(
    width: int,
    height: int,
    radius: Radius | int | None,
    color: ColorLike,
    border_width: int,
) -> pygame.Surface:
    """Border-only rounded-rect outline on a transparent SRCALPHA surface.

    Interior transparent (children show through); border drawn over them.
    Straight edges are axis-aligned (no AA); corners blit cached AA tiles.
    """
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    if border_width <= 0:
        return surf
    r = Radius._coerce(radius)
    rgb = _to_rgb(color)
    assert rgb is not None, "render_rounded_outline requires a non-None color"
    tl_tile = _corner_outline_tile(r.top_left, border_width, rgb, "tl")
    tr_tile = _corner_outline_tile(r.top_right, border_width, rgb, "tr")
    bl_tile = _corner_outline_tile(r.bottom_left, border_width, rgb, "bl")
    br_tile = _corner_outline_tile(r.bottom_right, border_width, rgb, "br")
    surf.blit(tl_tile, (0, 0))
    surf.blit(tr_tile, (width - tr_tile.get_width(), 0))
    surf.blit(bl_tile, (0, height - bl_tile.get_height()))
    surf.blit(br_tile, (width - br_tile.get_width(), height - br_tile.get_height()))
    # Straight spans between corner regions; a corner occupies [0, r].
    top_len = width - r.top_left - r.top_right
    bot_len = width - r.bottom_left - r.bottom_right
    left_len = height - r.top_left - r.bottom_left
    right_len = height - r.top_right - r.bottom_right
    if top_len > 0:
        pygame.draw.line(surf, color, (r.top_left, 0), (width - r.top_right, 0), border_width)
    if bot_len > 0:
        # pygame.draw.line centers on the endpoint; land at height-bw so the
        # full thickness stays on-surface (height-1 would clip half off).
        pygame.draw.line(
            surf,
            color,
            (r.bottom_left, height - border_width),
            (width - r.bottom_right, height - border_width),
            border_width,
        )
    if left_len > 0:
        pygame.draw.line(surf, color, (0, r.top_left), (0, height - r.bottom_left), border_width)
    if right_len > 0:
        pygame.draw.line(
            surf,
            color,
            (width - border_width, r.top_right),
            (width - border_width, height - r.bottom_right),
            border_width,
        )
    return surf


def render_rounded_fill(
    width: int,
    height: int,
    radius: Radius | int | None,
    color: ColorLike,
) -> pygame.Surface:
    """Opaque rounded-rect fill on a transparent SRCALPHA surface (1px AA falloff)."""
    return RoundedRectGlyph(width, height, Radius._coerce(radius), fill=color, border=None).render()
