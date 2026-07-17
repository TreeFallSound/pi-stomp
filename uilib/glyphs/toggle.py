"""ToggleGlyph: a filled rounded-rect chip with a single character centered
inside — the S/M/A-style toggle marker. Like BadgeGlyph, the character is baked
into the pixels (it can't be tinted at blit time), so the chip is cached per
(char, size, colors). The letter is rendered supersampled and Lanczos-downscaled
so its strokes stay crisp at this radius; the rounded-rect body underneath is
itself cached by RoundedRectGlyph, so a draw is a single dict lookup."""

from functools import lru_cache

import pygame
from PIL import Image

from common.color import ColorRGB, RectBorder
from uilib.config import Config, FontName
from uilib.glyphs.rounded_rect import RoundedRectGlyph
from uilib.misc import get_text_size
from uilib.radius import Radius

# Supersample factor for the text layer only: render the glyph at _SS× size,
# then downscale, so its edges resolve to sub-pixel accuracy instead of
# rounding to whole pixels. Cached per chip, so it costs nothing at draw time.
_SS = 4


def _lanczos_downscale(surf: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    # pygame.transform has no Lanczos filter — smoothscale/rotozoom are both
    # box/bilinear and visibly blur glyph strokes at this radius. Route
    # through Pillow (already a dependency) for a sharper resample.
    img = Image.frombytes("RGBA", surf.get_size(), pygame.image.tobytes(surf, "RGBA"))
    img = img.resize(size, Image.Resampling.LANCZOS)
    return pygame.image.frombytes(img.tobytes(), size, "RGBA")


@lru_cache(maxsize=64)
def _toggle_surface(
    char: str,
    width: int,
    height: int,
    radius: int,
    fill: ColorRGB | None,
    text_color: ColorRGB,
    outline: ColorRGB | None,
    border_width: int,
    font_name: FontName,
) -> pygame.Surface:
    border = RectBorder(top=outline, right=outline, bottom=outline, left=outline) if outline is not None else None
    # copy: the RoundedRectGlyph surface is shared from its own cache — don't
    # bake the letter into it.
    surf = RoundedRectGlyph(
        width, height, Radius.uniform(radius), fill=fill, border=border, border_width=border_width,
    ).render().copy()

    font = Config().get_font(font_name)
    if font is None or not char:
        return surf
    base_size = font.size if isinstance(font.size, (int, float)) else font.size[0]
    big_size = base_size * _SS
    tw, th = get_text_size(char, font, size=big_size)
    asc = int(font.get_sized_ascender(big_size))

    layer = pygame.Surface((width * _SS, height * _SS), pygame.SRCALPHA)
    prev = font.origin
    font.origin = True
    try:
        x = (width * _SS - tw) // 2
        y = (height * _SS - th) // 2 + asc
        font.render_to(layer, (x, y), char, fgcolor=text_color + (255,), size=big_size)  # pyright: ignore[reportCallIssue]
    finally:
        font.origin = prev
    surf.blit(_lanczos_downscale(layer, (width, height)), (0, 0))
    return surf


class ToggleGlyph:
    """`Glyph`-shaped (width/height/render()): a rounded chip with `char`
    centered in it. Cheap to construct per draw — the pixels are cached by
    `_toggle_surface`."""

    def __init__(
        self,
        char: str,
        *,
        width: int,
        height: int,
        fill: ColorRGB,
        text_color: ColorRGB,
        radius: int = 3,
        outline: ColorRGB | None = None,
        border_width: int = 1,
        font_name: FontName = "tiny",
    ) -> None:
        self._char = char
        self._w = int(width)
        self._h = int(height)
        self._radius = radius
        self._fill = fill
        self._text_color = text_color
        self._outline = outline
        self._border_width = border_width
        self._font_name = font_name

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h

    def render(self) -> pygame.Surface:
        return _toggle_surface(
            self._char, self._w, self._h, self._radius, self._fill,
            self._text_color, self._outline, self._border_width, self._font_name,
        )
