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

Full-frame (320×240 = 76,800 px, 153,600 B) medians, service stopped.
"Total" is `pack + address-window + payload write`; MB/s is payload/wire.

| Requested | CDIV | **Actual** | Wire | Total | Throughput | Full-frame ceiling |
|-----------|------|-----------|---------|---------|----------|-----|
| 12.5 MHz | 32 | 12.50 MHz | 98.77 ms | 102.87 ms | 1.56 MB/s | 9.7 fps |
| 20 MHz | 20 | 20.00 MHz | 61.90 ms | 65.93 ms | 2.48 MB/s | 15.2 fps |
| 25–28.5 MHz | 16 | 25.00 MHz | 49.63 ms | 53.70 ms | 3.09 MB/s | 18.6 fps |
| 33.3 MHz | 14 | 28.57 MHz | 43.49 ms | 47.63 ms | 3.53 MB/s | 21.0 fps |
| 40–44.4 MHz | 10 | 40.00 MHz | 31.18 ms | 35.53 ms | 4.93 MB/s | 28.1 fps |
| 50–66.66 MHz | 8 | 50.00 MHz | 25.05 ms | 29.23 ms | 6.13 MB/s | 34.2 fps |
| **66,666,667–99.9 MHz** | **6** | **66.67 MHz** | **18.94 ms** | **23.30 ms** | **8.11 MB/s** | **42.9 fps** |
| ≥ 100 MHz | 4 | 100 MHz | 12.3 ms | — | — | **display garbled** |

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

Wire time is `px × 16 bits / clock`; `BITS_PER_PIXEL` fits to **16.00**, i.e.
there is no framing overhead.  Everything else is fixed or CPU-bound:

| Term | Cost | Scales with |
|------|------|-------------|
| Payload `write()` overhead (syscall + DMA setup) | **0.48 ms** | nothing — flat across all 7 clocks |
| Address window (5 small writes + DC/CS toggles) | **0.50 ms** | nothing |
| RGB565 pack, idle | `0.36 ms + 4.23e-5 × px` | pixels (3.61 ms full frame) |
| RGB565 pack, under service load | `0.41 ms + 6.56e-5 × px` | pixels (5.45 ms full frame) |

The payload-write overhead being constant (0.466–0.505 ms) from 12.5 MHz all the
way to 66.67 MHz is also the proof that `core_freq` is pinned at 400 MHz; a
scaling VPU clock would show up as clock-dependent drift here.

Fixed cost per push is therefore **~1.0 ms** at the Python boundary, not the
~15 µs of kernel-side register writes.  Ten small dirty rects cost 10 ms of pure
overhead before a single pixel moves.

**`spidev.bufsiz`** matters exactly as on the Pi 5: the 4096 B default means 38
writes per frame.  `spidev.bufsiz=163840` is already set on the kernel cmdline.

---

## Where the time actually goes

Live profile of the idle main panel (`PISTOMP_PROFILE=1`, 1 s windows).  Note
that `profiling.maybe_start()` is only called by the tuner and NAM panels, so
reproducing this requires starting the reporter explicitly.

| Stage | Mean | % of one core |
|---|---|---|
| `poll_lcd_updates` | 7.23 ms | 33% |
| ├ `lcd.update:_block` (SPI wire) | 1.94 ms | 11% |
| ├ `widget.do_draw` | 1.32 ms | 7% |
| ├ `lcd.update:pack` | 1.26 ms | 7% |
| ├ `panelstack.recompose` | 0.65 ms | 4% |
| └ unaccounted | ~2.0 ms | — |
| `poll_controls` | 0.83 ms | 8% |

The whole pi-stomp process sits at ~55% of one core, and the main loop achieves
**92 Hz**, not the nominal 100.

**The SPI transfer is only 27% of an LCD tick.**  The push is bandwidth-bound
only for large rects; for the small dirty rects of normal operation it is
compute-bound.  Raising the clock from 50 → 66.67 MHz shaves ~0.5 ms off a
7.2 ms idle tick (~7%), but cuts a *full-frame* push from 25.05 ms to 18.94 ms —
so it pays off on panel and pedalboard transitions, not on idle animation.

`uilib/spi_timing.py`'s constants were fit on a Pi 5 and already predict Pi 3A+
totals to within ~5% (mean 4.6%).  A Pi 3A+ refit gives `FIXED_MS=0.95`,
`PIPELINE_MS_PER_PX=4.81e-5`, `BITS_PER_PIXEL=16.0` (mean error 2.2%) and moves
the 8 ms inline-push gate from 19,244 px to 19,144 px — a 0.5% shift, not worth
per-device constants.

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
| Peak payload throughput | **8.11 MB/s** measured (8.33 MB/s theoretical) |
| Full-frame wire time | 25.05 ms @ 50 MHz → **18.94 ms @ 66.67 MHz** |
| PCIe DMA stall | None (on-die DMA) |
| Fixed overhead/push | ~1.0 ms (0.48 payload write + 0.50 address window) |
| SPI share of an idle LCD tick | ~27% (the rest is CPU) |
| Primary optimization lever | Dirty-rect culling |
