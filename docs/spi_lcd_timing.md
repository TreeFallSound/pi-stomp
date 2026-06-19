# SPI LCD Timing Analysis — Pi 5 / BCM2712

Investigation of the full kernel path for pushing a 320×240 16-bit frame to
the ILI9341 display over SPI on Raspberry Pi 5.  All measurements were taken
on-device with a PREEMPT_RT kernel (`linux 6.18.33-3-rpi-rt-v8-rt`).

---

## Hardware architecture

```
BCM2712 (main SoC)
┌──────────────────────────────────────┐
│  CPU / DRAM                          │
│  kernel tx_buf (spidev bounce)       │
│  BCM SPI master (107d004000)         │
│    ↓ wire → GPIO pins                │
│  ILI9341 display                     │
└──────────────────────────────────────┘
```

**SPI controller**: `spi-bcm2835` driver, hardware at `107d004000`.

**Device nodes**:
- `/dev/spidev0.0` — ILI9341 LCD (CE0)
- `/dev/spidev0.1` — MCP3008 ADC (CE1)

Both share the same SPI controller.  The RP1 DW APB SSI at `1f00050000`
(`spi10`) is a separate controller not used by either the display or the ADC.

The BCM SPI controller lives at `107d004000`, which is in BCM2712's own
peripheral address space — **not** inside the PCIe BAR (`1f00000000`).
There is no PCIe hop in the SPI data path.

---

## Clock control

The BCM SPI controller receives its clock from `vpu-clock` (750 MHz).  Speed
is controlled by the clock tree — the CDIV register at offset `0x08` is
always `4` regardless of the requested rate; the driver calls `clk_set_rate()`
on the parent clock and the clock tree snaps to the nearest achievable rate.

Measured actual speeds (on-device, full-frame wire time, spidev0.0):

| Requested range | Actual speed | Full-frame wire time |
|-----------------|-------------|----------------------|
| ≤ ~40 MHz       | ~33 MHz     | ~37 ms               |
| ~41–99 MHz      | 50 MHz      | ~25 ms               |
| ≥ 100 MHz       | 75 MHz      | ~16 ms — **display garbled** |

The ILI9341 write cycle minimum is 15 ns (66.7 MHz maximum).  At 75 MHz
actual the display receives out-of-spec timing and renders garbage.  **Do not
request ≥ 100 MHz.**

The practical maximum is any value in `41–99 MHz` (all land on the same 50 MHz
actual clock).

---

## Effect of chunk size (`spidev.bufsiz`)

`spidev` limits each `os.write()` to `bufsiz` bytes.  On this device
`bufsiz` is **4096** (`cat /sys/module/spidev/parameters/bufsiz`).  A full
frame (320×240×2 = 153,600 bytes) requires 38 chunks.

Each additional `write()` call costs ~38 µs of fixed overhead (syscall + kernel
copy + CS toggle).  38 chunks adds ~1.5 ms of overhead per frame on top of
wire time.

Measured at 50 MHz actual (81 MHz requested):

| Chunk size | Writes | Total time |
|------------|--------|------------|
| 4,096 B    | 38     | ~26.5 ms   |

Increasing `spidev.bufsiz` (e.g. via `spidev.bufsiz=163840` on the kernel
command line) would reduce this to a single write and drop the total to ~25 ms.
The gain is ~1.5 ms — modest given the 25 ms wire time dominates.

---

## Making the transfer async

The ~26 ms that `write()` blocks Python is the dominant cost for the poll
loop.  Wire time is hardware-fixed and cannot be eliminated, but it can be
hidden by decoupling the LCD push from the main thread.

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
  os.write(spidev_fd, data)              # blocks ~26 ms on worker thread
  lock.release()
```

`LcdIli9341` already has `self.lock`; the only change is moving the `update()`
body onto a thread and making the call-site non-blocking.

**What changes:**

| Metric | Before | After |
|--------|--------|-------|
| Poll loop blocked per frame | ~26 ms | ~0 ms (lock check only) |
| Wall-clock frame latency | ~26 ms | ~26 ms (unchanged — same hardware) |
| Visible tearing risk | None (sequential) | Low — drop-frame policy means LCD always shows a complete frame |
| Kernel / boot changes | None | None |
| Partial update (`box=`) | Works as-is | Works as-is |

This is the lowest-risk path: no changes outside `uilib/lcd_ili9341.py`, no
kernel driver verification, and the existing dirty-rect and partial-update
infrastructure is unaffected.

---

### Framebuffer via `panel-mipi-dbi-spi`

The Linux `panel-mipi-dbi-spi` DRM driver presents the ILI9341 as a standard
framebuffer (`/dev/fb0`).  A `write()` to `/dev/fb0` copies the pixel data into
a kernel-managed framebuffer and returns immediately; the actual SPI transfer
runs in a DRM worker thread.

**Hardware path is identical.**  `panel-mipi-dbi-spi` programs the same BCM
SPI controller.  Wire time (~25 ms) is unchanged.

**What changes:**

| Metric | spidev (`os.write`) | `/dev/fb0` (mipi-dbi) |
|--------|--------------------|-----------------------|
| `write()` blocks caller for | ~26 ms | ~30 µs (kernel copy only) |
| SPI transfer runs on | caller's thread | DRM worker thread |
| Wire time | ~25 ms | ~25 ms (same hardware) |
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

## Primary optimization lever: dirty-rect culling

Both wire time and chunk count scale linearly with pixels pushed.  Culling to
only the changed region of the screen is the most impactful software-side
optimization and requires no kernel or boot changes.

---

## Summary

| What | Value |
|------|-------|
| SPI driver | `spi-bcm2835` |
| SPI controller address | `107d004000` |
| LCD device node | `/dev/spidev0.0` (CE0) |
| ADC device node | `/dev/spidev0.1` (CE1) |
| PCIe in SPI path | **No** |
| Clock source | `vpu-clock` (750 MHz); speed via `clk_set_rate`, CDIV frozen at 4 |
| 81 MHz requested → actual | **50 MHz** |
| ≥ 100 MHz requested → actual | **~75 MHz — exceeds ILI9341 max, display garbled** |
| Safe maximum setting | Any value 56–99 MHz (all give 50 MHz actual) |
| `spidev.bufsiz` on this device | 4096 (38 chunks per frame) |
| Full-frame time @ 50 MHz actual | ~26.5 ms (25 ms wire + 1.5 ms chunk overhead) |
| Primary optimization lever | Dirty-rect culling (linear in pixel count) |
