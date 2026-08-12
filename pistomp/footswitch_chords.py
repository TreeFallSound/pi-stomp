# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Instance-scoped footswitch longpress/chord resolver.

The handler owns one instance, rebuilt on each pedalboard change. A "group" is
a named longpress action shared by one or more footswitches: a lone member is a
solo action, several members are a chord.

Resolution is synchronous — a longpress fires the moment the switch matures,
never after a wait. It can be, because the chord question is answered by
physical hold state rather than by the partners' own longpresses: when the
first member of a chord reaches its hold threshold, every other member is
already held, so the chord is decided right there and the partners' later
longpresses are redundant. `PRESSED` (held, hasn't matured yet) is what marks a
genuine simultaneous stomp; a member sitting in `LONGPRESSED` is a foot parked
on a switch that already spent its own longpress, and forms no chord.
"""

from __future__ import annotations

import logging
from typing import Callable, Protocol

import pistomp.switchstate as switchstate


class LongpressMember(Protocol):
    """Structural view of a Footswitch. Keeps this module off the Footswitch
    import, the way pistomp.input.dispatch keeps PanelOps off uilib.Panel."""

    id: int | None
    longpress_groups: list[str]

    @property
    def press_state(self) -> switchstate.Value: ...


class LongpressGroup:
    def __init__(self, name: str):
        self.name = name
        self.members: list[LongpressMember] = []
        # Set when this group fires; silences the members that have yet to
        # mature, cleared once the whole group is released.
        self.spent = False

    @property
    def is_chord(self) -> bool:
        return len(self.members) > 1

    @property
    def any_held(self) -> bool:
        return any(m.press_state is not switchstate.Value.RELEASED for m in self.members)

    def satisfied_by(self, fs: LongpressMember) -> bool:
        """True when every member other than the one maturing is held and has
        not spent its own longpress. All members, not any — a partly-stomped
        group fires nothing."""
        return all(m.press_state is switchstate.Value.PRESSED for m in self.members if m is not fs)


class FootswitchChords:
    def __init__(self):
        self.groups: dict[str, LongpressGroup] = {}
        self.callbacks: dict[str, Callable] = {}

    def rebuild(self, callbacks: dict[str, Callable]) -> None:
        """Reset for a new pedalboard. Only names with a callback participate."""
        self.callbacks = callbacks
        self.groups = {}

    def register(self, fs: LongpressMember) -> None:
        """Record a footswitch's membership in each of its longpress groups."""
        for name in fs.longpress_groups:
            if name not in self.callbacks:
                logging.warning(
                    "footswitch %s: longpress group '%s' names no known action; ignored",
                    fs.id,
                    name,
                )
                continue
            self.groups.setdefault(name, LongpressGroup(name)).members.append(fs)

    def poll(self):
        """Release reconciliation. Call once per poll cycle. No timing — a
        spent group re-arms only once every one of its members is up, which is
        what stops a chord from firing twice off one gesture."""
        for group in self.groups.values():
            if group.spent and not group.any_held:
                group.spent = False

    def observe(self, fs: LongpressMember) -> list[str]:
        """Resolve a matured longpress. Returns the callback names to fire: the
        chord when one of this switch's groups is fully held, otherwise its solo
        groups, or nothing when it's a remaining member of a chord that already
        fired."""
        mine = [g for g in self.groups.values() if any(m is fs for m in g.members)]

        satisfied = [g for g in mine if g.is_chord and not g.spent and g.satisfied_by(fs)]
        if satisfied:
            # Most specific wins: a 3-chord outranks a pair drawn from it.
            winner = max(satisfied, key=lambda g: len(g.members))
            winner.spent = True
            return [winner.name]

        if any(g.spent for g in mine):
            return []

        return [g.name for g in mine if not g.is_chord]
