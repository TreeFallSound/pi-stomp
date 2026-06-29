"""Color types shared across the codebase."""

from __future__ import annotations

from dataclasses import dataclass

ColorRGB = tuple[int, int, int]


@dataclass(frozen=True)
class RectBorder:
    """Per-side border colors.

    Each side is optional. A ``None`` side is omitted from the rendered
    border. Corner arcs take the color of the meeting horizontal edge —
    top for the top corners, bottom for the bottom corners — falling back
    to the vertical edge if the horizontal is unset.
    """

    top: ColorRGB | None = None
    right: ColorRGB | None = None
    bottom: ColorRGB | None = None
    left: ColorRGB | None = None
