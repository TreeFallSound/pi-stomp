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

"""Instance-scoped footswitch longpress/chord resolver.

Replaces the old class-level state on Footswitch. The handler owns one
instance, rebuilt on each pedalboard change. A "group" is a named longpress
action shared by one or more footswitches; two members pressed within WINDOW
seconds resolve as a chord, a lone member fires after the window expires.
"""

from __future__ import annotations

import logging
import time
from typing import Callable


class LongpressGroup:
    def __init__(self):
        self.number_in_group = 0
        self.timestamps: dict[int, float] = {}


class FootswitchChords:
    # Window within which two member longpresses count as a chord, and the
    # timeout after which a lone member fires on its own.
    WINDOW = 0.4

    def __init__(self):
        self.groups: dict[str, LongpressGroup] = {}
        self.callbacks: dict[str, Callable] = {}

    def rebuild(self, callbacks: dict[str, Callable]) -> None:
        """Reset for a new pedalboard. Only names with a callback participate."""
        self.callbacks = callbacks
        self.groups = {}

    def register(self, longpress_groups: list) -> None:
        """Count a footswitch's membership in each of its longpress groups."""
        for name in longpress_groups:
            if name not in self.callbacks:
                continue
            self.groups.setdefault(name, LongpressGroup()).number_in_group += 1

    def observe(self, fs, timestamp: float) -> None:
        """Record a longpress timestamp for each group this footswitch joins."""
        for name in fs.longpress_groups:
            group = self.groups.get(name)
            if group is not None:
                logging.debug("longpress event logged: %s", name)
                group.timestamps[fs.id] = timestamp

    def tick(self) -> list:
        """Resolve pending longpresses. Call once per poll cycle. Returns the
        callback names that fired this cycle."""
        now = time.monotonic()
        fired = []
        for name, group in self.groups.items():
            num_ts = len(group.timestamps)
            if num_ts > 1:
                # Chord: two members within WINDOW. Only one chord fires per cycle.
                last = group.timestamps.popitem()[1]
                first = group.timestamps.popitem()[1]
                if abs(last - first) < self.WINDOW:
                    fired.append(name)
                self._clear_all()
                return fired
            elif num_ts == 1 and group.number_in_group == 1:
                # Singleton: lone member, fire once the chord window has expired.
                ts = next(iter(group.timestamps.values()))
                if now >= ts + self.WINDOW:
                    fired.append(name)
                    group.timestamps.clear()
        return fired

    def _clear_all(self) -> None:
        for group in self.groups.values():
            group.timestamps.clear()
