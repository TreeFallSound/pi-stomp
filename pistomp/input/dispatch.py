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

"""Panel-local binding resolution and effect firing — see "Where a panel
plugs in" in pistomp/input/README.md.

Scoped to one panel's own rows, no cross-context chain — a panel only ever
competes with itself. Cross-context resolution (pedalboard rows, blend) goes
through the same ContextStack.resolve directly (see ControllerManager.bind,
Modhandler._fire_blend_row)."""

from typing import Protocol, runtime_checkable

from common.contexts import (
    AudioCardEffect,
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
from common.param_roles import ParamRole
from common.parameter import Symbol
from pistomp.input.event import EncoderEvent


@runtime_checkable
class Selectable(Protocol):
    def symbol_for(self, role: ParamRole) -> Symbol | None: ...


@runtime_checkable
class MultiSelectable(Protocol):
    """A selection representing more than one live symbol at once (e.g. an EQ
    band's gain/freq/Q) — CLICK opens a submenu over these instead of a single
    dialog."""

    def menu_rows(self) -> tuple[tuple[str, Symbol], ...]: ...

    def menu_title(self) -> str: ...


class PanelOps(Protocol):
    """Not the concrete Panel type — pistomp/input must not import uilib back."""

    @property
    def sel_ref(self) -> object: ...

    def edit_symbol(self, symbol: Symbol, rotations: int, multiplier: float = 1.0) -> bool: ...


def resolve_local(rows: tuple[BindingDecl, ...], control: ControlRef, event_kind: EventKind) -> BindingDecl | None:
    """Resolve one panel's own declared rows — no chain, no other contexts."""
    layer = ContextLayer(ref=ContextRef(kind=ContextKind.PANEL))
    for decl in rows:
        layer.rows.setdefault((decl.control.cls, decl.event_kind), []).append(decl)
    stack = ContextStack(layers=[layer])
    return stack.resolve(control, event_kind)


def fire(decl: BindingDecl, ops: PanelOps, event: EncoderEvent) -> bool:
    for effect in decl.effects:
        match effect:
            case SelectionEditEffect(role=role):
                sel = ops.sel_ref
                symbol = sel.symbol_for(role) if isinstance(sel, Selectable) else None
                if symbol is not None:
                    ops.edit_symbol(symbol, event.rotations, event.multiplier)
            case ParamEffect(symbol=param_symbol) | AudioCardEffect(param_symbol=param_symbol) if isinstance(
                param_symbol, str
            ):
                ops.edit_symbol(param_symbol, event.rotations, event.multiplier)
            case NoneEffect():
                pass
    return decl.consume
