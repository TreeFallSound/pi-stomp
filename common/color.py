"""Color types shared across the codebase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uilib.paint import ColorLike

ColorRGB = tuple[int, int, int]


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
