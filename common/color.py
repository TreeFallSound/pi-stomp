"""Color types shared across the codebase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uilib.paint import ColorLike

ColorRGB = tuple[int, int, int]

SELECT_COLOR: ColorRGB = (255, 255, 0)

# ── Plugin category colors ─────────────────────────────────────────────
# Two distinct maps for two distinct surfaces. The accent map drives the
# LED strip and dialog title-bar tinting; the tile map drives on-screen
# plugin tiles (brighter for the 320x240 LCD).

ACCENT_DEFAULT_COLOR: ColorRGB = (80, 80, 80)

ACCENT_CATEGORY_COLORS: dict[str, ColorRGB] = {
    "Delay": (199, 21, 133),
    "Distortion": (0, 176, 0),
    "Dynamics": (200, 80, 0),
    "Filter": (170, 140, 0),
    "Generator": (75, 0, 130),
    "Midiutility": (200, 200, 200),
    "Modulator": (50, 50, 255),
    "Reverb": (20, 140, 180),
    "Simulator": (139, 69, 19),
    "Spacial": (128, 128, 128),
    "Spectral": (230, 0, 0),
    "Utility": (200, 200, 200),
}

TILE_DEFAULT_COLOR: ColorRGB = (192, 192, 192)  # "Silver"

TILE_CATEGORY_COLORS: dict[str, ColorRGB] = {
    "Delay": (199, 21, 133),
    "Distortion": (0, 255, 0),
    "Dynamics": (255, 69, 0),
    "Filter": (205, 133, 40),
    "Generator": (75, 0, 130),
    "Midiutility": (128, 128, 128),
    "Modulator": (50, 50, 255),
    "Reverb": (20, 160, 255),
    "Simulator": (139, 69, 19),
    "Spacial": (128, 128, 128),
    "Spectral": (255, 0, 0),
    "Utility": (128, 128, 128),
}


def accent_color_for(category: str | None) -> ColorRGB:
    """LED-strip / dialog-accent color for *category*, falling back to ACCENT_DEFAULT_COLOR."""
    if category is None:
        return ACCENT_DEFAULT_COLOR
    return ACCENT_CATEGORY_COLORS.get(category, ACCENT_DEFAULT_COLOR)


def tile_color_for(category: str | None) -> ColorRGB:
    """LCD tile-fill color for *category*, falling back to TILE_DEFAULT_COLOR."""
    if category is None:
        return TILE_DEFAULT_COLOR
    return TILE_CATEGORY_COLORS.get(category, TILE_DEFAULT_COLOR)


@dataclass(frozen=True)
class RectBorder:
    """Per-side border colors.

    Each side is optional. A ``None`` side is omitted from the rendered
    border. Corner arcs take the color of the meeting horizontal edge —
    top for the top corners, bottom for the bottom corners — falling back
    to the vertical edge if the horizontal is unset.

    Colors are typed as ``ColorLike`` so callers can pass through 4-tuples
    (RGBA) when targeting alpha-aware surfaces; the actual renderer only
    consumes RGB but accepts the wider type for symmetry with paint.py.
    """

    top: "ColorLike | None" = None
    right: "ColorLike | None" = None
    bottom: "ColorLike | None" = None
    left: "ColorLike | None" = None
