# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Idempotent pygame + pygame._freetype initialization.

Use pygame._freetype (the C extension) rather than pygame.freetype: the public
pygame.freetype module triggers a circular import with pygame.font on Python
3.14 / pygame 2.6.1.
"""

import os

_initialized = False


def init(headless: bool = True):
    global _initialized
    if _initialized:
        return
    if headless and "SDL_VIDEODRIVER" not in os.environ:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame
    import pygame._freetype as _freetype

    pygame.init()
    _freetype.init()
    _apply_css_color_overrides(pygame)
    _initialized = True


# Pillow colours
_CSS_OVERRIDES = {
    "gray": (128, 128, 128, 255),
    "grey": (128, 128, 128, 255),
    "green": (0, 128, 0, 255),
    "purple": (128, 0, 128, 255),
    "maroon": (128, 0, 0, 255),
}


def _apply_css_color_overrides(pygame):
    table = pygame.color.THECOLORS
    for name, rgba in _CSS_OVERRIDES.items():
        table[name] = rgba


def freetype():
    """Return the pygame._freetype module, initializing if needed."""
    init()
    import pygame._freetype as _freetype

    return _freetype
