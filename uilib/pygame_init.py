# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Idempotent pygame + pygame._freetype initialization.

This is the single entry point for getting a ready-to-use freetype module:
call `freetype()` (or `font()`) and pygame/freetype are initialized on demand.
Nothing else in the codebase should `import pygame._freetype` or call
`pygame.init()` / `pygame.quit()` directly — route through here so init order
and re-init after teardown stay consistent.

We use pygame._freetype (the C extension) rather than pygame.freetype: the
public pygame.freetype module triggers a circular import with pygame.font on
Python 3.14 / pygame 2.6.1.
"""

import os

_initialized = False


def init():
    """Initialize pygame + pygame._freetype, idempotently.

    Re-initializes if a prior `quit()` (ours or a bare `pygame.quit()`) tore
    down the C-level state — our module flag alone can't observe an external
    teardown, so we also consult pygame/freetype's own init state.
    """
    global _initialized
    # default to headless mode; this is the production use case
    if "SDL_VIDEODRIVER" not in os.environ:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame
    import pygame._freetype as _freetype

    if _initialized and pygame.get_init() and _freetype.get_init():
        return
    pygame.init()
    _freetype.init()
    _apply_css_color_overrides(pygame)
    _initialized = True


def quit():
    """Tear down pygame and reset state so a later `init()` re-initializes."""
    global _initialized
    import pygame

    pygame.quit()
    _initialized = False


def freetype():
    """Return the pygame._freetype module, initializing if needed."""
    init()
    import pygame._freetype as _freetype

    return _freetype


def font(path, size):
    """Create a pygame._freetype.Font, initializing pygame/freetype if needed."""
    return freetype().Font(str(path), size)


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
