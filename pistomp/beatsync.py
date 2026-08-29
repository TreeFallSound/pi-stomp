# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from dataclasses import dataclass

from modalapi.ws_protocol import BeatSyncMessage


FLASH_US = 50_000
STALE_AFTER_US = 5_000_000


@dataclass(frozen=True)
class TickState:
    is_anchored: bool
    is_flashing: bool
    is_bar_start: bool
    bpm: float
    bpb: float
    beat_phase: float = 0.0  # normalized [0, 1) within the current beat
    bar_phase: float = 0.0  # normalized [0, 1) within the current bar
    is_free: bool = False  # the beat comes from the tap, not from the transport

    @property
    def is_running(self) -> bool:
        """True when there is a beat to flash on. Only an anchored grid gives a
        bar. A free grid has no `bar_phase` and no bar start."""
        return self.is_anchored or self.is_free


class BeatGrid:
    """Tracks the transport clock from a stream of `BeatSyncMessage` clock
    samples: pos(t) = beat_in_bar + (t - t_us) * bpm / 60, anchored fresh from
    each sample's own beat_in_bar (no cumulative bar count needed — mod-host
    doesn't expose one). Downbeat is *computed* from this position
    (`beat_index % bpb == 0`), not reconstructed from message-arrival timing —
    so it's correct regardless of emission cadence, and self-healing: the
    latest sample fully replaces any prior anchor, so a dropped/late one just
    means more extrapolation, never a wrong lock."""

    def __init__(self) -> None:
        self._anchor_t_us: int | None = None
        self._anchor_pos: float = 0.0
        self._bpm: float = 120.0
        self._bpb: float = 4.0
        self._last_beat_idx: int = 0
        self._flash_end_us: int | None = None
        self._last_crossing_was_bar_start: bool = False

    @property
    def is_anchored(self) -> bool:
        return self._anchor_t_us is not None

    def on_anchor(self, msg: BeatSyncMessage) -> None:
        if msg.bpm <= 0 or msg.bpb <= 0:
            self.clear()
            return
        if not msg.is_new_bar:
            self._retune(msg)
            return

        self._anchor_t_us = msg.t_us
        self._anchor_pos = msg.beat_in_bar
        self._bpm = msg.bpm
        self._bpb = msg.bpb
        self._flash_end_us = None
        self._last_crossing_was_bar_start = False
        # The sample occurs on the bar line, thus its own beat is the
        # crossing. Seed one beat behind, or the first tick() does not find
        # the crossing: the beat index is already equal to the modulo target.
        self._last_beat_idx = int(self._anchor_pos // 1) - 1

    def _retune(self, msg: BeatSyncMessage) -> None:
        """Take the tempo from a sample that has an incorrect phase (a tempo
        change or a meter change). The next bar heartbeat corrects the phase."""
        self.set_tempo(msg.bpm, msg.t_us)
        self._bpb = msg.bpb

    def set_tempo(self, bpm: float, now_us: int) -> None:
        """Change the rate without a clock sample. mod-ui's `transport` path
        (a tweak knob, a tap, a browser) writes the mod-host globals but emits
        no beat_sync, thus this is the only way the grid learns that rate."""
        if bpm <= 0:
            return
        if self._anchor_t_us is not None:
            elapsed_us = now_us - self._anchor_t_us
            self._anchor_pos += elapsed_us * self._bpm / 60_000_000.0
            self._anchor_t_us = now_us
        self._bpm = bpm

    def clear(self) -> None:
        self._anchor_t_us = None
        self._anchor_pos = 0.0
        self._last_beat_idx = 0
        self._flash_end_us = None
        self._last_crossing_was_bar_start = False

    def tick(self, now_us: int, free_bpm: float = 0.0, free_anchor_us: int = 0) -> TickState:
        if self._anchor_t_us is None:
            return self._free_tick(now_us, free_bpm, free_anchor_us)

        if self._bpm <= 0 or self._bpb <= 0:
            self.clear()
            return self._free_tick(now_us, free_bpm, free_anchor_us)

        if now_us - self._anchor_t_us > STALE_AFTER_US:
            self.clear()
            return self._free_tick(now_us, free_bpm, free_anchor_us)

        bpb_int = int(self._bpb)
        delta_us = now_us - self._anchor_t_us
        pos = self._anchor_pos + delta_us * self._bpm / 60_000_000.0
        current_beat_idx = int(pos // 1)
        beat_phase = pos - current_beat_idx  # fractional part [0, 1)
        bar_phase = (pos % self._bpb) / self._bpb

        if current_beat_idx > self._last_beat_idx:
            self._last_beat_idx = current_beat_idx
            beat_boundary_us = self._anchor_t_us + int((current_beat_idx - self._anchor_pos) * 60_000_000.0 / self._bpm)
            self._flash_end_us = beat_boundary_us + FLASH_US
            self._last_crossing_was_bar_start = (current_beat_idx % bpb_int) == 0

        is_flashing = self._flash_end_us is not None and now_us < self._flash_end_us
        return TickState(
            is_anchored=True,
            is_flashing=is_flashing,
            is_bar_start=is_flashing and self._last_crossing_was_bar_start,
            bpm=self._bpm,
            bpb=self._bpb,
            beat_phase=beat_phase,
            bar_phase=bar_phase,
        )

    def _free_tick(self, now_us: int, bpm: float, anchor_us: int) -> TickState:
        """Beats without a transport: the tap phase at the tap tempo. No bar,
        thus this grid has beats only and no renderer can show an accent."""
        if bpm <= 0:
            return TickState(False, False, False, self._bpm, self._bpb)
        period_us = 60_000_000.0 / bpm
        phase_us = (now_us - anchor_us) % period_us
        return TickState(
            is_anchored=False,
            is_flashing=phase_us < FLASH_US,
            is_bar_start=False,
            bpm=bpm,
            bpb=self._bpb,
            beat_phase=phase_us / period_us,
            is_free=True,
        )
