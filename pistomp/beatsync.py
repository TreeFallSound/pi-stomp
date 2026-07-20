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


FLASH_US = 80_000
STALE_AFTER_US = 5_000_000
# A clock sample landing within this many beats of a boundary is treated as
# the crossing itself (arms the flash/bar-start immediately) rather than
# waiting for a later tick to detect it — this is what makes a downbeat
# sample's own arrival distinguishable, fixing the old bug where the seeded
# anchor position was never "crossed" because it was the modulo target itself.
_ANCHOR_CROSSING_EPSILON_BEATS = 0.05


@dataclass(frozen=True)
class TickState:
    is_anchored: bool
    is_flashing: bool
    is_bar_start: bool
    bpm: float
    bpb: float
    beat_phase: float = 0.0  # normalized [0, 1) within the current beat


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
        self._anchor_t_us = msg.t_us
        self._anchor_pos = msg.beat_in_bar
        self._bpm = msg.bpm
        self._bpb = msg.bpb
        self._flash_end_us = None
        self._last_crossing_was_bar_start = False

        current_beat_idx = int(self._anchor_pos // 1)
        frac = self._anchor_pos - current_beat_idx
        if frac < _ANCHOR_CROSSING_EPSILON_BEATS:
            # This sample lands right at (or just past) a beat boundary — the
            # crossing already happened at anchor time. Seed one beat behind
            # so the very first tick() call (even at the anchor's own
            # timestamp) detects the crossing and arms the flash/bar-start,
            # instead of never detecting it because it *is* the modulo target.
            self._last_beat_idx = current_beat_idx - 1
        else:
            self._last_beat_idx = current_beat_idx

    def clear(self) -> None:
        self._anchor_t_us = None
        self._anchor_pos = 0.0
        self._last_beat_idx = 0
        self._flash_end_us = None
        self._last_crossing_was_bar_start = False

    def tick(self, now_us: int) -> TickState:
        if self._anchor_t_us is None:
            return TickState(False, False, False, self._bpm, self._bpb)

        if self._bpm <= 0 or self._bpb <= 0:
            self.clear()
            return TickState(False, False, False, self._bpm, self._bpb)

        if now_us - self._anchor_t_us > STALE_AFTER_US:
            self.clear()
            return TickState(False, False, False, self._bpm, self._bpb)

        bpb_int = int(self._bpb)
        delta_us = now_us - self._anchor_t_us
        pos = self._anchor_pos + delta_us * self._bpm / 60_000_000.0
        current_beat_idx = int(pos // 1)
        beat_phase = pos - current_beat_idx  # fractional part [0, 1)

        if current_beat_idx > self._last_beat_idx:
            self._last_beat_idx = current_beat_idx
            self._flash_end_us = now_us + FLASH_US
            self._last_crossing_was_bar_start = (current_beat_idx % bpb_int) == 0

        is_flashing = (
            self._flash_end_us is not None and now_us < self._flash_end_us
        )
        return TickState(
            is_anchored=True,
            is_flashing=is_flashing,
            is_bar_start=is_flashing and self._last_crossing_was_bar_start,
            bpm=self._bpm,
            bpb=self._bpb,
            beat_phase=beat_phase,
        )
