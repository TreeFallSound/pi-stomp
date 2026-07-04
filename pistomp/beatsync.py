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


@dataclass(frozen=True)
class TickState:
    is_anchored: bool
    is_flashing: bool
    is_bar_start: bool
    bpm: float
    bpb: float


class BeatGrid:
    def __init__(self) -> None:
        self._anchor_t_us: int | None = None
        self._anchor_beat_idx: int = 0
        self._bpm: float = 120.0
        self._bpb: float = 4.0
        self._last_beat_idx: int = 0
        self._flash_end_us: int | None = None
        self._last_crossing_was_bar_start: bool = False

    @property
    def is_anchored(self) -> bool:
        return self._anchor_t_us is not None

    def on_anchor(self, msg: BeatSyncMessage) -> None:
        bpb = msg.bpb if msg.bpb > 0 else 0
        self._anchor_t_us = msg.t_us
        self._anchor_beat_idx = msg.bar * int(bpb) if bpb else 0
        self._bpm = msg.bpm
        self._bpb = msg.bpb
        self._last_beat_idx = self._anchor_beat_idx
        self._flash_end_us = None
        self._last_crossing_was_bar_start = False

    def clear(self) -> None:
        self._anchor_t_us = None
        self._anchor_beat_idx = 0
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
        delta_beats = delta_us * self._bpm / 60_000_000.0
        current_beat_idx = self._anchor_beat_idx + int(delta_beats)

        if current_beat_idx > self._last_beat_idx:
            self._last_beat_idx = current_beat_idx
            self._flash_end_us = now_us + FLASH_US
            self._last_crossing_was_bar_start = (
                bpb_int > 0 and (current_beat_idx % bpb_int) == 0
            )

        is_flashing = (
            self._flash_end_us is not None and now_us < self._flash_end_us
        )
        return TickState(
            is_anchored=True,
            is_flashing=is_flashing,
            is_bar_start=is_flashing and self._last_crossing_was_bar_start,
            bpm=self._bpm,
            bpb=self._bpb,
        )
