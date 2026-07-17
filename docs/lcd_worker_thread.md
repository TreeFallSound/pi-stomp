# Move the LCD push off the poll loop

## Why

A full-frame push blocks the UI thread for **21.4 ms on v2** and **25.2 ms on v3**,
against a 10 ms tick. Nothing mitigates this today.

`PanelStack.propagate_dirty` gates pushes on `transfer_ms(clip) <= INLINE_BUDGET_MS`
(8 ms), which *looks* like it protects the poll loop. It doesn't. The deferred path
— `poll_lcd_updates()` → `flush()` → `lcd.update()` — runs on the **same UI thread**
(`modalapistomp.py:224`). There is no worker anywhere. Deferring a push doesn't
offload it; it moves it to a later tick, where it blocks just as long. The gate only
chooses *which* tick eats the stall.

The win is available because the cost is almost entirely **wire time**, and wire time
is the part that touches no UI state:

| | stays on UI thread (compose + 565 pack) | movable (address window + `os.write`) |
|---|---|---|
| v3 @ 50 MHz | 0.29 ms | 24.9 ms |
| v2 @ 66.67 MHz | 1.82 ms | 19.3 ms |

`LcdIli9341.update()` already materialises `pixels_bytes` (an immutable `bytes`) and
hands it to `_block_fast(x0, y0, x1, y1, data)`, which touches only the SPI fd and the
DC/CS pins. **The seam is already there.** No UI code moves, no surface is shared, and
no double-buffer is needed — `tobytes()` is the copy. `os.write` releases the GIL, so
the UI thread genuinely runs during the transfer.

Estimated UI-thread stall on a full frame: **25.2 → ~0.3 ms (v3)**, **21.4 → ~1.8 ms (v2)**.

## Hazards

Both were found by measurement, and both are invisible from the cost model. Neither is
a reason not to do this — but a naive "wrap `update()` in a thread" ships a regression.

### 1. The ADC shares the SPI bus, and a full frame is one kernel message

The MCP3008 is on the same master (CE1, raw `spidev` @1 MHz); `poll_controls()` reads it
every tick on the UI thread. Today LCD and ADC **cannot** overlap — both are on the UI
thread — so the kernel sees one transfer at a time. A worker breaks that invariant, and
with `spidev.bufsiz=163840` the whole 153,600 B payload is a *single* SPI message. The
spi core serialises messages per master, so an ADC read issued mid-frame waits for the
entire frame to clock out.

Measured on v2 @ 66.67 MHz (`tools/bench_adc_contention.py`), ADC `xfer2` latency:

| | median | p95 | max | reads over the 10 ms tick |
|---|---|---|---|---|
| LCD idle (today) | 0.18 ms | 0.30 ms | 1.08 ms | **0%** |
| worker, one 153.6 kB write | **11.30 ms** | 12.86 ms | 18.14 ms | **100%** |
| worker, 64 kB chunks | 3.24 ms | 9.12 ms | 10.51 ms | 1% |
| worker, 16 kB chunks | 1.98 ms | 3.19 ms | 4.04 ms | **0%** |
| worker, 4 kB chunks | 0.82 ms | 1.61 ms | 2.91 ms | 0% |

Unchunked, **every** ADC read blocks past the tick. That trades a 21 ms stall in
`poll_lcd_updates` for an 11 ms stall in `poll_controls` — knobs and expression pedals
judder instead of the display. Strictly worse than today.

**16 kB is the sweet spot.** ADC max 4.04 ms, zero reads over tick. It costs full-frame
throughput (48.8 → 39 fps, −20%), which is free: `lcd_poll_divisor` gates pushes far
below that anyway.

### 2. LCD chip-select is a GPIO held low across the whole block write

`_block_fast` drives CS manually (`cs.value = ...`) and holds it asserted for the entire
call. **Any SPI traffic the kernel interleaves while that line is low is clocked into the
ILI9341 as pixel data.** So releasing the kernel lock between chunks is not sufficient —
chunking must genuinely *deassert CS* per chunk.

And once CS drops mid-GRAM-write, resuming needs the ILI9341's **`Write_Memory_Continue`
(0x3C)**. The Adafruit driver only defines `_RAM_WRITE = 0x2C` (`ili9341.py:49`), and
re-issuing *that* resets the address pointer to the window origin.

> **This is the trap.** It is invisible in the timing data — the bytes and the bus
> occupancy are identical whether or not the panel interprets them correctly. The
> chunked rows in the table above were produced by a prototype that did **not** send
> 0x3C, so its *timings are valid but its pixels are unverified*. MISO is not wired on
> v2, so GRAM cannot be read back; this needs a human looking at the screen.

## Proposed architecture

1. **Worker owns `_block_fast` only.** Poll loop composes, packs to 565, and submits
   `(bytes, x0, y0, x1, y1)` to a single-slot queue. Non-blocking. If a push is already
   in flight, coalesce or drop — `LcdIli9341.self.lock` already exists for this.
2. **Chunk the payload at ~16 kB**, deasserting CS between chunks so the ADC can
   interleave.
3. **Add `Write_Memory_Continue` (0x3C)** for every chunk after the first. Without it,
   (2) corrupts the frame.

Do (2) and (3) together or not at all — (2) alone is a silent corruption bug, and (1)
alone is a regression.

### Knock-on: the cost model gets less load-bearing

`transfer_ms` exists to gate inline pushes onto the UI thread. Once pushes don't block
the UI thread, a bad estimate stops being dangerous, and the per-SoC `PUSH_PROFILE` in
`uilib/spi_timing.py` (v2's per-pixel cost is 6.2× v3's — the boards genuinely diverge)
is demoted from safety-critical to an optimisation. It's still needed for
`lcd320x240.poll_divisor` and the emulator, which both need an estimate before any push
has happened.

### Unrelated, and worth more than it looks

`PanelStack._pending_lcd_clip` coalesces with `Box.union` — a **bounding box**,
unconditionally. Wire cost is linear in pixels, so merging disjoint rects is close to
pure loss: the 4×(32×131) case in [`spi_lcd_timing_pi3.md`](spi_lcd_timing_pi3.md) costs
**9.20 ms pushed separately, 21.36 ms coalesced** (2.3× worse). On v2 a merge only pays
while the union adds < ~4,575 px (6% of the screen) — the point where the added pixels
outweigh the 1.20 ms fixed cost saved.

We built a cost model and then don't consult it for the one decision where it would pay.
Comparing `cost(union)` against `cost(a) + cost(b)` before merging is small, self-
contained, and independent of everything above.

## Status

⚠️ **Proposed. Hazards measured, architecture not built.**

Evidence: `tools/bench_adc_contention.py` (v2 numbers above; **not yet run on v3** — the
Pi 5's DMA path arbitrates differently and its ADC sits behind RP1 rather than on-die).
Push costs: `tools/bench_lcd_device.py`, fitted into `spi_timing.PUSH_PROFILE`.

Verify 0x3C **visually on hardware** before trusting the chunked path. The one thing the
instruments cannot tell you here is whether the picture is right.

> Bench scripts live in `tools/` and must `sys.path.insert` the repo root — otherwise
> `import uilib` resolves to the copy in the venv's site-packages and you will silently
> benchmark the *packaged* driver instead of your working tree. This has already cost
> one round of bad constants.
