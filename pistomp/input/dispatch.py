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

"""Panel-local binding resolution and effect firing (docs/input-contexts-implementation-plan.md §4).

Scoped to one panel's own rows, no cross-context chain — that only matters
once ControllerManager becomes a table builder (step 5)."""

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
from common.param_roles import ParamRole
from pistomp.input.event import EncoderEvent


@runtime_checkable
class Selectable(Protocol):
    def symbol_for(self, role: ParamRole) -> str | None: ...


class PanelOps(Protocol):
    """Not the concrete Panel type — pistomp/input must not import uilib back."""

    @property
    def sel_ref(self) -> object: ...

    def edit_symbol(self, symbol: str, rotations: int) -> bool: ...

    def input_step(self, direction: int, count: int, multiplier: float) -> bool: ...


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
                    ops.edit_symbol(symbol, event.rotations)
            case ParamEffect(symbol=param_symbol) if isinstance(param_symbol, str):
                ops.edit_symbol(param_symbol, event.rotations)
            case AliasEffect(target_control=_target, target_event_kind=target_kind):
                kind = target_kind or decl.event_kind
                if kind == EventKind.ROTATE:
                    d = event.rotations
                    if d != 0:
                        ops.input_step(1 if d > 0 else -1, abs(d), event.multiplier)
            case NoneEffect():
                pass
    return decl.consume
