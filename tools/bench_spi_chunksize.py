#!/usr/bin/env python3
"""Sweep chunk sizes for SPI frame writes and measure total transfer time.

Since spidev.bufsiz is set large (>=153600), we can test any chunk size
without rebooting. Each chunk size controls how many os.write() syscalls
are issued per frame push.

Usage (on device, service stopped):
    SDL_VIDEODRIVER=dummy python tools/bench_spi_chunksize.py
"""
import os, sys, time, statistics

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()
pygame.display.set_mode((1, 1))

import board, digitalio
from uilib.lcd_ili9341 import LcdIli9341
from uilib.box import Box

BAUD = 80_000_000
ITERS = 30

lcd = LcdIli9341(
    board.SPI(),
    digitalio.DigitalInOut(board.CE0),
    digitalio.DigitalInOut(board.D6),
    digitalio.DigitalInOut(board.D5),
    BAUD,
    True,
)

# Build a full-frame test surface
surf = pygame.Surface((320, 240))
for y in range(240):
    pygame.draw.line(surf, (y, 255 - y, (y * 3) % 256), (0, y), (319, y))

box = Box(0, 0, 320, 240)
FRAME_BYTES = 320 * 240 * 2  # 153600 bytes

# Sizes to test: from 4KB default up to full frame in one shot
# Also test 65532 (BCM2835 max DMA len) as a special case
chunk_sizes = [
    4096,       # kernel default (38 chunks)
    8192,       # 19 chunks
    16384,      # 10 chunks
    32768,       # 5 chunks
    65532,      # BCM2835 max_dma_len (3 chunks, aligns with internal splits)
    76800,      # 2 chunks
    113920,     # ~74% of frame (2 chunks, 2nd tiny)
    153600,     # 1 chunk (kernel splits to 3 DMA internally)
]

print(f"baud={BAUD/1e6:.0f}MHz  frame={FRAME_BYTES} bytes  iters={ITERS}")
print(f"{'chunk_bytes':>12}  {'n_chunks':>8}  {'median_ms':>10}  {'min_ms':>8}  {'p95_ms':>8}  {'σ_ms':>7}")
print("-" * 68)

import uilib.lcd_ili9341 as lcd_mod

for chunk in chunk_sizes:
    # Monkey-patch the module-level constant for this run
    lcd_mod.SPIDEV_BUFSIZ = chunk

    # Warm up
    for _ in range(5):
        lcd.update(surf, box)

    samples = []
    for _ in range(ITERS):
        t0 = time.perf_counter_ns()
        lcd.update(surf, box)
        samples.append((time.perf_counter_ns() - t0) / 1e6)

    n_chunks = -(-FRAME_BYTES // chunk)  # ceiling division
    med   = statistics.median(samples)
    mn    = min(samples)
    p95   = sorted(samples)[int(0.95 * len(samples))]
    sigma = statistics.stdev(samples)
    print(f"{chunk:>12}  {n_chunks:>8}  {med:>10.3f}  {mn:>8.3f}  {p95:>8.3f}  {sigma:>7.3f}")

# Restore original
try:
    with open("/sys/module/spidev/parameters/bufsiz") as f:
        lcd_mod.SPIDEV_BUFSIZ = int(f.read().strip())
except Exception:
    lcd_mod.SPIDEV_BUFSIZ = 4096

print()
print(f"Wire time at {BAUD/1e6:.0f}MHz for {FRAME_BYTES} bytes = {FRAME_BYTES*8/BAUD*1000:.2f}ms")
