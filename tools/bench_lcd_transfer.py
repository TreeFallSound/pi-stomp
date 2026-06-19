#!/usr/bin/env python3
"""Synthetic benchmark for the LCD transfer path.

Measures each stage of the pygame -> PIL -> numpy -> RGB565 -> SPI-bytes
pipeline in isolation so we can validate the cost model from the panel
reviews before touching any panel or driver code.

This is a *host-side* benchmark (no real SPI, no real LCD). It measures the
*Python-side* overhead that dominates at >=48 MHz SPI clocks. The actual SPI
transfer time is computed analytically from the byte count and clock.

What it does NOT measure:
  - Real SPI kernel-driver overhead (spidev write syscalls)
  - The adafruit_bus_device SPIDevice context-manager cost on real hardware
  - GPIO DC-pin toggle cost

What it DOES measure (the parts we can optimise in Python):
  1. pygame.Surface format effects on `pygame.image.tobytes("RGB")`
     (RGB vs RGBA source surface)
  2. PIL.Image.frombytes + img.rotate(rotation, expand=True)
  3. image_to_data: the numpy 565 conversion, with and without the
     `.flatten().tolist()` re-pack
  4. Whole-pipeline end-to-end for each dirty-rect size

Run:
    uv run python tools/bench_lcd_transfer.py
    uv run python tools/bench_lcd_transfer.py --sizes 320x240,4x131,50x178
    uv run python tools/bench_lcd_transfer.py --csv
"""

from __future__ import annotations

import argparse
import csv
import gc
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pygame
from PIL import Image

# ---------------------------------------------------------------------------
# Replicate the upstream adafruit image_to_data exactly (3.14.3) so we bench
# the real code path, not a paraphrase.
# ---------------------------------------------------------------------------


def image_to_data_upstream(image: Image.Image) -> list[int]:
    """adafruit_rgb_display.rgb.image_to_data, 3.14.3, verbatim logic."""
    data = np.array(image.convert("RGB")).astype("uint16")
    color = ((data[:, :, 0] & 0xF8) << 8) | ((data[:, :, 1] & 0xFC) << 3) | (data[:, :, 2] >> 3)
    return np.dstack(((color >> 8) & 0xFF, color & 0xFF)).flatten().tolist()


def image_to_data_tobytes(image: Image.Image) -> bytes:
    """Proposed drop-in: skip .tolist(), use ndarray.tobytes() directly.

    Returns bytes (not list) — `bytes(list)` in the caller becomes a no-op
    wrapper since the result is already bytes. Same byte layout: high byte
    then low byte of each 565 pixel, row-major.
    """
    data = np.array(image.convert("RGB")).astype("uint16")
    color = ((data[:, :, 0] & 0xF8) << 8) | ((data[:, :, 1] & 0xFC) << 3) | (data[:, :, 2] >> 3)
    packed = np.dstack(((color >> 8) & 0xFF, color & 0xFF)).astype(np.uint8)
    return packed.tobytes()


def image_to_data_tobytes_contiguous(image: Image.Image) -> bytes:
    """Variant: force C-contiguous before tobytes (dstack result may not be)."""
    data = np.array(image.convert("RGB")).astype("uint16")
    color = ((data[:, :, 0] & 0xF8) << 8) | ((data[:, :, 1] & 0xFC) << 3) | (data[:, :, 2] >> 3)
    hi = ((color >> 8) & 0xFF).astype(np.uint8)
    lo = (color & 0xFF).astype(np.uint8)
    # Interleave via column stack then flatten -> (H, W, 2) C-contiguous uint8
    out = np.column_stack((hi.ravel(), lo.ravel())).reshape(color.shape[0], color.shape[1], 2)
    return out.tobytes()


def image_to_data_no_pil(rgb_bytes: bytes, w: int, h: int) -> bytes:
    """Variant: take raw RGB888 bytes (from pygame) and skip PIL entirely.

    This is the path a fully-bypassed driver would take. Measures the
    theoretical floor for the 565 conversion when PIL is removed from the
    chain. Output must match image_to_data_tobytes byte-for-byte.
    """
    arr = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(h, w, 3).astype("uint16")
    color = ((arr[:, :, 0] & 0xF8) << 8) | ((arr[:, :, 1] & 0xFC) << 3) | (arr[:, :, 2] >> 3)
    hi = ((color >> 8) & 0xFF).astype(np.uint8)
    lo = (color & 0xFF).astype(np.uint8)
    out = np.column_stack((hi.ravel(), lo.ravel())).reshape(h, w, 2)
    return out.tobytes()


def image_to_data_no_pil_opt(rgb_bytes: bytes, w: int, h: int) -> bytes:
    """Highly optimized no-PIL variant avoiding uint16 upcasting and column_stack."""
    arr = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(h, w, 3)
    out = np.empty((h, w, 2), dtype=np.uint8)
    out[:, :, 0] = (arr[:, :, 0] & 0xF8) | (arr[:, :, 1] >> 5)
    out[:, :, 1] = ((arr[:, :, 1] & 0x1C) << 3) | (arr[:, :, 2] >> 3)
    return out.tobytes()


# ---------------------------------------------------------------------------
# Correctness check — make sure all variants produce identical output.
# ---------------------------------------------------------------------------


def _assert_variants_match(seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    w, h = 37, 19  # odd dims to catch stride bugs
    rgb = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
    rgb_bytes = pygame.image.tobytes(surf, "RGB")
    pil = Image.frombytes("RGB", (w, h), rgb_bytes)

    ref = bytes(image_to_data_upstream(pil))
    a = image_to_data_tobytes(pil)
    b = image_to_data_tobytes_contiguous(pil)
    c = image_to_data_no_pil(rgb_bytes, w, h)
    d = image_to_data_no_pil_opt(rgb_bytes, w, h)
    assert a == ref, f"tobytes variant mismatch: {a[:20]} vs {ref[:20]}"
    assert b == ref, f"tobytes_contiguous variant mismatch"
    assert c == ref, f"no_pil variant mismatch"
    assert d == ref, f"no_pil_opt variant mismatch"
    # Sanity: byte length is w*h*2
    assert len(ref) == w * h * 2, f"bad length {len(ref)} vs {w * h * 2}"


# ---------------------------------------------------------------------------
# Timing harness
# ---------------------------------------------------------------------------


@dataclass
class TimingResult:
    label: str
    samples_ms: list[float] = field(default_factory=list)

    @property
    def median_ms(self) -> float:
        return statistics.median(self.samples_ms)

    @property
    def mean_ms(self) -> float:
        return statistics.fmean(self.samples_ms)

    @property
    def stdev_ms(self) -> float:
        return statistics.stdev(self.samples_ms) if len(self.samples_ms) > 1 else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.samples_ms)

    @property
    def p95_ms(self) -> float:
        s = sorted(self.samples_ms)
        return s[min(len(s) - 1, int(0.95 * len(s)))]


def bench(label: str, fn: Callable[[], None], iters: int, warmup: int = 5) -> TimingResult:
    """Run fn iters times after warmup, returning per-call ms timings."""
    for _ in range(warmup):
        fn()
    gc.collect()
    res = TimingResult(label=label)
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        res.samples_ms.append((t1 - t0) / 1e6)
    return res


def fmt_spi_ms(byte_count: int, mhz: float) -> float:
    """Analytic SPI transfer time for byte_count at mhz clock (565 = 2 B/px)."""
    bits = byte_count * 8
    return bits / (mhz * 1e6) * 1e3  # ms


# ---------------------------------------------------------------------------
# Stage benchmarks
# ---------------------------------------------------------------------------


def make_surface(w: int, h: int, fmt: str, fill: tuple = (40, 80, 120)) -> pygame.Surface:
    """fmt: 'RGB' (24-bit) or 'RGBA' (32-bit SRCALPHA)."""
    if fmt == "RGBA":
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((*fill, 255))
    else:
        s = pygame.Surface((w, h))
        s.fill(fill)
    return s


def stage_tobytes(surf: pygame.Surface, fmt: str) -> Callable[[], None]:
    def go() -> None:
        pygame.image.tobytes(surf, fmt)

    return go


def stage_pil_frombytes_rotate(rgb_bytes: bytes, w: int, h: int, rotation: int) -> Callable[[], None]:
    def go() -> None:
        img = Image.frombytes("RGB", (w, h), rgb_bytes)
        if rotation:
            img = img.rotate(rotation, expand=True)
        # touch the data so rotate is realised (PIL is lazy on some ops)
        img.load()

    return go


def stage_image_to_data(img_rotated: Image.Image, variant: str) -> Callable[[], None]:
    if variant == "upstream":
        fn = image_to_data_upstream
    elif variant == "tobytes":
        fn = image_to_data_tobytes
    elif variant == "tobytes_contig":
        fn = image_to_data_tobytes_contiguous
    elif variant == "no_pil":
        # Caller must pass a pre-rotated rgb buffer; we ignore img_rotated
        raise ValueError("no_pil variant uses stage_no_pil, not stage_image_to_data")
    else:
        raise ValueError(variant)

    def go() -> None:
        fn(img_rotated)

    return go


def stage_no_pil(rgb_bytes: bytes, w: int, h: int) -> Callable[[], None]:
    def go() -> None:
        image_to_data_no_pil(rgb_bytes, w, h)

    return go


def stage_end_to_end_upstream(surf: pygame.Surface, w: int, h: int, rotation: int) -> Callable[[], None]:
    def go() -> None:
        rgb = pygame.image.tobytes(surf, "RGB")
        img = Image.frombytes("RGB", (w, h), rgb)
        if rotation:
            img = img.rotate(rotation, expand=True)
        _ = bytes(image_to_data_upstream(img))

    return go


def stage_end_to_end_patched(surf: pygame.Surface, w: int, h: int, rotation: int) -> Callable[[], None]:
    def go() -> None:
        rgb = pygame.image.tobytes(surf, "RGB")
        img = Image.frombytes("RGB", (w, h), rgb)
        if rotation:
            img = img.rotate(rotation, expand=True)
        _ = image_to_data_tobytes(img)

    return go


def stage_end_to_end_no_pil(surf: pygame.Surface, w: int, h: int, rotation: int) -> Callable[[], None]:
    """Bypasses PIL entirely. Rotation is done in numpy.

    This is the theoretical floor: pygame -> 565 bytes, no PIL.
    """
    if rotation == 270:
        rot = lambda a: np.rot90(a, k=3)
    elif rotation == 90:
        rot = lambda a: np.rot90(a, k=1)
    elif rotation == 0:
        rot = lambda a: a
    elif rotation == 180:
        rot = lambda a: np.rot90(a, k=2)
    else:
        raise ValueError(rotation)

    def go() -> None:
        rgb = pygame.image.tobytes(surf, "RGB")
        arr = np.frombuffer(rgb, dtype=np.uint8).reshape(h, w, 3)
        arr = rot(arr)
        out = np.empty((arr.shape[0], arr.shape[1], 2), dtype=np.uint8)
        out[:, :, 0] = (arr[:, :, 0] & 0xF8) | (arr[:, :, 1] >> 5)
        out[:, :, 1] = ((arr[:, :, 1] & 0x1C) << 3) | (arr[:, :, 2] >> 3)
        _ = out.tobytes()

    return go


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SPI_SPEEDS = [24, 48, 56, 80]
ROTATION = 270  # v3 flip


def parse_sizes(spec: str) -> list[tuple[int, int]]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        w, h = part.split("x")
        out.append((int(w), int(h)))
    return out


def run(sizes: list[tuple[int, int]], iters: int) -> list[dict]:
    rows = []
    for w, h in sizes:
        px = w * h
        rgb565_bytes = px * 2
        # Make both an RGB and an RGBA surface to compare format effects.
        surf_rgb = make_surface(w, h, "RGB")
        surf_rgba = make_surface(w, h, "RGBA")
        # Pre-render a rotated PIL image for the isolated image_to_data stage.
        rgb_pre = pygame.image.tobytes(surf_rgb, "RGB")
        pil_pre = Image.frombytes("RGB", (w, h), rgb_pre).rotate(ROTATION, expand=True)
        pil_pre.load()
        # Pre-render rotated rgb bytes for the no_pil path
        arr_pre = np.frombuffer(rgb_pre, dtype=np.uint8).reshape(h, w, 3)
        arr_rot = np.rot90(arr_pre, k=3) if ROTATION == 270 else arr_pre
        rgb_rot_bytes = arr_rot.tobytes()
        h_rot, w_rot = arr_rot.shape[0], arr_rot.shape[1]

        print(f"\n=== {w}x{h}  ({px} px, {rgb565_bytes} B RGB565) ===")

        # Stage 1: pygame.image.tobytes("RGB") — RGB vs RGBA source
        r1a = bench("tobytes(RGB surf)", stage_tobytes(surf_rgb, "RGB"), iters)
        r1b = bench("tobytes(RGBA surf)", stage_tobytes(surf_rgba, "RGB"), iters)
        _print(r1a)
        _print(r1b)

        # Stage 2: PIL frombytes + rotate
        r2 = bench("PIL frombytes+rotate", stage_pil_frombytes_rotate(rgb_pre, w, h, ROTATION), iters)
        _print(r2)

        # Stage 3: image_to_data variants (operate on pre-rotated image)
        r3a = bench("image_to_data upstream (.tolist())", stage_image_to_data(pil_pre, "upstream"), iters)
        r3b = bench("image_to_data tobytes", stage_image_to_data(pil_pre, "tobytes"), iters)
        r3c = bench("image_to_data tobytes_contig", stage_image_to_data(pil_pre, "tobytes_contig"), iters)
        r3d = bench("image_to_data no_pil (raw bytes->565)", stage_no_pil(rgb_rot_bytes, w_rot, h_rot), iters)
        _print(r3a)
        _print(r3b)
        _print(r3c)
        _print(r3d)

        # Stage 4: end-to-end (pygame surface -> 565 bytes)
        r4a = bench("E2E upstream", stage_end_to_end_upstream(surf_rgb, w, h, ROTATION), iters)
        r4b = bench("E2E patched (tobytes)", stage_end_to_end_patched(surf_rgb, w, h, ROTATION), iters)
        r4c = bench("E2E no-PIL (numpy rotate)", stage_end_to_end_no_pil(surf_rgb, w, h, ROTATION), iters)
        r4d = bench("E2E upstream (RGBA surf)", stage_end_to_end_upstream(surf_rgba, w, h, ROTATION), iters)
        _print(r4a)
        _print(r4b)
        _print(r4c)
        _print(r4d)

        # Analytic SPI times for reference
        spi_times = {mhz: fmt_spi_ms(rgb565_bytes, mhz) for mhz in SPI_SPEEDS}

        for label, r in [
            ("tobytes_rgb", r1a),
            ("tobytes_rgba", r1b),
            ("pil_rotate", r2),
            ("i2d_upstream", r3a),
            ("i2d_tobytes", r3b),
            ("i2d_tobytes_contig", r3c),
            ("i2d_no_pil", r3d),
            ("e2e_upstream", r4a),
            ("e2e_patched", r4b),
            ("e2e_no_pil", r4c),
            ("e2e_upstream_rgba", r4d),
        ]:
            rows.append(
                {
                    "size": f"{w}x{h}",
                    "w": w,
                    "h": h,
                    "pixels": px,
                    "rgb565_bytes": rgb565_bytes,
                    "stage": label,
                    "median_ms": round(r.median_ms, 4),
                    "mean_ms": round(r.mean_ms, 4),
                    "p95_ms": round(r.p95_ms, 4),
                    "min_ms": round(r.min_ms, 4),
                    "stdev_ms": round(r.stdev_ms, 4),
                    "iters": iters,
                    "spi_24mhz_ms": round(spi_times[24], 4),
                    "spi_48mhz_ms": round(spi_times[48], 4),
                    "spi_56mhz_ms": round(spi_times[56], 4),
                    "spi_80mhz_ms": round(spi_times[80], 4),
                }
            )
    return rows


def _print(r: TimingResult) -> None:
    print(
        f"  {r.label:<38} med={r.median_ms:7.4f}  mean={r.mean_ms:7.4f}  "
        f"p95={r.p95_ms:7.4f}  min={r.min_ms:7.4f}  σ={r.stdev_ms:6.4f} ms"
    )


def print_summary(rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("SPI transfer time (analytic, ms) for reference:")
    print(f"  {'size':<10} {'bytes':>10} {'24MHz':>8} {'48MHz':>8} {'56MHz':>8} {'80MHz':>8}")
    seen = set()
    for row in rows:
        key = row["size"]
        if key in seen:
            continue
        seen.add(key)
        print(
            f"  {row['size']:<10} {row['rgb565_bytes']:>10} "
            f"{row['spi_24mhz_ms']:>8.3f} {row['spi_48mhz_ms']:>8.3f} "
            f"{row['spi_56mhz_ms']:>8.3f} {row['spi_80mhz_ms']:>8.3f}"
        )

    print("\nEnd-to-end median (ms) — what the panel actually pays per refresh:")
    print(f"  {'size':<10} {'upstream':>10} {'patched':>10} {'no-PIL':>10} {'RGBAΔ%':>8}")
    e2e = {}
    for row in rows:
        if row["stage"] in ("e2e_upstream", "e2e_patched", "e2e_no_pil", "e2e_upstream_rgba"):
            e2e.setdefault(row["size"], {})[row["stage"]] = row["median_ms"]
    for size, d in e2e.items():
        upstream = d.get("e2e_upstream", 0)
        patched = d.get("e2e_patched", 0)
        no_pil = d.get("e2e_no_pil", 0)
        rgba = d.get("e2e_upstream_rgba", 0)
        delta_pct = ((rgba - upstream) / upstream * 100) if upstream else 0
        print(f"  {size:<10} {upstream:>10.4f} {patched:>10.4f} {no_pil:>10.4f} {delta_pct:>7.1f}%")

    print("\nimage_to_data stage only (ms) — isolates the .tolist() vs .tobytes() win:")
    print(f"  {'size':<10} {'upstream':>10} {'tobytes':>10} {'contig':>10} {'no_pil':>10} {'speedup':>8}")
    i2d = {}
    for row in rows:
        if row["stage"].startswith("i2d_"):
            i2d.setdefault(row["size"], {})[row["stage"]] = row["median_ms"]
    for size, d in i2d.items():
        upstream = d.get("i2d_upstream", 0)
        tobytes = d.get("i2d_tobytes", 0)
        contig = d.get("i2d_tobytes_contig", 0)
        no_pil = d.get("i2d_no_pil", 0)
        speedup = (upstream / tobytes) if tobytes else 0
        print(f"  {size:<10} {upstream:>10.4f} {tobytes:>10.4f} {contig:>10.4f} {no_pil:>10.4f} {speedup:>7.1f}x")


def write_csv(rows: list[dict], path: str) -> None:
    fields = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"\nCSV written to {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", default="320x240,320x178,4x131,50x178,320x65,320x13")
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--csv", default=None, help="write results CSV to this path")
    ap.add_argument("--no-check", action="store_true", help="skip correctness self-check")
    args = ap.parse_args()

    pygame.init()
    pygame.display.set_mode((1, 1))  # headless-ish; needed for Surface ops

    if not args.no_check:
        _assert_variants_match()
        print("Correctness check passed: all image_to_data variants produce identical bytes.\n")

    sizes = parse_sizes(args.sizes)
    print(f"Running {args.iters} iters per stage, rotation={ROTATION}°, sizes={sizes}\n")

    rows = run(sizes, args.iters)
    print_summary(rows)
    if args.csv:
        write_csv(rows, args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
