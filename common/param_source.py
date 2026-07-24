# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-Stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Reactive param-source protocol — the seam a `PluginPanel` core depends on.

`PluginPanel[TState]` was originally hardwired to `modalapi.plugin.Plugin`.
The Audio & MIDI menu (see `docs/audio-midi-menu.md`) edits synthetic
parameters — audiocard levels + the 5 global-EQ bands — with no backing
`Plugin`. Rather than hand-rolling a parallel edit/commit pipeline, the
behaviour core was lifted off `Plugin` onto this protocol: anything that
exposes subscribable `Parameter`s and a `set_param_value` write path reuses
`PluginPanel`'s coalescing queue, the subscribe→dirty→`apply_state`
reconcile, and `edit_symbol`'s `ParameterSteps` math.

`Plugin` satisfies `ParamSource` structurally with no edits; the audio
menu's source is a synthetic bundle (see `plugins.audio_midi.source`).
Bypass/reset are *not* on the protocol — a source without a bypass
(audiocard, global EQ) composes the reactive core with a footer that
omits the Bypass/Reset buttons (§4.2 of the doc). The bypass wiring on
`PluginPanel` guards on `hasattr`-free `isinstance` against the optional
`BypassSource` extension so a bypass-free core is a valid configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from common.parameter import Parameter, Symbol


@runtime_checkable
class ParamSource(Protocol):
    """A reactive bag of parameters a `PluginPanel` core can edit.

    Structural — `modalapi.plugin.Plugin` and the Audio & MIDI synthetic
    bundle both satisfy this without inheriting it.
    """

    # Protocol attributes: a plain instance attribute satisfies these, so
    # `Plugin.instance_id` / `Plugin.parameters` match without changes.
    instance_id: str
    parameters: "dict[Symbol, Parameter]"

    def set_param_value(self, symbol: "Symbol", value: float) -> None: ...

    def subscribe(self, cb: "Callable[[Parameter], None]") -> "Callable[[], None]": ...


@runtime_checkable
class BypassSource(Protocol):
    """Optional bypass surface a `ParamSource` may also expose.

    `Plugin` implements this; the Audio & MIDI synthetic bundle does not.
    `PluginPanel`'s bypass/reset path guards on `isinstance(source,
    BypassSource)` so a bypass-free source simply has no bypass button.
    """

    def is_bypassed(self) -> bool: ...

    def set_bypass(self, bypass: bool) -> None: ...

    pedalboard_snapshot: "dict[Symbol, float]"


@runtime_checkable
class ParamSink(Protocol):
    """The outbound dual of `ParamSource` — where a *local edit* goes next.

    A parameter's value moves for one of two reasons, and they are not the same
    event. A **local edit** (a knob turn, a dialog commit) is a command: set the
    value and tell whoever owns it upstream. A **remote reconcile** (mod-ui
    echoing its own state back at us) is the opposite: adopt the value, tell
    nobody — mod-ui is already the single writer.

    `Parameter.value`'s setter carries the reconcile semantics (notify observers
    to repaint, publish nothing); `Parameter.edit()` carries the command (set,
    then publish through this sink). A reconcile has no send to suppress — the
    distinction is which method the caller reaches for, not a flag guarding a
    shared one. A parameter with no sink is display-only: reconciled, never sent.
    """

    def publish(self, param: "Parameter") -> None: ...