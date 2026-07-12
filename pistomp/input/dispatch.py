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

"""Panel-local binding resolution and effect firing.

Scoped deliberately narrow (see docs/input-contexts-implementation-plan.md
build order item 4): until ControllerManager becomes a table builder, a panel
is the only context ever in play while it's open, so there is no
cross-context shadowing to resolve here — just "which of this panel's own
declared rows answers this event." `resolve_local` reuses `ContextStack`'s
per-key/enabled_when semantics on a single ad hoc layer rather than
duplicating them.
"""

from typing import Protocol, runtime_checkable

from common.contexts import (
    AliasEffect,
    BindingDecl,
    ContextKind,
    ContextLayer,
    ContextRef,
    ContextStack,
    ControlRef,
    EventKind,
    NoneEffect,
    ParamEffect,
    SelectionEditEffect,
)
from pistomp.input.event import EncoderEvent


@runtime_checkable
class HasSymbol(Protocol):
    symbol: str


class PanelOps(Protocol):
    """The narrow surface `fire` needs from a panel. Deliberately not the
    concrete `Panel` type — `pistomp/input/` must not import `uilib` back
    (uilib already imports pistomp.input.event/sink)."""

    @property
    def sel_ref(self) -> object: ...

    def edit_symbol(self, symbol: str, rotations: int) -> bool:
        """Compute the new value for `symbol` from `rotations`, clamp it,
        commit it, and refresh any panel-specific display. Returns True iff
        the value changed. Panel-owned because the step/taper math genuinely
        differs per plugin (e.g. parametric EQ's exponential frequency step
        vs. a linear default)."""
        ...

    def input_step(self, direction: int, count: int, multiplier: float) -> bool:
        """Fire the base NAV rotation behavior directly (AliasEffect target).
        Only ROTATE aliases are needed by this slice's panels; PRESS/LONGPRESS
        aliasing (e.g. NAM enc1 -> NAV click) is future migration work."""
        ...


def resolve_local(rows: tuple[BindingDecl, ...], control: ControlRef, event_kind: EventKind) -> BindingDecl | None:
    """Resolve one panel's own declared rows for (control, event_kind) — no
    chain, no other contexts. Equivalent to a ContextStack with a single
    PANEL layer."""
    layer = ContextLayer(ref=ContextRef(kind=ContextKind.PANEL))
    for decl in rows:
        layer.rows.setdefault((decl.control.cls, decl.event_kind), []).append(decl)
    stack = ContextStack(layers=[layer])
    return stack.resolve(control, event_kind)


def fire(decl: BindingDecl, ops: PanelOps, event: EncoderEvent) -> bool:
    """Execute a resolved row's effects. Returns True (the row was found and
    is meant to consume the event) whenever consume=True, which is the only
    mode this slice's callers declare."""
    for effect in decl.effects:
        match effect:
            case SelectionEditEffect(fallback_symbol=fallback):
                sel = ops.sel_ref
                symbol = sel.symbol if isinstance(sel, HasSymbol) else fallback
                if symbol is not None:
                    ops.edit_symbol(symbol, event.rotations)
            case ParamEffect(symbol=symbol) if isinstance(symbol, str):
                ops.edit_symbol(symbol, event.rotations)
            case AliasEffect(target_control=_target, target_event_kind=target_kind):
                kind = target_kind or decl.event_kind
                if kind == EventKind.ROTATE:
                    d = event.rotations
                    if d != 0:
                        ops.input_step(1 if d > 0 else -1, abs(d), event.multiplier)
            case NoneEffect():
                pass
    return decl.consume
