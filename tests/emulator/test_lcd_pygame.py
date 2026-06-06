"""Verify blit_scaled surfaces a consistent snapshot of all
queued updates, even when the SPI worker thread is throttled."""

import pygame
import pytest
from PIL import Image, ImageDraw

from emulator.lcd_pygame import LcdPygame
from uilib.box import Box


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    yield
    pygame.quit()


def _full_screen_with_stripes(width, height, stripes):
    """Build a full-screen image with coloured vertical stripes, matching
    the real PanelStack._do_refresh() calling convention (full image + box)."""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for x0, y0, x1, y1, color in stripes:
        draw.rectangle([x0, y0, x1, y1], fill=color)
    return img


def test_blit_scaled_reflects_all_queued_updates():
    # Each full-screen update at spi_hz=200_000 takes many seconds of
    # simulated SPI time, but the flush must still guarantee consistency.
    lcd = LcdPygame(width=320, height=240, spi_hz=10_000_000)

    colors = [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 0, 255),
    ]
    # Each update is a full-screen image (matching real usage) with one
    # coloured stripe; the dirty-region box covers just that stripe.
    for i, color in enumerate(colors):
        x0 = i * 8
        stripe = [(x0, 80, x0 + 4, 100, color)]
        img = _full_screen_with_stripes(320, 240, stripe)
        box = Box(x0, 80, x0 + 4, 100)
        lcd.update(img, box)

    # Snapshot via the same path render() uses
    dest = pygame.Surface((320, 240))
    lcd.blit_scaled(dest, pygame.Rect(0, 0, 320, 240))

    # Every queued color must be on screen at its expected position.
    for i, color in enumerate(colors):
        sample = dest.get_at((i * 8 + 1, 90))[:3]
        assert sample == color, (
            f"Update {i} (color {color}) missing from snapshot — got {sample}. "
            "This is the SPI-worker race that drops tuner strobe stripes."
        )


def test_wrap_around_stripe_both_halves_visible():
    """A strobe stripe that wraps from x=320 back to x=0 must show both halves
    in a single snapshot."""
    lcd = LcdPygame(width=320, height=240, spi_hz=10_000_000)

    # Erase the stripe row to background
    bg = Image.new("RGB", (320, 240), (0, 0, 0))
    lcd.update(bg, Box(0, 80, 320, 100))

    # Draw a red stripe: right half (310→320) and wrap half (0→10)
    red = (255, 0, 0)
    right = _full_screen_with_stripes(320, 240, [(310, 80, 320, 100, red)])
    lcd.update(right, Box(310, 80, 320, 100))
    wrap = _full_screen_with_stripes(320, 240, [(0, 80, 10, 100, red)])
    lcd.update(wrap, Box(0, 80, 10, 100))

    dest = pygame.Surface((320, 240))
    lcd.blit_scaled(dest, pygame.Rect(0, 0, 320, 240))

    # Both halves must be visible
    assert dest.get_at((315, 90))[:3] == red, "Right half of wrap stripe missing"
    assert dest.get_at((5, 90))[:3] == red, "Wrap (left) half of wrap stripe missing"
