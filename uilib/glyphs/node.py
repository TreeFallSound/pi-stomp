"""The value-handle "node": a filled circle that punches through whatever bar or
curve it sits on, with an optional selection halo.

Shared by every control that marks a value on a track — parametric/graphic EQ
band nodes, the parameter-window handle, and the mixer's fader/pan handles — so
they read as one visual language. Pure ``uilib`` (no panel deps) so any of them
can import it without coupling to another's module.
"""

from __future__ import annotations

from uilib.glyphs.circle import CircleGlyph, RingGlyph
from uilib.glyphs.tint import tint_mask

NODE_R = 4
HALO_R = 6
HALO_COLOR = (255, 255, 255)

_ERASER_COLOR = (0, 0, 0)


def paint_band_node(ctx, cx: int, cy: int, color: tuple[int, int, int], selected: bool) -> None:
    """Paint the node circle (black eraser, coloured fill, optional halo)."""
    eraser = CircleGlyph(NODE_R + 2)
    ctx.paste(tint_mask(eraser.render(), _ERASER_COLOR), (cx - eraser.radius, cy - eraser.radius))
    node = CircleGlyph(NODE_R)
    ctx.paste(tint_mask(node.render(), color), (cx - node.radius, cy - node.radius))
    if selected:
        halo = RingGlyph(HALO_R)
        ctx.paste(tint_mask(halo.render(), HALO_COLOR), (cx - halo.half_size, cy - halo.half_size))
