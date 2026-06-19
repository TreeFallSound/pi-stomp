#!/usr/bin/env python3
"""On-device timing of the real LcdIli9341.update() across clip sizes.

Times the full pygame->PIL->565->SPI push for several full-width boxes so we
can fit transfer_ms = pipeline_per_px*px + wire(px, clock). Run once per clock:

    SDL_VIDEODRIVER=dummy python tools/bench_lcd_device.py <baud_hz>

Must run with the LCD free (service stopped). Drives the panel directly.
"""
import os
import sys
import time
import statistics

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()
pygame.display.set_mode((1, 1))

import board
import digitalio
from uilib.box import Box
from uilib.lcd_ili9341 import LcdIli9341

baud = int(sys.argv[1]) if len(sys.argv) > 1 else 24_000_000

lcd = LcdIli9341(
    board.SPI(),
    digitalio.DigitalInOut(board.CE0),
    digitalio.DigitalInOut(board.D6),
    digitalio.DigitalInOut(board.D5),
    baud,
    True,
)

surf = pygame.Surface((320, 240))
for y in range(240):
    pygame.draw.line(surf, (y, 255 - y, (y * 3) % 256), (0, y), (319, y))

heights = [240, 178, 120, 65, 24, 6]
iters = 60

print(f"baud={baud/1e6:.0f}MHz  px,median_ms,min_ms")
for h in heights:
    box = Box(0, 0, 320, h)
    for _ in range(5):
        lcd.update(surf, box)
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        lcd.update(surf, box)
        samples.append((time.perf_counter_ns() - t0) / 1e6)
    px = 320 * h
    print(f"{px},{statistics.median(samples):.3f},{min(samples):.3f}")
