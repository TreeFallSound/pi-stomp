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

"""What `PluginPanel` needs of the thing it edits.

`Plugin` and the Audio & MIDI synthetic bundle both satisfy it structurally.
Bypass is not part of it: a source without one gets a footer with no
Bypass/Reset, and `PluginPanel` gates that wiring on `isinstance(source,
Plugin)`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from common.parameter import Parameter, Symbol


@runtime_checkable
class ParamSource(Protocol):
    """Subscribable parameters plus a write path. Satisfied structurally."""

    instance_id: str
    parameters: "dict[Symbol, Parameter]"

    def set_param_value(self, symbol: "Symbol", value: float) -> None: ...

    def subscribe(self, cb: "Callable[[Parameter], None]") -> "Callable[[], None]": ...


ParamSink = Callable[["Parameter"], bool]
"""Carries a committed value upstream (mod-ui, MIDI out, the audio card).
False means it did not send, and `commit` reverts the value."""
