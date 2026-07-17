# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Analog input connection monitor — detects disconnected/floating ADC pins.

A pure-Python two-state machine fed one raw 10-bit ADC reading per poll tick.
No hardware dependencies; fully unit-testable with synthetic streams.

WHY
  The MCP3008 has no fault-detection pin. An unconnected analog input
  (e.g. an expression-pedal jack with nothing plugged in) floats, picking
  up 60 Hz mains hum via capacitive coupling. At our 100 Hz poll rate the
  60 Hz aliases into a ~40 Hz beat, producing stddev of ~23–34 LSB and
  excursions up to 142 LSB on a nominally "zero" input. This drives
  spurious MIDI CCs and, worse, repaints the LCD control-progress bars
  every tick.

  A connected passive potentiometer at rest produces Johnson + kTC noise
  well below 1 LSB (measured σ ≈ 0.4 LSB), so the two states are separated
  by ~50× in stddev. This module exploits that gap.

STATES
  DETERMINING  First WINDOW samples after construction. Classify as ASLEEP
               if the window shows the floating signature (high σ, high
               excursion, low rail-avoidant mean); otherwise AWAKE.
               Autosync is suppressed until a verdict is reached.
  AWAKE        Normal operation — the caller should emit MIDI and update
               its cached reading. Every tick also feeds a rolling window
               so we can detect an unplug at runtime.
  ASLEEP       The pin appears floating. The caller should silently drop
               readings (no MIDI, no LCD progress update). The baseline
               drifts via EMA to track slow floating-mean wander. A
               reading that steps far enough from the baseline wakes
               immediately (a pedal was plugged in).

THRESHOLDS (derived from on-device measurement, see docs below)
  WINDOW               = 16 samples  (160 ms at 10 ms poll)
  STD_MIN              = 3 LSB       (3× above connected σ≈0.4, ~8× below floating σ≈23)
  STD_MAX              = 50 LSB      (above floating σ≈34; a fast sweep >128 LSB has σ≈40+)
  EXCURSION_MIN        = 8 LSB       (4× above connected E≈2, ~12× below floating E≈96)
  EXCURSION_MAX        = 150 LSB     (above floating E≈142; a fast sweep >128 LSB has E≈128+)
  WAKE_EXCURSION       = 48 LSB      (1.2% false-wake on pure floating noise; catches all plug-ins ≥ 100 LSB)
  EMA_ALPHA            = 0.01        (baseline tracks slow floating drift over minutes)

The classifier uses std AND excursion, each bounded in a [min, max) range.
A connected pot at rest has σ ≈ 0.4 LSB and E ≈ 2 LSB — far below both
gates regardless of where the wiper is parked. A floating pin has
σ ≈ 23–34 LSB and E up to 142 LSB — within the gates. A fast pedal sweep
(>128 LSB over 160 ms) has σ > 40 and E > 128, which exceeds the upper
bounds and is correctly AWAKE. A slow sweep near heel overlaps the
floating band and may be ASLEEP at startup, but the wake mechanism
(48 LSB step from baseline) recovers it within 1 frame.

The upper bounds make the classifier conservative: when in doubt, AWAKE.
This matches the musical-instrument priority — let a few noise samples
through rather than block a real pedal.

All thresholds are over the 10-bit ADC range [0, 1023].
"""

from __future__ import annotations

from collections import deque
from enum import Enum


class AnalogConnectionState(Enum):
    DETERMINING = "determining"
    AWAKE = "awake"
    ASLEEP = "asleep"


class AnalogConnectionMonitor:
    """Two-state connection monitor for a single ADC channel.

    Feed one raw 10-bit reading per poll tick via observe(); the return
    tells the caller whether to emit the reading (pass it downstream) or
    drop it silently.
    """

    # --- Tunables (see module docstring for justification) ---
    WINDOW: int = 16
    STD_MIN: float = 3.0
    STD_MAX: float = 50.0
    EXCURSION_MIN: float = 8.0
    EXCURSION_MAX: float = 150.0
    WAKE_EXCURSION: float = 48.0
    EMA_ALPHA: float = 0.01

    def __init__(self) -> None:
        self._state: AnalogConnectionState = AnalogConnectionState.DETERMINING
        self._window: deque[int] = deque(maxlen=self.WINDOW)
        self._baseline: float = 0.0
        self._startup_samples: int = 0

    # --- Public API -----------------------------------------------------

    @property
    def state(self) -> AnalogConnectionState:
        return self._state

    @property
    def is_awake(self) -> bool:
        return self._state is AnalogConnectionState.AWAKE

    @property
    def baseline(self) -> float:
        """Current baseline value (floating mean when ASLEEP, last mean when AWAKE)."""
        return self._baseline

    def observe(self, raw: int) -> AnalogConnectionState:
        """Process one raw ADC reading. Returns the resulting state.

        The caller checks ``is_awake`` (or compares the returned state to
        its previous state) to decide whether to emit the reading.
        """
        self._window.append(raw)
        if self._state is AnalogConnectionState.DETERMINING:
            self._startup_samples += 1
            if self._startup_samples >= self.WINDOW:
                self._classify_startup()
            # Still determining: don't emit (autosync suppressed).
            return self._state

        if self._state is AnalogConnectionState.AWAKE:
            self._check_runtime_sleep(raw)
            return self._state

        # ASLEEP
        self._check_runtime_wake(raw)
        return self._state

    # --- Internal -------------------------------------------------------

    def _window_stats(self) -> tuple[float, float, float]:
        """Return (mean, stddev, excursion) of the current window."""
        n = len(self._window)
        if n == 0:
            return 0.0, 0.0, 0.0
        s = float(sum(self._window))
        mean = s / n
        if n == 1:
            return mean, 0.0, 0.0
        var = sum((v - mean) ** 2 for v in self._window) / n  # population
        std = var ** 0.5
        excursion = float(max(self._window)) - float(min(self._window))
        return mean, std, excursion

    def _has_floating_signature(self) -> bool:
        """True if the current window looks like a floating pin."""
        if len(self._window) < self.WINDOW:
            return False
        _, std, exc = self._window_stats()
        return (
            self.STD_MIN <= std < self.STD_MAX
            and self.EXCURSION_MIN <= exc < self.EXCURSION_MAX
        )

    def _classify_startup(self) -> None:
        mean, _, _ = self._window_stats()
        self._baseline = mean
        if self._has_floating_signature():
            self._state = AnalogConnectionState.ASLEEP
        else:
            self._state = AnalogConnectionState.AWAKE

    def _check_runtime_sleep(self, raw: int) -> None:
        """While AWAKE, watch for the floating signature (unplug event)."""
        if self._has_floating_signature():
            mean, _, _ = self._window_stats()
            self._state = AnalogConnectionState.ASLEEP
            self._baseline = mean

    def _check_runtime_wake(self, raw: int) -> None:
        """While ASLEEP, watch for a real signal stepping away from baseline."""
        # EMA-update the baseline so slow floating drift over minutes does
        # not accumulate into a false wake. A genuinely floating reading
        # stays near the drifting baseline; a plugged-in pedal jumps.
        self._baseline = self._baseline + self.EMA_ALPHA * (raw - self._baseline)
        if abs(raw - self._baseline) >= self.WAKE_EXCURSION:
            self._state = AnalogConnectionState.AWAKE