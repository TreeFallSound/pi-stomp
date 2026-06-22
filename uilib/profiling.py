# Lightweight env-gated op profiler for the tuner CPU investigation.
#
# Enable with PISTOMP_TUNER_PROFILE=1. Measures cost-per-op (mean µs) and
# wall-CPU fraction per op, binned by |cents| so the cents-dependent flush
# rate is visible. A daemon thread prints a table once/sec and resets.
#
# The %CPU column is the fraction of one core spent in that op during the
# window (sum of measured intervals / window). Counts are hardware-independent;
# multiply mean-µs by the A53↔host single-core ratio to estimate the 3A+.

import os
import threading
import time
from collections import defaultdict

ENABLED = os.environ.get("PISTOMP_TUNER_PROFILE", "") not in ("", "0", "false")

# Current |cents| bin for the main-thread render path. Ops nested inside
# TunerPanel.tick (update/_block) inherit whatever bin tick() set.
_BIN_EDGES = (2.0, 5.0, 15.0, 30.0, 50.0)
_BIN_LABELS = ("<2", "2-5", "5-15", "15-30", "30-50", "50+", "none")

_current_bin = "none"
_lock = threading.Lock()
# (category, bin) -> [count, total_seconds]
_acc: dict = defaultdict(lambda: [0, 0.0])
_started = False


def bin_for_cents(cents):
    if cents is None:
        return "none"
    a = abs(cents)
    for i, edge in enumerate(_BIN_EDGES):
        if a < edge:
            return _BIN_LABELS[i]
    return _BIN_LABELS[len(_BIN_EDGES)]


def set_cents_bin(label):
    global _current_bin
    _current_bin = label


class _Timer:
    __slots__ = ("category", "bin", "t0")

    def __init__(self, category, bin_override=None):
        self.category = category
        self.bin = bin_override if bin_override is not None else _current_bin

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        dt = time.perf_counter() - self.t0
        key = (self.category, self.bin)
        with _lock:
            slot = _acc[key]
            slot[0] += 1
            slot[1] += dt


def measure(category, bin_override=None):
    """Context manager timing a block under (category, current-or-override bin)."""
    return _Timer(category, bin_override)


def _printer():
    while True:
        time.sleep(1.0)
        with _lock:
            snapshot = list(_acc.items())
            _acc.clear()
        if not snapshot:
            continue
        # Order: category, then bin by severity.
        order = {lbl: i for i, lbl in enumerate(_BIN_LABELS)}
        snapshot.sort(key=lambda kv: (kv[0][0], order.get(kv[0][1], 99)))
        lines = [
            "",
            "=== tuner profile (1s window) ===",
            f"{'op':22} {'bin':7} {'calls/s':>8} {'mean_us':>9} {'%core':>7}",
        ]
        for (cat, b), (n, total) in snapshot:
            mean_us = (total / n) * 1e6 if n else 0.0
            pct = total * 100.0
            lines.append(f"{cat:22} {b:7} {n:8d} {mean_us:9.1f} {pct:7.2f}")
        print("\n".join(lines), flush=True)


def maybe_start():
    global _started
    if not ENABLED or _started:
        return
    _started = True
    threading.Thread(target=_printer, daemon=True, name="tuner-profile").start()
