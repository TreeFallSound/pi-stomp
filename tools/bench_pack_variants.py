#!/usr/bin/env python3
"""Benchmark RGB565 pack variants for the LCD update path.

Compares the current pygame.image.tobytes() approach against pygame.surfarray
alternatives (pixels3d / array3d) at clip sizes the tuner strobe actually
generates: one stripe edge (~5px), one stripe span (~53px), the unioned strobe
region (~270px), and the full strobe widget (320px).

Source surface is RGBA (the PanelStack surface format when use_dimming=True).
Both reading and output buffer allocation strategies are tested.

Run:
    uv run python tools/bench_pack_variants.py
    uv run python tools/bench_pack_variants.py --iters 2000
    uv run python tools/bench_pack_variants.py --sizes 5x107,53x107,270x107
"""

from __future__ import annotations

import argparse
import gc
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pygame


# ---------------------------------------------------------------------------
# Pack variants
# All accept a pygame.Surface (sub-rect already extracted) and a pre-allocated
# output buffer of shape (MAX_H, MAX_W, 2) uint8, returning bytes.
# ---------------------------------------------------------------------------


def pack_tobytes(sub: pygame.Surface, out: np.ndarray) -> bytes:
    """Current production path: tobytes → frombuffer → channel ops → tobytes."""
    sh, sw = sub.get_height(), sub.get_width()
    rgb_bytes = pygame.image.tobytes(sub, "RGB")
    arr = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(sh, sw, 3)
    pix = out[:sh, :sw]
    g = arr[:, :, 1]
    pix[:, :, 0] = (arr[:, :, 0] & 0xF8) | (g >> 5)
    pix[:, :, 1] = ((g & 0x1C) << 3) | (arr[:, :, 2] >> 3)
    return pix.tobytes()


def pack_pixels3d_transpose(sub: pygame.Surface, out: np.ndarray) -> bytes:
    """pixels3d (zero-copy lock) + .transpose() (non-contiguous view)."""
    sh, sw = sub.get_height(), sub.get_width()
    # pixels3d returns (width, height, 3); transpose to (height, width, 3)
    arr = pygame.surfarray.pixels3d(sub).transpose(1, 0, 2)
    pix = out[:sh, :sw]
    g = arr[:, :, 1]
    pix[:, :, 0] = (arr[:, :, 0] & 0xF8) | (g >> 5)
    pix[:, :, 1] = ((g & 0x1C) << 3) | (arr[:, :, 2] >> 3)
    return pix.tobytes()


def pack_pixels3d_contig(sub: pygame.Surface, out: np.ndarray) -> bytes:
    """pixels3d + ascontiguousarray to force a single C-contiguous copy."""
    sh, sw = sub.get_height(), sub.get_width()
    arr = np.ascontiguousarray(pygame.surfarray.pixels3d(sub).transpose(1, 0, 2))
    pix = out[:sh, :sw]
    g = arr[:, :, 1]
    pix[:, :, 0] = (arr[:, :, 0] & 0xF8) | (g >> 5)
    pix[:, :, 1] = ((g & 0x1C) << 3) | (arr[:, :, 2] >> 3)
    return pix.tobytes()


def pack_array3d(sub: pygame.Surface, out: np.ndarray) -> bytes:
    """array3d: makes a C-contiguous (width, height, 3) copy, then transpose."""
    sh, sw = sub.get_height(), sub.get_width()
    arr = pygame.surfarray.array3d(sub).transpose(1, 0, 2)
    pix = out[:sh, :sw]
    g = arr[:, :, 1]
    pix[:, :, 0] = (arr[:, :, 0] & 0xF8) | (g >> 5)
    pix[:, :, 1] = ((g & 0x1C) << 3) | (arr[:, :, 2] >> 3)
    return pix.tobytes()


def pack_pixels3d_colmajor(sub: pygame.Surface, out_col: np.ndarray) -> bytes:
    """pixels3d with NO transpose: work in (width, height) column-major order.

    Skips the transpose entirely. The output is column-major (x-major) which
    is wrong for the LCD — this variant is included only to measure the cost
    of the transpose step in isolation. DO NOT use for real LCD output.
    """
    sh, sw = sub.get_height(), sub.get_width()
    arr = pygame.surfarray.pixels3d(sub)  # (sw, sh, 3) — no transpose
    pix = out_col[:sw, :sh]               # (sw, sh, 2) — col-major scratch
    g = arr[:, :, 1]
    pix[:, :, 0] = (arr[:, :, 0] & 0xF8) | (g >> 5)
    pix[:, :, 1] = ((g & 0x1C) << 3) | (arr[:, :, 2] >> 3)
    return pix.tobytes()  # wrong byte order for LCD — for timing only


def pack_pixels2d(sub: pygame.Surface, out: np.ndarray) -> bytes:
    """pixels2d: lock the surface as a (width, height) array of mapped pixels.

    Extracts R/G/B via bit shifts into the mapped pixel value. The exact shift
    depends on the surface's pixel format; we query it at call time.
    """
    sh, sw = sub.get_height(), sub.get_width()
    fmt = sub.get_masks()   # (Rmask, Gmask, Bmask, Amask)
    rshift = sub.get_shifts()[0]
    gshift = sub.get_shifts()[1]
    bshift = sub.get_shifts()[2]
    raw = pygame.surfarray.pixels2d(sub)  # (sw, sh), uint32, locked
    r = ((raw >> rshift) & 0xFF).astype(np.uint8)  # (sw, sh)
    g = ((raw >> gshift) & 0xFF).astype(np.uint8)
    b = ((raw >> bshift) & 0xFF).astype(np.uint8)
    # r/g/b are (sw, sh) — transpose to (sh, sw) for row-major output
    pix = out[:sh, :sw]
    pix[:, :, 0] = (r.T & 0xF8) | (g.T >> 5)
    pix[:, :, 1] = ((g.T & 0x1C) << 3) | (b.T >> 3)
    return pix.tobytes()


# ---------------------------------------------------------------------------
# Correctness check
# ---------------------------------------------------------------------------


def _check_all_match() -> None:
    rng = np.random.default_rng(7)
    # Use a size that's not a power-of-2 to catch stride bugs
    w, h = 13, 47
    rgba = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
    # Build an RGBA surface from random data
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.blit_array(surf, rgba[:, :, :3].transpose(1, 0, 2).copy())

    out = np.empty((h, w, 2), dtype=np.uint8)
    out_col = np.empty((w, h, 2), dtype=np.uint8)

    ref = pack_tobytes(surf, out.copy())

    variants = [
        ("pixels3d_transpose", pack_pixels3d_transpose(surf, out.copy())),
        ("pixels3d_contig",    pack_pixels3d_contig(surf, out.copy())),
        ("array3d",            pack_array3d(surf, out.copy())),
        ("pixels2d",           pack_pixels2d(surf, out.copy())),
    ]
    for name, result in variants:
        assert result == ref, (
            f"{name} mismatch at ({w}x{h}):\n"
            f"  ref[0:8]={list(ref[:8])}\n  got[0:8]={list(result[:8])}"
        )
    print("Correctness check passed: all variants produce identical bytes.\n")


# ---------------------------------------------------------------------------
# Timing harness
# ---------------------------------------------------------------------------


@dataclass
class Result:
    label: str
    samples_us: list[float] = field(default_factory=list)

    @property
    def median_us(self) -> float:
        return statistics.median(self.samples_us)

    @property
    def mean_us(self) -> float:
        return statistics.fmean(self.samples_us)

    @property
    def stdev_us(self) -> float:
        return statistics.stdev(self.samples_us) if len(self.samples_us) > 1 else 0.0

    @property
    def min_us(self) -> float:
        return min(self.samples_us)

    @property
    def p95_us(self) -> float:
        s = sorted(self.samples_us)
        return s[min(len(s) - 1, int(0.95 * len(s)))]


def bench(label: str, fn: Callable[[], None], iters: int, warmup: int = 20) -> Result:
    for _ in range(warmup):
        fn()
    gc.collect()
    r = Result(label=label)
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        fn()
        r.samples_us.append((time.perf_counter_ns() - t0) / 1e3)
    return r


def _print(r: Result, baseline_us: float | None = None) -> None:
    speedup = f"  {baseline_us / r.median_us:5.2f}x vs baseline" if baseline_us else ""
    print(
        f"  {r.label:<36} med={r.median_us:7.1f}  mean={r.mean_us:7.1f}"
        f"  p95={r.p95_us:7.1f}  min={r.min_us:7.1f}  σ={r.stdev_us:6.1f} µs{speedup}"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def make_rgba_surface(w: int, h: int) -> pygame.Surface:
    """RGBA surface with random pixel data (matches PanelStack format)."""
    rng = np.random.default_rng(42)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    data = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
    # blit_array expects (w, h, 3) for RGB
    pygame.surfarray.blit_array(surf, data[:, :, :3].transpose(1, 0, 2).copy())
    return surf


def run(sizes: list[tuple[int, int]], iters: int) -> None:
    MAX_W = max(w for w, h in sizes)
    MAX_H = max(h for w, h in sizes)
    out     = np.empty((MAX_H, MAX_W, 2), dtype=np.uint8)  # row-major (h,w,2)
    out_col = np.empty((MAX_W, MAX_H, 2), dtype=np.uint8)  # col-major (w,h,2)

    for w, h in sizes:
        surf = make_rgba_surface(w, h)
        px   = w * h
        print(f"\n{'='*72}")
        print(f"  {w}x{h}  ({px:,} px, {px*2:,} B RGB565)")
        print(f"{'='*72}")

        results = [
            bench("tobytes (baseline)",          lambda s=surf: pack_tobytes(s, out),                iters),
            bench("pixels3d + transpose",         lambda s=surf: pack_pixels3d_transpose(s, out),     iters),
            bench("pixels3d + ascontiguousarray", lambda s=surf: pack_pixels3d_contig(s, out),        iters),
            bench("array3d + transpose",          lambda s=surf: pack_array3d(s, out),                iters),
            bench("pixels2d + transpose",         lambda s=surf: pack_pixels2d(s, out),               iters),
            bench("pixels3d no-transpose [WRONG]",lambda s=surf: pack_pixels3d_colmajor(s, out_col), iters),
        ]

        baseline = results[0].median_us
        for r in results:
            _print(r, baseline_us=None if r is results[0] else baseline)

        print()
        print(f"  Speedup summary vs tobytes baseline ({baseline:.1f} µs median):")
        for r in results[1:]:
            delta = baseline - r.median_us
            sign  = "faster" if delta > 0 else "SLOWER"
            print(f"    {r.label:<36} {abs(delta):5.1f} µs {sign}  ({baseline/r.median_us:.2f}x)")


def parse_sizes(spec: str) -> list[tuple[int, int]]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        w_s, h_s = part.split("x")
        out.append((int(w_s), int(h_s)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sizes",
        default="5x107,8x107,53x107,270x107,320x107,320x127",
        help="comma-separated WxH clip sizes to test (default: strobe-relevant sizes)",
    )
    ap.add_argument("--iters", type=int, default=1000, help="iterations per variant (default: 1000)")
    ap.add_argument("--no-check", action="store_true", help="skip correctness self-check")
    args = ap.parse_args()

    pygame.init()
    pygame.display.set_mode((1, 1))

    if not args.no_check:
        _check_all_match()

    sizes = parse_sizes(args.sizes)
    print(f"Running {args.iters} iters per variant on {len(sizes)} clip sizes\n")
    run(sizes, args.iters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
