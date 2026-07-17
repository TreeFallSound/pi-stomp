# SPI LCD Timing — Pi 3A+ / BCM2837 (v2 hardware)

Pushing a 320×240 16-bit frame to the ILI9341 over SPI on the v2 pi-stomp
(Raspberry Pi 3A+, BCM2837B0).

For the v3 hardware (Pi 5 / RP1), see [`spi_lcd_timing_pi5.md`](spi_lcd_timing_pi5.md).
That doc also covers the device-agnostic options for getting the blocking
`write()` off the poll loop (background thread, `panel-mipi-dbi-spi`).

All numbers here are measured on-device (`6.18.36-rpi-v8-rt`, `core_freq=400`,
`spidev.bufsiz=163840`) by timing the pixel-payload `os.write()` inside
`LcdIli9341._block_fast` and deriving the clock from bits/second.

`uilib/spi_timing.py` models this: `actual_spi_hz()` applies the divisor rule for
the running host (detected from `/proc/device-tree/compatible`), and
`transfer_ms()` estimates push cost from the *actual* clock, never the requested
one.

---

## Hardware architecture

The SPI peripheral is **on-die** — there is no PCIe hop, and therefore none of
the Pi 5's PCIe DMA stall.  The Linux driver is `spi-bcm2835`, not `spi_dw_mmio`.

```
BCM2837B0
┌───────────────────────────────────┐
│  4× Cortex-A53 @ 1.2–1.4 GHz      │
│  512 MB SDRAM                     │
│  bcm2835-dma ──► reads SDRAM      │
│      ↓  (no PCIe)                 │
│  spi0 (spi-bcm2835) ◄─ VPU 400MHz │
│      ├─ ILI9341 LCD  (CE0)        │
│      └─ MCP3008 ADC  (CE1)        │
└───────────────────────────────────┘
```

**Device nodes**: `/dev/spidev0.0` (LCD, CE0), `/dev/spidev0.1` (ADC, CE1).
The ADC is opened separately by `hardware.init_spi()` (`spidev.SpiDev().open(0, 1)`,
1 MHz), so it has its own fd and cannot clobber the LCD's clock.

---

## The clock divisor rule

`spi-bcm2835.c` computes:

```c
cdiv = DIV_ROUND_UP(clk_hz, spi_hz);   /* clk_hz = 400 MHz */
cdiv += cdiv % 2;                      /* round *up to even*, not to a power of 2 */
```

**CDIV is rounded up to an even number, not to a power of two.**  The
power-of-2 rule is legacy folklore — it appears in the BCM2835 datasheet and in
the pre-2015 downstream driver — and it is wrong for mainline.  Verified
empirically across 20 requested speeds: every measured clock lands on
`400 / even`, including 40 MHz (CDIV=10), 28.57 MHz (CDIV=14) and 66.67 MHz
(CDIV=6), none of which a power-of-2 rule can produce.

Because the divisor is rounded *up*, the actual clock is always ≤ the requested
clock.  Requesting one hertz below an exact divisor point costs a full step:

```
66_666_666 → CDIV=8 → 50.00 MHz
66_666_667 → CDIV=6 → 66.67 MHz
```

This is why `Lcd` takes `spi_speed_hz` (an exact integer) rather than
`spi_speed_mhz`.

The VPU core clock is pinned at 400 MHz.  Setting `core_freq` (or `force_turbo`)
moves the SPI clock with it.

---

## Achievable speeds

Full-frame (320×240 = 76,800 px, 153,600 B), service stopped.
"Total" is `pack + address-window + payload write`; MB/s is payload/wire.

Wire time is clock-derived and unaffected by the pack. **Total** is from the
current SDL convert-blit pack (see "The pack" below): measured at 20, 40 and
66.67 MHz, and model-derived from `spi_timing.PUSH_PROFILE` at the rest.

| Requested | CDIV | **Actual** | Wire | Total | Throughput | Full-frame ceiling |
|-----------|------|-----------|---------|---------|----------|-----|
| 12.5 MHz | 32 | 12.50 MHz | 97.83 ms | 100.85 ms | 1.57 MB/s | 9.9 fps |
| 20 MHz | 20 | 20.00 MHz | 61.14 ms | **63.98 ms** ᵐ | 2.51 MB/s | 15.6 fps |
| 25–28.5 MHz | 16 | 25.00 MHz | 48.92 ms | 51.93 ms | 3.14 MB/s | 19.3 fps |
| 33.3 MHz | 14 | 28.57 MHz | 42.80 ms | 45.82 ms | 3.59 MB/s | 21.8 fps |
| 40–44.4 MHz | 10 | 40.00 MHz | 30.57 ms | **33.66 ms** ᵐ | 5.02 MB/s | 29.8 fps |
| 50–66.66 MHz | 8 | 50.00 MHz | 24.46 ms | 27.47 ms | 6.28 MB/s | 36.4 fps |
| **66,666,667–99.9 MHz** | **6** | **66.67 MHz** | **18.34 ms** | **21.31 ms** ᵐ | **8.37 MB/s** | **46.8 fps** |
| ≥ 100 MHz | 4 | 100 MHz | 12.3 ms | — | — | **display garbled** |

ᵐ = measured; the rest are the fitted model.

**66.67 MHz is the practical maximum.**  It sits at the ILI9341's 66.7 MHz
write-cycle limit, and the next step up (CDIV=4) is the known-garbled 100 MHz.
`pistompcore.py` requests `66_666_667`.

This is the one axis on which **v2 out-runs v3**: the Pi 5's 200 MHz source
cannot produce 66.67 MHz (it needs an odd divisor), so v3 is stuck at 50 MHz
while v2 pushes a full frame 24% faster.

> **Not electronically verified.**  MISO is not wired on v2 — `RDDID` (0x04)
> returns all zeros — so the panel's GRAM cannot be read back to confirm pixel
> integrity at 66.67 MHz.  The panel accepts the writes without stalling, but
> correctness at this clock rests on visual inspection.

---

## Measured per-call overhead

Wire time is `px × 16 bits / clock`; the fitted `bits_per_pixel` is **15.92**,
i.e. there is no framing overhead.  Everything else is fixed or CPU-bound:

| Term | Cost | Scales with |
|------|------|-------------|
| Payload `write()` overhead (syscall + DMA setup) | **0.48 ms** | nothing — flat across all 7 clocks |
| Address window (5 small writes + DC/CS toggles) | **0.50 ms** | nothing |
| RGB565 pack + driver (`pipeline_ms_per_px`) | `2.36e-5 × px` | pixels (**1.82 ms** full frame) |

The payload-write overhead being constant (0.466–0.505 ms) from 12.5 MHz all the
way to 66.67 MHz is also the proof that `core_freq` is pinned at 400 MHz; a
scaling VPU clock would show up as clock-dependent drift here.

Fixed cost per push is **1.20 ms** (`fixed_ms`) at the Python boundary, not the
~15 µs of kernel-side register writes.  Ten small dirty rects cost 12 ms of pure
overhead before a single pixel moves.

### The pack

`LcdIli9341.update()` quantises to RGB565 with a **single SDL convert-blit** into a
preallocated 16-bit staging surface, not a numpy channel-mask pipeline.  Measured
on this board, end-to-end through `_block` at 66.67 MHz:

| Full frame | numpy pack | SDL convert-blit |
|---|---|---|
| 320×240 | 23.91 ms | **21.31 ms** (−2.59 ms) |

The blit source **must be opaque** — `PanelStack`'s root is XRGB for exactly this
reason.  Blitting an `SRCALPHA` surface silently takes SDL's per-pixel
alpha-blending path instead of a format convert, which on this A53 is *~8× slower
than the numpy pack it replaced*.  See CLAUDE.md "Traps" and
`tools/bench_pack_variants.py`.

**`spidev.bufsiz`** matters exactly as on the Pi 5: the 4096 B default means 38
writes per frame.  `spidev.bufsiz=163840` is already set on the kernel cmdline.

---

## Where the time actually goes

Live profile of the idle main panel (`PISTOMP_PROFILE=1`, 1 s windows).  Note
that `profiling.maybe_start()` is only called by the tuner and NAM panels, so
reproducing this requires starting the reporter explicitly.

> **Captured with the old numpy pack.**  The `lcd.update:pack` row is the one the
> SDL convert-blit changed; the others stand.  Not re-profiled live.

| Stage | Mean | % of one core |
|---|---|---|
| `poll_lcd_updates` | 7.23 ms | 33% |
| ├ `lcd.update:_block` (SPI wire) | 1.94 ms | 11% |
| ├ `widget.do_draw` | 1.32 ms | 7% |
| ├ `lcd.update:pack` | 1.26 ms → **~0.5 ms** | 7% → ~3% |
| ├ `panelstack.recompose` | 0.65 ms | 4% |
| └ unaccounted | ~2.0 ms | — |
| `poll_controls` | 0.83 ms | 8% |

The whole pi-stomp process sat at ~55% of one core with a **92 Hz** main loop, not
the nominal 100.  The pack is now ~2.6× cheaper, so expect an idle tick nearer
6.5 ms — but that is derived from the pack benchmark, not a fresh live profile.

**The SPI transfer is only ~27% of an LCD tick.**  The push is bandwidth-bound
only for large rects; for the small dirty rects of normal operation it is
compute-bound.  Raising the clock from 50 → 66.67 MHz shaves ~0.5 ms off an idle
tick, but cuts a *full-frame* push from 24.46 ms to 18.34 ms of wire — so it pays
off on panel and pedalboard transitions, not on idle animation.

### Why the cost model is per-SoC

A single global constant set used to be defensible: with the numpy pack, a Pi 3A+
refit gave `PIPELINE_MS_PER_PX=4.81e-5` against the Pi 5's `5.86e-5` — near enough
that sharing one value moved the 8 ms gate by 0.5%.

**The SDL convert-blit ended that.**  It is a far bigger win on the A76 than on the
A53, so the two boards diverged:

| | `fixed_ms` | `pipeline_ms_per_px` | full-frame pack |
|---|---|---|---|
| v3 (Pi 5, BCM2712) | 0.2727 | 3.83e-6 | 0.29 ms |
| v2 (Pi 3A+, BCM2837) | 1.2008 | **2.36e-5 (6.2×)** | 1.82 ms |

Both terms are CPU-bound, and `transfer_ms` gates **inline pushes onto the UI
thread** (`PanelStack.INLINE_BUDGET_MS`).  Sharing v3's numbers would let the gate
admit a 31,691 px clip inline on v2 that actually costs **9.56 ms** — against an
8 ms budget on a 10 ms tick, consuming essentially all the slack.  Underestimating
is the unsafe direction, so `spi_timing.PUSH_PROFILE` keys the profile off the
device-tree SoC, and an unrecognised board gets the *slower* profile.

Refit with `tools/bench_lcd_device.py` **on each board** whenever the pack changes.

### Two environmental drags

- **Thermal soft limit.**  `vcgencmd get_throttled` returns `0x80008` (bit 3,
  "soft temp limit active") above 60 °C.  `arm_freq=1400` and `cpufreq` sysfs
  both report 1.4 GHz, but `vcgencmd measure_clock arm` reports **1.2 GHz** —
  the firmware cap is invisible to the standard telemetry.
- **Memory pressure.**  463 MB usable, ~86 MB available, with ~150 MB compressed
  into zram.  Steady-state `si`/`so` are ~0, so it is not thrashing, but fresh
  allocations (opening a menu, building a panel, loading a pedalboard) can stall
  the main thread on decompression.

---

## Coalescing cuts both ways

`PanelStack._pending_lcd_clip` merges pending pushes with `Box.union`, which is a
**bounding box**.  Because wire time is linear in pixels, merging disjoint rects
can cost far more than pushing them separately:

| | Separate | Coalesced to bounding box |
|---|---|---|
| 4 × (32×131) rects, disjoint | 9.8 ms | 29.3 ms (full screen) |

Coalescing wins on per-push overhead (~1.0 ms each) and on genuine overlap; it
loses whenever the union area exceeds the summed areas by more than that.
`PanelStack.INLINE_BUDGET_MS = 8.0` defers anything estimated over 8 ms, which is
a latency guard for the 10 ms tick, not a throughput optimization.

Dirty-rect **culling** — pushing fewer pixels — remains the primary lever, as on
the Pi 5.

---

## Summary

| What | Value |
|------|-------|
| SPI driver | `spi-bcm2835` |
| LCD device node | `/dev/spidev0.0` (CE0) |
| ADC device node | `/dev/spidev0.1` (CE1, own fd, 1 MHz) |
| Clock source | VPU core clock = 400 MHz (pinned) |
| Divisor rule | **Round up to even** (`cdiv += cdiv % 2`) |
| Practical max speed | **66.67 MHz** (request ≥ `66_666_667`) |
| Configured in `pistompcore.py` | `spi_speed_hz=66_666_667` |
| Peak payload throughput | **8.37 MB/s** measured (8.33 MB/s theoretical) |
| Full-frame wire time | 24.46 ms @ 50 MHz → **18.34 ms @ 66.67 MHz** |
| Full-frame total | **21.31 ms** @ 66.67 MHz (was 23.91 ms with the numpy pack) |
| PCIe DMA stall | None (on-die DMA) |
| RGB565 pack | SDL convert-blit; source **must be opaque** |
| Fixed overhead/push | 1.20 ms (`PUSH_PROFILE[bcm2837].fixed_ms`) |
| Per-pixel pipeline | 2.36e-5 ms/px — **6.2× the Pi 5's**, hence per-SoC constants |
| SPI share of an idle LCD tick | ~27% (the rest is CPU) |
| Primary optimization lever | Dirty-rect culling |
