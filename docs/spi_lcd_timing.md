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
│  CPU / DRAM      │◄─────────►│  dw_axi_dmac                │
│  kernel tx_buf   │           │    ↓ reads host DRAM        │
│  (spidev bounce) │           │  DW APB SSI (SPI ctrl)      │
└──────────────────┘           │    ↓ FIFO → wire            │
                               │  ILI9341 display            │
                               └─────────────────────────────┘
```

**SPI driver**: `spi_dw_mmio` → `spi_dw` (Synopsys DesignWare APB SSI,
`snps,dw-apb-ssi`).  There is no `spi-rp1.c`; the RP1's SPI peripheral is a
generic DW IP block.

**DMA driver**: `dw_axi_dmac_platform` (Synopsys AXI DMA, `snps,axi-dma-1.01a`)
— lives inside RP1.  It reads source data from BCM2712 DRAM via PCIe inbound
window (`IB MEM 0x0000000000..0x0fffffffff`).

---

## The clock divisor trap

The DW APB SSI forces the SPI clock divider to an even number
(`spi-dw-core.c`: `clk_div = ... & 0xfffe`).  The RP1 `ssi_clk` source is
**200 MHz**.  Achievable speeds near the range of interest:

| Requested | Divisor | **Actual speed** | Full-frame wire time |
|-----------|---------|------------------|----------------------|
| ≤ 80 MHz  | 4       | **50 MHz**       | 24.6 ms              |
| 81–200 MHz | 2      | **100 MHz**      | 12.3 ms              |

**Requesting 80 MHz gives 50 MHz.**  Requesting 125 MHz (or any value 81–200)
gives 100 MHz — the fastest achievable.

The `lcd.spi_speed_mhz` setting in `settings.yml` should be set to **125** (or
higher) to obtain 100 MHz actual.  The ILI9341 datasheet rates the write cycle
at 10 MHz; 100 MHz is a 10× overclock that works reliably with short traces.

---

## Full write() path — one full-frame push

Path for a single `os.write(fd, data)` call of 153,600 bytes (320×240 @ 16 bpp).

| Stage | Kernel location | Scales with clock? | Scales with bytes? | Approx. time |
|-------|----------------|--------------------|--------------------|-------------|
| syscall + VFS + `spidev` mutex | `spidev.c:188` | No | No | ~3 µs |
| `copy_from_user(tx_buffer, buf, N)` — userspace→kernel bounce | `spidev.c:193` | No | Yes (fast) | ~30 µs |
| `spi_sync` fast path → `transfer_one_message` | `spi.c:4552` | No | No | ~2 µs |
| `dma_map_sgtable` — ARM64 cache flush of bounce buffer | `spi.c:1186` | No | Yes | ~5 µs |
| `dw_spi_transfer_one`: CS + CTRLR0 config (PCIe MMIO writes) | `spi-dw-core.c:523` | No | No | ~5 µs |
| DMA descriptor build (`dw_axi_dma_chan_prep_slave_sg`) | `dw-axi-dmac-platform.c:946` | No | No (1 descriptor) | ~3 µs |
| `dma_async_issue_pending` — kick DMA via PCIe MMIO | `spi-dw-dma.c:537` | No | No | ~5 µs |
| **Wire time** (bits on clock) | hardware | **Yes, inversely** | Yes | **12.3 ms @ 100 MHz** |
| **PCIe DMA stall** (see below) | hardware | No | Yes | **~3.9 ms @ 100 MHz** |
| DMA completion IRQ + `complete()` wakeup (PREEMPT_RT thread) | `spi-dw-dma.c` | No | No | ~20–50 µs |
| `dma_unmap_sgtable` | `spi.c:1207` | No | Yes | ~5 µs |
| `mutex_unlock` + return to userspace | kernel | No | No | ~2 µs |

**Total at 100 MHz actual: ~16.1 ms.**  Fixed overhead is ~100 µs; the
remaining ~16 ms is wire time + PCIe stall.

### DMA path detail

`spidev` allocates a static kernel bounce buffer (`tx_buffer`, allocated at
open).  Each `write()` copies the user payload into it (`copy_from_user`), then
calls `spi_sync()` which DMA-maps the buffer and hands it to the DW SPI
driver.  The DW AXI DMA controller inside RP1 then reads this buffer from
BCM2712 DRAM **via PCIe** in 16-byte bursts and feeds the SPI TX FIFO.

### DMA threshold (IRQ vs DMA selection)

`dw_spi_can_dma` (`spi-dw-dma.c:253`) returns false when
`xfer->len <= dws->fifo_len`.  The DW APB SSI FIFO on RP1 is **64 entries**
(confirmed by probing the TXFTLR register).  With 2-byte words this is 128
bytes.

- Transfers ≤ 128 bytes: **IRQ path** — one TX-empty interrupt, ~30 µs fixed cost.
- Transfers > 128 bytes: **DMA path** — bulk DMA with ~100 µs fixed cost.

A full frame (153,600 bytes) always uses DMA.

---

## The PCIe DMA stall

At 100 MHz SPI clock, the TX FIFO drains 16 bytes in **1.28 µs**.  The RP1
DMA fetches the next 16-byte burst from BCM2712 DRAM over PCIe with a
round-trip latency of ~**400 ns**.  Since 400 ns > 0 but < 1.28 µs the FIFO
occasionally starves mid-transfer.

Measured overhead = **31% of wire time** at 100 MHz, consistent with
`400 ns / 1.28 µs ≈ 31%`.  At 50 MHz the same 16 bytes take 2.56 µs — the
DMA has time to pipeline and stall overhead is near zero.

### Can this be reduced?

| Approach | Feasibility | Expected gain |
|----------|------------|---------------|
| Faster PCIe (Gen 3) | **No** — RP1 link is Gen 2 fixed in silicon | — |
| Larger DMA burst size | Possible via kernel driver patch; capped at `min(dma_caps_max, fifo_len/2)` = 64 bytes | halves stall (~2 ms) |
| BCM2712 DMA push instead of RP1 pull | Major rework; bypasses the stall entirely | eliminates ~3.9 ms |
| Reduce pixel count (dirty-rect culling) | **Yes, in software today** | linear with area |

Dirty-rect culling is the most actionable lever: both wire time and PCIe stall
scale linearly with pixels pushed.

### BCM2712 DMA push (explained)

The current flow is **RP1 pulling**: RP1's `dw_axi_dmac` initiates PCIe **read**
transactions to fetch data from BCM2712 DRAM.  A PCIe read requires a
round-trip — RP1 sends a Read Request TLP, waits for BCM2712 to return a
Completion TLP with the data, then issues the next read.  That ~400 ns
wait-per-burst is the stall.

PCIe **writes** have no such round-trip.  A write TLP is fire-and-forget; the
initiator does not wait for a completion before sending the next one.  Writes
can be fully pipelined up to the link bandwidth limit (~500 MB/s on Gen 2),
which is far above the ~10 MB/s the SPI transfer actually needs.

A **BCM2712 DMA push** would flip the initiator: instead of RP1 reading,
BCM2712's own DMA engine would write data directly to RP1's SPI TX FIFO
register address over PCIe.  No round-trip, no stall.

Why it is not straightforward: the `spi_dw` driver is written entirely from
RP1's perspective — it programs RP1's own registers and uses RP1's
`dw_axi_dmac`.  A BCM2712-side push would require a driver that (a) knows the
PCIe outbound address of RP1's SPI FIFO from BCM2712's address space, (b) uses
BCM2712's DMA engine (a different driver entirely), and (c) manages SPI FIFO
flow control without cheap access to RP1's FIFO-depth registers.  It is
effectively a ground-up rewrite of the SPI transfer path against the grain of
how the driver stack is structured.

---

## Effect of chunk size (`spidev.bufsiz`)

Each `os.write()` call is limited to `bufsiz` bytes (default 4096).
`lcd_ili9341.py` reads `/sys/module/spidev/parameters/bufsiz` and chunks
accordingly.  Measured at 100 MHz actual (125 MHz requested):

| Chunk size | Writes | Total time |
|------------|--------|-----------|
| 4,096 B | 38 | 18.3 ms |
| 8,192 B | 19 | 17.3 ms |
| 16,384 B | 10 | 16.8 ms |
| 32,768 B | 5 | 16.4 ms |
| 65,536 B | 3 | 16.3 ms |
| 153,600 B | 1 | **16.1 ms** |

Each additional `write()` call costs ~55 µs (syscall + copy + DMA setup +
completion).  38 chunks wastes ~2 ms versus a single write.

`spidev.bufsiz=163840` is set on the kernel command line in
`pistomp-arch/files/cmdline.txt`, so `lcd_ili9341.py` already performs a
single write per frame.  Do not remove this parameter.

---

## Making the transfer async

The 16.1 ms that `write()` blocks Python is the dominant cost for the poll
loop.  Wire time and PCIe stall are hardware-fixed and cannot be eliminated, but
both can be hidden by decoupling the LCD push from the main thread.  Two
approaches are available.

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
  os.write(spidev_fd, data)              # blocks 16.1 ms on worker thread
  lock.release()
```

`LcdIli9341` already has `self.lock`; the only change is moving the `update()`
body onto a thread and making the call-site non-blocking.

**What changes:**

| Metric | Before | After |
|--------|--------|-------|
| Poll loop blocked per frame | 16.1 ms | ~0 ms (lock check only) |
| Wall-clock frame latency | 16.1 ms | 16.1 ms (unchanged — same hardware) |
| Visible tearing risk | None (sequential) | Low — drop-frame policy means LCD always shows a complete frame |
| Kernel / boot changes | None | None |
| Partial update (`box=`) | Works as-is | Works as-is |

The trade-off is frame rate, not latency.  At 100 MHz actual the SPI transfer
takes 16.1 ms; a new frame cannot start until it finishes, so the display
updates at most once per 16.1 ms (~62 fps ceiling).  The poll loop is free to do
other work during that window.

This is the lowest-risk path: no changes outside `uilib/lcd_ili9341.py`, no
kernel driver verification, and the existing dirty-rect and partial-update
infrastructure is unaffected.

---

### Framebuffer via `panel-mipi-dbi-spi`

The Linux `panel-mipi-dbi-spi` DRM driver presents the ILI9341 as a standard
framebuffer (`/dev/fb0`).  A `write()` to `/dev/fb0` copies the pixel data into
a kernel-managed framebuffer and returns immediately; the actual SPI transfer
runs in a DRM worker thread.

**Hardware path is identical.**  `panel-mipi-dbi-spi` programs the same RP1 DW
APB SSI controller via the same `spi_dw_mmio` driver and the same
`dw_axi_dmac` DMA path.  Wire time (12.3 ms) and PCIe stall (3.9 ms) are
unchanged.

**What changes:**

| Metric | spidev (`os.write`) | `/dev/fb0` (mipi-dbi) |
|--------|--------------------|-----------------------|
| `write()` blocks caller for | 16.1 ms | ~30 µs (kernel copy only) |
| SPI transfer runs on | caller's thread | DRM worker thread |
| Wire time + PCIe stall | 16.1 ms | 16.1 ms (same hardware) |
| Partial update | ILI9341 address window | DRM damage rect → full flush |
| Double-buffer / tearing | N/A (sequential) | Needed for clean frames |

The async benefit is the same as the background thread, but achieved in the
kernel rather than in Python.

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

## Summary

| What | Value |
|------|-------|
| SPI driver | `spi_dw_mmio` + `spi_dw` (DesignWare APB SSI) |
| DMA driver | `dw_axi_dmac_platform` (inside RP1, reads host DRAM via PCIe) |
| RP1 SPI source clock | 200 MHz |
| Clock divisor constraint | Even only (`& 0xfffe`) |
| 80 MHz requested → actual | **50 MHz** (div=4) |
| ≥81 MHz requested → actual | **100 MHz** (div=2) — hardware maximum |
| Full-frame time @ 50 MHz | ~24.7 ms (wire-dominated, near-zero PCIe stall) |
| Full-frame time @ 100 MHz | ~16.1 ms (12.3 ms wire + 3.9 ms PCIe stall) |
| DMA/IRQ crossover | 128 bytes (FIFO depth) |
| Optimal `spidev.bufsiz` | ≥153,600 (set to 163,840 in cmdline) |
| Primary optimization lever | Dirty-rect culling (linear in pixel count) |
