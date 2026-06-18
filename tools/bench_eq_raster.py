#!/usr/bin/env python3
"""Benchmark pygame pixel-write strategies for the EQ curve rasterizer.

The EQ panel's `_draw` writes per-column pixels via `surf.set_at` in a Python
loop. This measures that against a vectorized `pygame.surfarray.pixels3d`
approach on the actual device, so we know whether the refactor is worth it.

Run:
    SDL_VIDEODRIVER=dummy python tools/bench_eq_raster.py
"""

from __future__ import annotations

import gc
import statistics
import time
import numpy as np
import pygame

W, H = 320, 178  # EQ graph widget size


def bench(label, fn, iters=200, warmup=10):
    for _ in range(warmup):
        fn()
    gc.collect()
    ms = []
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        ms.append((t1 - t0) / 1e6)
    med = statistics.median(ms)
    p95 = sorted(ms)[min(len(ms) - 1, int(0.95 * len(ms)))]
    print(f"  {label:<42} med={med:7.4f}  p95={p95:7.4f} ms")
    return med


def make_rgb_surface():
    s = pygame.Surface((W, H))
    s.fill((0, 0, 0))
    return s


def set_at_full_curve(surf):
    """Simulate the EQ curve: one set_at per column for the curve line (~320 calls)."""
    surf.fill((0, 0, 0))
    for x in range(W):
        y = int(H // 2 + 30 * np.sin(x * 0.05))
        surf.set_at((x, y), (255, 255, 255))


def set_at_curve_plus_smear(surf):
    """Simulate curve + smear: ~320 columns × ~30 row smear = ~9600 set_at calls."""
    surf.fill((0, 0, 0))
    for x in range(W):
        cy = int(H // 2 + 30 * np.sin(x * 0.05))
        for y in range(max(0, cy - 15), min(H, cy + 15)):
            surf.set_at((x, y), (40, 80, 120))


def set_at_dirty_50cols(surf):
    """Surgical refresh: 50 columns × ~30 row smear = ~1500 set_at calls."""
    x0, x1 = 100, 150
    for x in range(x0, x1):
        cy = int(H // 2 + 30 * np.sin(x * 0.05))
        for y in range(max(0, cy - 15), min(H, cy + 15)):
            surf.set_at((x, y), (40, 80, 120))


def pixels3d_full_curve(surf):
    """Vectorized: write the whole curve via a numpy view."""
    arr = pygame.surfarray.pixels3d(surf)
    arr[:] = 0
    xs = np.arange(W)
    ys = (H // 2 + 30 * np.sin(xs * 0.05)).astype(int)
    ys = np.clip(ys, 0, H - 1)
    arr[xs, ys, 0] = 255
    arr[xs, ys, 1] = 255
    arr[xs, ys, 2] = 255
    del arr


def pixels3d_curve_plus_smear(surf):
    """Vectorized curve + smear."""
    arr = pygame.surfarray.pixels3d(surf)
    arr[:] = 0
    xs = np.arange(W)
    cy = (H // 2 + 30 * np.sin(xs * 0.05)).astype(int)
    cy = np.clip(cy, 0, H - 1)
    # Build a (W, smear_h) smear band
    smear = 15
    ys_rel = np.arange(-smear, smear)  # (smear_h,)
    ys = cy[:, None] + ys_rel[None, :]  # (W, smear_h)
    valid = (ys >= 0) & (ys < H)
    xs_idx = np.broadcast_to(xs[:, None], ys.shape)
    arr[xs_idx[valid], ys[valid], 0] = 40
    arr[xs_idx[valid], ys[valid], 1] = 80
    arr[xs_idx[valid], ys[valid], 2] = 120
    # Curve line on top
    arr[xs, cy, 0] = 255
    arr[xs, cy, 1] = 255
    arr[xs, cy, 2] = 255
    del arr


def pixels3d_dirty_50cols(surf):
    """Vectorized surgical refresh: 50 columns."""
    arr = pygame.surfarray.pixels3d(surf)
    x0, x1 = 100, 150
    xs = np.arange(x0, x1)
    cy = (H // 2 + 30 * np.sin(xs * 0.05)).astype(int)
    cy = np.clip(cy, 0, H - 1)
    smear = 15
    ys_rel = np.arange(-smear, smear)
    ys = cy[:, None] + ys_rel[None, :]
    valid = (ys >= 0) & (ys < H)
    xs_idx = np.broadcast_to(xs[:, None], ys.shape)
    arr[xs_idx[valid], ys[valid], :] = (40, 80, 120)
    arr[xs, cy, :] = 255
    del arr


def draw_rect_erase_only(surf):
    """Baseline: just a fill_rect erase (no curve), for reference."""
    surf.fill((0, 0, 0))


def main():
    pygame.init()
    pygame.display.set_mode((1, 1))
    surf = make_rgb_surface()

    print(f"EQ graph rasterizer benchmark — {W}x{H} surface\n")

    print("Full-curve refresh (320 columns):")
    bench("set_at: curve only (320 calls)", lambda: set_at_full_curve(surf))
    bench("pixels3d: curve only", lambda: pixels3d_full_curve(surf))

    print("\nFull refresh: curve + smear (~9600 px):")
    bench("set_at: curve + smear", lambda: set_at_curve_plus_smear(surf))
    bench("pixels3d: curve + smear", lambda: pixels3d_curve_plus_smear(surf))

    print("\nSurgical refresh: 50 cols × smear (~1500 px):")
    bench("set_at: 50 cols", lambda: set_at_dirty_50cols(surf))
    bench("pixels3d: 50 cols", lambda: pixels3d_dirty_50cols(surf))

    print("\nBaseline (erase only, no drawing):")
    bench("surf.fill(black)", lambda: draw_rect_erase_only(surf))

    # Raw set_at cost per call
    print("\nRaw set_at cost (1000 isolated calls):")

    def raw_set_at():
        for i in range(1000):
            surf.set_at((i % W, i % H), (i % 256, (i * 2) % 256, (i * 3) % 256))

    bench("1000 × set_at", raw_set_at, iters=500)


if __name__ == "__main__":
    main()
