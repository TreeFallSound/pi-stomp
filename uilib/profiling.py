# Lightweight env-gated op profiler.
#
# Enable with PISTOMP_PROFILE=1 (or the legacy PISTOMP_TUNER_PROFILE=1).
# Measures cost-per-op (mean µs) and wall-CPU fraction per op, binned by a
# caller-supplied context tag. A daemon thread prints a table once/sec and
# resets.
#
# The %CPU column is the fraction of one core spent in that op during the
# window (sum of measured intervals / window). Counts are hardware-independent;
# multiply mean-µs by the A53↔host single-core ratio to estimate the 3A+.

import os
import threading
import time
from collections import defaultdict

_RAW = os.environ.get
ENABLED = _RAW("PISTOMP_PROFILE", "") not in ("", "0", "false") or \
          _RAW("PISTOMP_TUNER_PROFILE", "") not in ("", "0", "false")

# Tuner-specific cent bins — kept for TunerPanel backward compatibility.
_BIN_EDGES = (2.0, 5.0, 15.0, 30.0, 50.0)
_BIN_LABELS = ("<2", "2-5", "5-15", "15-30", "30-50", "50+", "none")

# Current context tag for the main-thread render path. Ops nested inside a
# panel's tick() inherit whatever tag tick() set.
_current_tag = "none"
_lock = threading.Lock()
# (category, tag) -> [count, total_seconds]
_acc: dict = defaultdict(lambda: [0, 0.0])
_started = False


# ── Tuner helpers (cent-specific) ─────────────────────────────────────────────


def bin_for_cents(cents):
    if cents is None:
        return "none"
    a = abs(cents)
    for i, edge in enumerate(_BIN_EDGES):
        if a < edge:
            return _BIN_LABELS[i]
    return _BIN_LABELS[len(_BIN_EDGES)]


# ── Generic context tag ───────────────────────────────────────────────────────


def set_context_tag(label: str) -> None:
    """Set the context tag inherited by all measure() calls on this thread."""
    global _current_tag
    _current_tag = label


def set_cents_bin(label: str) -> None:
    """Backward-compatible alias for set_context_tag (used by TunerPanel)."""
    set_context_tag(label)


# ── Timer ─────────────────────────────────────────────────────────────────────


class _Timer:
    __slots__ = ("category", "tag", "t0")

    def __init__(self, category: str, tag_override=None):
        self.category = category
        self.tag = tag_override if tag_override is not None else _current_tag

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        dt = time.perf_counter() - self.t0
        key = (self.category, self.tag)
        with _lock:
            slot = _acc[key]
            slot[0] += 1
            slot[1] += dt


def measure(category: str, bin_override=None):
    """Context manager timing a block under (category, current-or-override tag)."""
    return _Timer(category, bin_override)


# ── Reporter ──────────────────────────────────────────────────────────────────


def _printer():
    while True:
        time.sleep(1.0)
        with _lock:
            snapshot = list(_acc.items())
            _acc.clear()
        if not snapshot:
            continue
        snapshot.sort(key=lambda kv: (kv[0][0], kv[0][1]))
        lines = [
            "",
            "=== pistomp profile (1s window) ===",
            f"{'op':30} {'tag':12} {'calls/s':>8} {'mean_us':>9} {'%core':>7}",
        ]
        for (cat, tag), (n, total) in snapshot:
            mean_us = (total / n) * 1e6 if n else 0.0
            pct = total * 100.0
            lines.append(f"{cat:30} {tag:12} {n:8d} {mean_us:9.1f} {pct:7.2f}")
        print("\n".join(lines), flush=True)


def maybe_start():
    """Start the background reporter if profiling is enabled. Idempotent."""
    global _started
    if not ENABLED or _started:
        return
    _started = True
    threading.Thread(target=_printer, daemon=True, name="pistomp-profile").start()
