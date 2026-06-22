# SPI LCD Timing Analysis — Pi 5 / RP1

Investigation of the full kernel path for pushing a 320×240 16-bit frame to
the ILI9341 display over SPI on Raspberry Pi 5.  All measurements were taken
on-device with a PREEMPT_RT kernel (`linux 6.18.33-3-rpi-rt-v8-rt`).

---

## Hardware architecture

The Pi 5 is not a BCM2835/6/7 system.  All I/O (SPI, GPIO, USB, etc.) lives
in the **RP1** chip, a secondary I/O die connected to the BCM2712 main SoC via
**PCIe Gen 2**.  This PCIe hop is the dominant source of non-obvious overhead.

```
BCM2712 (main SoC)              RP1 (I/O die)
┌──────────────────┐  PCIe G2  ┌─────────────────────────────┐
│  CPU / DRAM      │◄─────────►│  rp1_dma (dw_axi_dmac)      │
│  kernel tx_buf   │           │    ↓ reads host DRAM        │
│  (spidev bounce) │           │  rp1_spi0 (DW APB SSI)      │
└──────────────────┘           │    ↓ FIFO → wire            │
                               │  ILI9341 display (CE0)      │
                               │  MCP3008 ADC     (CE1)      │
                               └─────────────────────────────┘
```

**SPI driver**: `spi_dw_mmio` → `spi_dw` (Synopsys DesignWare APB SSI,
`snps,dw-apb-ssi`).  The RP1's SPI peripheral (`rp1_spi0`) is a generic DW IP
block clocked from `RP1_CLK_SYS`.

**DMA driver**: `dw_axi_dmac_platform` (RP1's internal AXI DMA,
`snps,axi-dma-1.01a`) — reads source data from BCM2712 DRAM via PCIe inbound
window.

**Device nodes** (both on the same `rp1_spi0` controller, `/dev/spidev0.x`):
- `/dev/spidev0.0` — ILI9341 LCD (CE0)
- `/dev/spidev0.1` — MCP3008 ADC (CE1)

**Note**: `spidev10.0` (`spi@7d004000`, `brcm,bcm2835-spi`, `clk_vpu` 750 MHz)
is a separate BCM2712 firmware SPI peripheral limited to 20 MHz by its DT
node.  It is not used by pi-stomp for the LCD or ADC.

---

## The clock divisor constraint

The DW APB SSI forces the SPI clock divisor (BAUDR) to an even number
(`spi-dw-core.c`: `clk_div = ALIGN(DIV_ROUND_UP(clk_hz, speed_hz), 2)`).
The RP1 `ssi_clk` source is `RP1_CLK_SYS` = **200 MHz**.

Achievable speeds near the range of interest:

| Requested | BAUDR | **Actual speed** | Full-frame wire time |
|-----------|-------|------------------|----------------------|
| ≤ 99 MHz  | 4     | **50 MHz**       | 24.6 ms              |
| ≥ 100 MHz | 2     | **100 MHz**      | 12.3 ms              |

**Requesting 81 MHz gives 50 MHz** (`ceil(200/81)=3` → rounds to BAUDR=4).
Requesting 100 MHz (or any value 100–200) gives 100 MHz — the fastest
achievable.

**Do not request ≥ 100 MHz.** The ILI9341 write cycle minimum is 15 ns
(66.7 MHz maximum).  At 100 MHz actual the display receives out-of-spec timing
and renders garbage.

66.7 MHz is not achievable: it would require BAUDR=3 (odd), which the
hardware forbids.  The safe maximum is **50 MHz** (any request in 56–99 MHz).

---

## Full write() path — one full-frame push

Path for a single `os.write(fd, data)` call of 153,600 bytes (320×240 @ 16 bpp).

| Stage | Kernel location | Scales with clock? | Scales with bytes? | Approx. time |
|-------|----------------|--------------------|--------------------|-------------|
| syscall + VFS + `spidev` mutex | `spidev.c:188` | No | No | ~3 µs |
| `copy_from_user(tx_buffer, buf, N)` — userspace→kernel bounce | `spidev.c:193` | No | Yes (fast) | ~30 µs |
| `spi_sync` fast path → `transfer_one_message` | `spi.c:4552` | No | No | ~2 µs |
| `dma_map_sgtable` — ARM64 cache flush of bounce buffer | `spi.c:1186` | No | Yes | ~5 µs |
| `dw_spi_transfer_one`: CS + CTRLR0 + BAUDR config (PCIe MMIO writes) | `spi-dw-core.c:523` | No | No | ~5 µs |
| DMA descriptor build (`dw_axi_dma_chan_prep_slave_sg`) | `dw-axi-dmac-platform.c:946` | No | No (1 descriptor) | ~3 µs |
| `dma_async_issue_pending` — kick DMA via PCIe MMIO | `spi-dw-dma.c:537` | No | No | ~5 µs |
| **Wire time** (bits on clock) | hardware | **Yes, inversely** | Yes | **24.6 ms @ 50 MHz** |
| **PCIe DMA stall** (see below) | hardware | No | Yes | **~0 ms @ 50 MHz** |
| DMA completion IRQ + `complete()` wakeup (PREEMPT_RT thread) | `spi-dw-dma.c` | No | No | ~20–50 µs |
| `dma_unmap_sgtable` | `spi.c:1207` | No | Yes | ~5 µs |
| `mutex_unlock` + return to userspace | kernel | No | No | ~2 µs |

**Total at 50 MHz actual: ~25 ms.**  Fixed overhead is ~100 µs; wire time
dominates and the PCIe stall is near-zero at 50 MHz.

---

## The PCIe DMA stall

At 100 MHz SPI clock (BAUDR=2), the TX FIFO drains 16 bytes in **1.28 µs**.
The RP1 DMA fetches the next 16-byte burst from BCM2712 DRAM over PCIe with
a round-trip latency of ~**400 ns**.  Since 400 ns > 0 but < 1.28 µs the FIFO
occasionally starves mid-transfer.

Measured overhead at 100 MHz ≈ **31% of wire time** (≈ 3.8 ms on top of
12.3 ms wire).  At 50 MHz the 16-byte drain takes 2.56 µs — DMA has time to
pipeline and stall is near-zero.

This stall is why 100 MHz would measure ~16 ms total despite 12.3 ms wire
time — **but 100 MHz garbles the ILI9341 regardless**, so this is academic.

---

## Effect of chunk size (`spidev.bufsiz`)

Each `os.write()` is limited to `bufsiz` bytes.  Default is 4096; a full frame
requires 38 chunks.  Each chunk costs ~38 µs fixed overhead (syscall + copy +
CS toggle), adding ~1.5 ms per frame.

Setting `spidev.bufsiz=163840` on the kernel command line (in
`pistomp-arch/files/cmdline.txt`) reduces this to a single write per frame.
Measured improvement at 50 MHz actual:

| Chunk size | Writes | Total time |
|------------|--------|------------|
| 4,096 B    | 38     | ~26.5 ms   |
| 153,600 B  | 1      | ~25.0 ms   |

The gain is ~1.5 ms — modest given the 25 ms wire time dominates.

---

## Making the transfer async

The ~25–26 ms that `write()` blocks Python is the dominant cost for the poll
loop.  Wire time is hardware-fixed, but it can be hidden by decoupling the LCD
push from the main thread.

### Background thread

Wrap `LcdIli9341.update()` in a daemon thread.  The poll loop calls a
non-blocking submit; if the previous transfer is still in progress it drops the
frame.

```
poll loop (10 ms cadence)
  → submit_frame(surface, clip)           # non-blocking
      if lock.locked(): return            # drop frame
      Thread(target=_do_update).start()

_do_update()                              # runs on worker thread
  lock.acquire()
  numpy pack + rot90   (~1 ms)
  os.write(spidev_fd, data)              # blocks ~25 ms on worker thread
  lock.release()
```

`LcdIli9341` already has `self.lock`; the only change is moving the `update()`
body onto a thread and making the call-site non-blocking.

**What changes:**

| Metric | Before | After |
|--------|--------|-------|
| Poll loop blocked per frame | ~25 ms | ~0 ms (lock check only) |
| Wall-clock frame latency | ~25 ms | ~25 ms (unchanged — same hardware) |
| Visible tearing risk | None (sequential) | Low — drop-frame policy means LCD always shows a complete frame |
| Kernel / boot changes | None | None |
| Partial update (`box=`) | Works as-is | Works as-is |

---

### Framebuffer via `panel-mipi-dbi-spi`

The Linux `panel-mipi-dbi-spi` DRM driver presents the ILI9341 as a standard
framebuffer (`/dev/fb0`).  A `write()` to `/dev/fb0` copies the pixel data into
a kernel-managed framebuffer and returns immediately; the actual SPI transfer
runs in a DRM worker thread.

**Hardware path is identical.**  Wire time (~24.6 ms) and PCIe stall
(near-zero at 50 MHz) are unchanged.

**What changes:**

| Metric | spidev (`os.write`) | `/dev/fb0` (mipi-dbi) |
|--------|--------------------|-----------------------|
| `write()` blocks caller for | ~25 ms | ~30 µs (kernel copy only) |
| SPI transfer runs on | caller's thread | DRM worker thread |
| Wire time | ~24.6 ms | ~24.6 ms (same hardware) |
| Partial update | ILI9341 address window | DRM damage rect → full flush |
| Double-buffer / tearing | N/A (sequential) | Needed for clean frames |

**Implementation requirements** (all in `pistomp-arch`):

1. **DC pin**: The `mipi-dbi-spi` overlay parameter must be `dtparam=dc-gpio=6`.
   GPIO 6 is the DC line (confirmed in `lcd-splash.c:43`).  Common guides
   incorrectly list `dc-gpio=8` (which is CE0, a chip-select line).

2. **Firmware blob**: The ILI9341 init sequence must be compiled with
   `mipi-dbi-cmd` into `panel.bin` and installed to `/lib/firmware/`.  This
   replaces the init sequence currently in `lcd-splash.c` and
   `LcdIli9341.__init__`.

3. **`lcd-splash` conflict**: `lcd-splash.c` drives GPIO 6 (DC) and GPIO 8/0
   (CS) directly via lgpio.  The `mipi-dbi-spi` driver claims those pins at
   boot via device tree; both cannot coexist.  `lcd-splash` would need to be
   rewritten as a DRM client (opening `/dev/dri/cardX`, issuing a
   `drmModeSetCrtc`) or replaced.

4. **Kernel driver availability**: `CONFIG_DRM_MIPI_DBI` must be set in the
   running kernel.  Verify on-device: `zcat /proc/config.gz | grep MIPI_DBI`.
   The stock `linux-rpi` kernel includes it; `linux-rpi-rt` depends on the base
   ALARM config and should be checked before building.

5. **`INIT_STAMP` / splash handoff**: `LcdIli9341.has_system_splash` reads
   `/run/lcd.init` to detect whether the display was already initialised this
   boot.  With a kernel driver the init sequence runs at module load, not via
   lcd-splash; the stamp mechanism would need redesigning.

**Python-side changes**: Replace `LcdIli9341` with a thin writer that opens
`/dev/fb0`, packs RGB565, and calls `write()`.  Rotation must be pre-applied
in numpy (same as today) or configured via `MADCTL` in the firmware blob to
make the panel landscape-native (eliminating the `rot90` step entirely).

**When to prefer this over the background thread**: If DRM integration is
wanted for other reasons (console on the display, compositor, hardware
page-flip with vsync), the mipi-dbi path is the right long-term direction.
For the sole goal of unblocking the poll loop, the background thread is
simpler and has no boot-infrastructure cost.

---

## Shared bus: LCD and ADC interaction

Both the ILI9341 (CE0) and MCP3008 (CE1) share `rp1_spi0`.  The DW SSI
driver reconfigures BAUDR per-transfer per chip-select, so the two devices
run at their own speeds without interfering:

| Device | `spi-max-frequency` | BAUDR | Actual clock | Transfer time |
|--------|---------------------|-------|-------------|---------------|
| ILI9341 LCD | 56–99 MHz | 4 | 50 MHz | ~25 ms (full frame) |
| MCP3008 ADC | 1 MHz | 200 | 1 MHz | ~24 µs (24 bits) |

The shared bus is a **serialising mutex** — an LCD frame push and an ADC read
cannot overlap; one blocks until the other releases the controller.  In
practice this is not an issue: ADC reads are ~24 µs, so even if one lands
mid-frame-push it queues and completes within microseconds of the frame
finishing.  The 10 ms ADC poll cadence is far slower than either transfer.

The MCP3008 is rated to 1.35 MHz max at 3.3V.  Operating at 1 MHz (BAUDR=200)
is within spec; the previous 240 kHz setting (BAUDR=834) was conservative and
buys nothing in a low-noise on-board trace environment.

## Primary optimization lever: dirty-rect culling

Both wire time and PCIe stall scale linearly with pixels pushed.  Culling to
only the changed region of the screen is the most impactful software-side
optimization and requires no kernel or boot changes.

---

## Summary

| What | Value |
|------|-------|
| SPI driver | `spi_dw_mmio` + `spi_dw` (DesignWare APB SSI) |
| DMA driver | `dw_axi_dmac_platform` (inside RP1, reads host DRAM via PCIe) |
| LCD device node | `/dev/spidev0.0` (rp1_spi0, CE0) |
| ADC device node | `/dev/spidev0.1` (rp1_spi0, CE1) |
| RP1 SPI source clock | `RP1_CLK_SYS` = 200 MHz |
| Clock divisor constraint | Even only (`ALIGN(DIV_ROUND_UP(...), 2)`) |
| 81 MHz requested → actual | **50 MHz** (BAUDR=4) — `ceil(200/81)=3` → rounds to 4 |
| ≥ 100 MHz requested → actual | **100 MHz** (BAUDR=2) — **display garbled** (ILI9341 max 66.7 MHz) |
| 66.7 MHz achievable? | **No** — requires BAUDR=3 (odd, forbidden) |
| Safe maximum setting | Any value 56–99 MHz (all give 50 MHz actual) |
| Full-frame time @ 50 MHz | ~25 ms (24.6 ms wire + ~0 PCIe stall + ~0.4 ms overhead) |
| DMA/IRQ crossover | 128 bytes (FIFO depth × 2-byte words) |
| Optimal `spidev.bufsiz` | ≥153,600 (set to 163,840 in `pistomp-arch/files/cmdline.txt`) |
| Primary optimization lever | Dirty-rect culling (linear in pixel count) |

---

## Appendix: Pi 3A+ (v2 hardware)

The v2 pi-stomp uses a Raspberry Pi 3A+ (BCM2837B0).  The SPI peripheral is
**on-die** — there is no PCIe hop.  The Linux driver is `spi-bcm2835`, not
`spi_dw_mmio`.

### Clock source and divisor rule

| | Pi 5 (RP1) | Pi 3A+ (BCM2837B0) |
|---|---|---|
| SPI clock source | `RP1_CLK_SYS` = 200 MHz | VPU core clock = 400 MHz |
| Divisor constraint | Even only (`ALIGN(…, 2)`) | **Power of 2 only** (`roundup_pow_of_two()`) |

`spi-bcm2835.c` computes `cdiv = roundup_pow_of_two(DIV_ROUND_UP(400_000_000, speed_hz))`.
At 400 MHz VPU the BCM2835 SPI CDIV register only works reliably with power-of-2
divisors (confirmed hardware constraint, raspberrypi/linux #2286).  Setting
`core_freq=250` in `config.txt` restores arbitrary even divisors but slows the
SDRAM interface and is not recommended.

### Achievable speeds near the ILI9341 limit

| Requested | CDIV | **Actual speed** | Full-frame wire time |
|-----------|------|------------------|----------------------|
| 51–99 MHz | 8 | **50 MHz** | 24.6 ms |
| ≥ 100 MHz | 4 | **100 MHz** | 12.3 ms — **display garbled** |
| ≤ 50 MHz  | 8–16 | 50 or 25 MHz | 24.6–49.2 ms |

`DIV_ROUND_UP(400, 99) = 5` → `roundup_pow_of_two(5) = 8` → 50 MHz.
`DIV_ROUND_UP(400, 100) = 4` → already pow2 → 100 MHz (garbled, same as Pi 5).

66.7 MHz is not achievable: it requires CDIV=6 (not a power of 2).
**Safe maximum is 50 MHz** (any request 51–99 MHz), identical to Pi 5.

### Differences from Pi 5

**No PCIe stall.**  BCM2835 DMA accesses SDRAM directly.  The 31% overhead
observed at 100 MHz on Pi 5 does not apply.  At 50 MHz this was near-zero on
Pi 5 too, so wire time is identical.

**Lower fixed overhead per transfer.**  CS/BAUDR/DMA-kick register writes hit
on-die MMIO directly (~1 ns) rather than over PCIe (~200 ns per write).
Fixed overhead per frame is ~10–15 µs vs ~100 µs on Pi 5.

**`spidev.bufsiz` matters identically.**  Default 4096 B → 38 writes per
frame → ~1.5 ms wasted overhead.  Same `spidev.bufsiz=163840` fix applies.

### Summary (Pi 3A+)

| What | Value |
|------|-------|
| SPI driver | `spi-bcm2835` |
| Clock source | VPU core clock = 400 MHz |
| Divisor rule | Power of 2 only |
| Safe max speed | **50 MHz** |
| Full-frame wire time | **~24.6 ms** (identical to Pi 5) |
| PCIe DMA stall | None (on-die DMA) |
| Fixed overhead/frame | ~15 µs |
| Primary optimization lever | Dirty-rect culling (same as Pi 5) |
