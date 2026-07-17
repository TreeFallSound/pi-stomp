"""Regression: no flash of unstyled plugin text ("FOUT") on a board redraw.

`draw_plugins` tears down the old grid and builds new tiles. Each PluginTile
paints once on construction (unstyled: label on the bare backdrop) and again
once `color_plugin` gives it its fill. If those intermediate paints reach the
LCD, the user sees every effect's name flash in white-on-black before the tiles
fill in. The redraw must present atomically — every frame pushed during the
rebuild is identical to the finished screen.
"""

from __future__ import annotations

import pygame

from tests.types import SystemFixture


def _frame_bytes(surface: pygame.Surface) -> bytes:
    return pygame.image.tobytes(surface, "RGB")


def test_draw_plugins_presents_atomically(v3_system: SystemFixture, fake_lcd, make_plugin):
    handler = v3_system.handler
    handler.current.pedalboard.plugins = [
        make_plugin("drive", category="Distortion"),
        make_plugin("verb", category="Reverb"),
        make_plugin("delay", category="Delay"),
    ]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, handler.hardware.footswitches)
    handler.lcd.draw_main_panel()

    fake = fake_lcd
    fake.frames.clear()
    handler.lcd.draw_plugins()
    fake.flush()

    assert fake.frames, "draw_plugins pushed no frame"
    final = _frame_bytes(fake.frames[-1])
    for i, frame in enumerate(fake.frames):
        assert _frame_bytes(frame) == final, (
            f"frame {i}/{len(fake.frames) - 1} differs from the finished screen: "
            "an intermediate (unstyled) plugin render leaked to the LCD (FOUT)"
        )
