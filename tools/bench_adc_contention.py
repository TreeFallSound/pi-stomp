#!/usr/bin/env python3
"""Does an in-flight LCD push stall the ADC on the shared SPI bus?

The LCD (CE0, Blinka) and the MCP3008 (CE1, raw spidev @1MHz) sit on the same
SPI master. Today they never overlap: poll_lcd_updates() and poll_controls()
both run on the UI thread, so the kernel sees one transfer at a time.

Moving the LCD push to a worker thread (docs/spi_lcd_timing_pi5.md) would remove
a 19-25ms UI-thread stall -- but only if it doesn't simply relocate that stall
into poll_controls(). With spidev.bufsiz=163840 a full frame is ONE kernel SPI
message, and the spi core serializes messages per master: an ADC read issued
mid-frame may wait for the whole payload to clock out.

This measures ADC xfer2 latency with the LCD idle vs. with a worker thread
pushing frames continuously, and sweeps the LCD payload chunk size -- chunking
releases the bus between writes, letting the ADC interleave, at the cost of more
syscalls.

Verdict this is looking for: p95/max ADC latency under contention. The UI tick is
10ms; an ADC read that blocks for ~19ms is a worse bug than the one we set out to
fix.

    sudo systemctl stop mod-ala-pi-stomp
    PYTHONPATH=/opt/pistomp/pi-stomp python tools/bench_adc_contention.py [baud]
"""

from __future__ import annotations

import os
import statistics
import sys
import threading
import time
from pathlib import Path

# tools/ lands on sys.path[0], not the repo root -- without this, `import uilib`
# finds the copy in the venv's site-packages and benches the packaged driver.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))

import board  # noqa: E402
import digitalio  # noqa: E402
import spidev  # noqa: E402

from uilib.box import Box  # noqa: E402
from uilib.lcd_ili9341 import LcdIli9341  # noqa: E402

BAUD = int(sys.argv[1]) if len(sys.argv) > 1 else 66_666_667
ADC_CHANNEL = 0


def adc_open() -> spidev.SpiDev:
    """Exactly what hardware.init_spi() does."""
    spi = spidev.SpiDev()
    spi.open(0, 1)  # bus 0, CE1
    spi.max_speed_hz = 1_000_000
    return spi


def adc_read(spi: spidev.SpiDev) -> int:
    """One MCP3008 single-ended read -- analogcontrol.readChannel()."""
    adc = spi.xfer2([1, (8 + ADC_CHANNEL) << 4, 0])
    return ((adc[1] & 3) << 8) + adc[2]


def sample_adc(spi: spidev.SpiDev, duration_s: float) -> list[float]:
    """Poll the ADC at the real 10ms tick cadence for `duration_s`."""
    out: list[float] = []
    deadline = time.perf_counter() + duration_s
    while time.perf_counter() < deadline:
        t0 = time.perf_counter_ns()
        adc_read(spi)
        out.append((time.perf_counter_ns() - t0) / 1e6)
        time.sleep(0.010)
    return out


def report(label: str, samples: list[float]) -> None:
    s = sorted(samples)
    p = lambda q: s[min(len(s) - 1, int(q * len(s)))]  # noqa: E731
    over = sum(1 for v in s if v > 10.0)
    print(
        f"  {label:<34} n={len(s):4d}  med={statistics.median(s):6.3f}  "
        f"p95={p(0.95):7.3f}  p99={p(0.99):7.3f}  max={max(s):7.3f} ms"
        f"   >10ms: {over} ({100*over/len(s):.1f}%)"
    )


def main() -> int:
    lcd = LcdIli9341(
        board.SPI(),
        digitalio.DigitalInOut(board.CE0),
        digitalio.DigitalInOut(board.D6),
        digitalio.DigitalInOut(board.D5),
        BAUD,
        True,
    )
    surf = pygame.Surface((320, 240), depth=32, masks=(0xFF0000, 0xFF00, 0xFF, 0))
    for y in range(240):
        pygame.draw.line(surf, (y, 255 - y, (y * 3) % 256), (0, y), (319, y))
    full = Box(0, 0, 320, 240)

    adc = adc_open()

    print(f"LCD @ {lcd.baudrate/1e6:.2f} MHz actual | ADC @ 1 MHz, CE1 | tick = 10 ms\n")

    print("ADC latency, LCD idle (baseline):")
    report("idle", sample_adc(adc, 2.0))

    # --- LCD pushing continuously on a worker thread ---
    stop = threading.Event()
    frames = [0]

    def pusher():
        while not stop.is_set():
            lcd.update(surf, full)
            frames[0] += 1

    print("\nADC latency, worker thread pushing full frames continuously:")
    t = threading.Thread(target=pusher, daemon=True)
    t.start()
    time.sleep(0.2)  # let it get going
    contended = sample_adc(adc, 4.0)
    stop.set()
    t.join(timeout=5)
    report("contended (one 153.6kB write)", contended)
    print(f"    (worker pushed {frames[0]} frames)")

    # --- same, but chunk the payload so the bus is released between writes ---
    orig_block = lcd.disp._block

    for chunk_kb in (64, 16, 4):
        chunk = chunk_kb * 1024

        def chunked(x0, y0, x1, y1, data=None, _c=chunk):
            if data is None:
                return orig_block(x0, y0, x1, y1, data)
            for i in range(0, len(data), _c):
                # Only the first call sets the address window; the panel
                # auto-increments GRAM across subsequent payload writes.
                if i == 0:
                    orig_block(x0, y0, x1, y1, data[i : i + _c])
                else:
                    _raw_payload(lcd, data[i : i + _c])
            return None

        lcd.disp._block = chunked
        stop = threading.Event()
        frames = [0]

        def pusher2():
            while not stop.is_set():
                lcd.update(surf, full)
                frames[0] += 1

        t = threading.Thread(target=pusher2, daemon=True)
        t.start()
        time.sleep(0.2)
        s = sample_adc(adc, 3.0)
        stop.set()
        t.join(timeout=5)
        report(f"contended ({chunk_kb}kB chunks)", s)
        print(f"    (worker pushed {frames[0]} frames)")

    lcd.disp._block = orig_block
    adc.close()
    return 0


def _raw_payload(lcd: LcdIli9341, data: bytes) -> None:
    """Continuation payload write: no address window, DC high, CS asserted."""
    disp = lcd.disp
    spi_dev = disp.spi_device
    spi = spi_dev.spi
    cs = spi_dev.chip_select
    dc = disp.dc_pin
    fd = spi._spi._spi.handle

    while not spi.try_lock():
        time.sleep(0)
    try:
        spi.configure(
            baudrate=spi_dev.baudrate, polarity=spi_dev.polarity, phase=spi_dev.phase
        )
        if cs:
            cs.value = spi_dev.cs_active_value
        dc.value = 1
        os.write(fd, data)
    finally:
        if cs:
            cs.value = not spi_dev.cs_active_value
        spi.unlock()


if __name__ == "__main__":
    sys.exit(main())
