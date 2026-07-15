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

"""What a control does is declared data, not per-panel `if` chains: a
BindingDecl names a ControlRef + EventKind, a closed Effect union to fire,
and the ContextRef (PANEL/BLEND/PEDALBOARD/SYSTEM) that owns it. NAV is the
one axiom excluded from this entirely — see uilib/panel.py's Panel.handle.

ContextStack.resolve walks a fixed per-ControlClass chain (_CHAINS below,
highest precedence first) and returns the winning row for a (control,
event_kind) pair, tagging every row it passed over ACTIVE/SHADOWED/ORPHANED
(ShadowState) so a shadowed binding is visible rather than silently dead —
this same resolved answer is what on-screen badges render from (never a
widget's own guess). Consumers: pistomp/input/dispatch.py (per-panel
resolve_local), pistomp/controller_manager.py (the PEDALBOARD layer),
modalapi/modhandler.py (the BLEND layer). See pistomp/input/README.md for
how the pieces fit together end to end."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Union

from common.param_roles import ParamRole
from common.parameter import Symbol


class ControlClass(Enum):
    NAV = auto()  # the meta-control; axiomatically unbindable
    VOLUME = auto()  # audiocard.MASTER by default; protected
    TWEAK = auto()  # freely bindable per context (v3-only today)
    ANALOG = auto()  # pots / expression; pedalboard-scoped only
    FOOTSWITCH = auto()


class EventKind(Enum):
    ROTATE = auto()  # EncoderEvent.rotations != 0  /  AnalogEvent
    PRESS = auto()  # SwitchEvent(kind=PRESS)
    LONGPRESS = auto()  # SwitchEvent(kind=LONGPRESS)


class ContextKind(Enum):
    PEDALBOARD = auto()  # singleton, always at the bottom of the stack
    PANEL = auto()  # pushed/popped with an accepts_input panel
    SYSTEM = auto()  # main-panel chrome
    BLEND = auto()  # blend mode, between PANEL and PEDALBOARD


class ShadowState(Enum):
    ACTIVE = auto()  # this row is the chain winner for the current stack
    SHADOWED = auto()  # a higher context in this row's chain wins instead
    ORPHANED = auto()  # row's ControlRef is no longer in hardware.controllers


@dataclass(frozen=True)
class ControlRef:
    cls: ControlClass
    # int: panel tweak/volume slot (1-3). str: physical "channel:CC" identity
    # (ANALOG/FOOTSWITCH, matches Hardware.controllers' key). None = "any id
    # of this class" (aliases only).
    id: int | str | None


@dataclass(frozen=True)
class ContextRef:
    kind: ContextKind
    name: str | None = None  # panel/plugin name for PANEL; None for others
    priority: int = 0  # within-kind tiebreak; higher wins
    override_volume: bool = False  # PANEL only: opt-in to claim VOLUME rows (A3 Q4)


class SelectionSymbol:
    """Sentinel: resolve to the owning panel's sel_ref's symbol at fire/render
    time. Not instantiated; used as a type marker on Effect fields."""


# --- Effect union (closed; every R1 census row maps to exactly one variant) ---


class Effect:
    """Base of the closed Effect union. Never instantiated directly."""


@dataclass(frozen=True)
class ParamEffect(Effect):
    plugin: object  # PluginRef, resolved at pedalboard load
    symbol: Union[Symbol, type[SelectionSymbol]]
    commit: bool = True  # WebSocket send_parameter on fire
    mirror: bool = True  # reconcile from inbound param_set echo


@dataclass(frozen=True)
class MidiCcEffect(Effect):
    cc_ref: Union[str, type[SelectionSymbol]]  # "channel:CC" or selection-resolved
    toggle: bool = False  # footswitch absolute toggle (127/0 alternation)


@dataclass(frozen=True)
class AudioCardEffect(Effect):
    param_symbol: Symbol  # "MASTER", "CAPTURE_VOLUME", ...
    card: str = "default"


@dataclass(frozen=True)
class CallbackEffect(Effect):
    name: str  # resolved via Handler.get_callback (e.g. "next_snapshot")


@dataclass(frozen=True)
class RelayEffect(Effect):
    relays: tuple[str, ...]  # ("LEFT",) / ("LEFT", "RIGHT")


@dataclass(frozen=True)
class PresetEffect(Effect):
    direction: str  # "UP" | "DOWN" | "<int>"


@dataclass(frozen=True)
class TapTempoEffect(Effect):
    pass


@dataclass(frozen=True)
class SelectionEditEffect(Effect):
    """Resolved at fire time via sel_ref.symbol_for(role)."""

    role: ParamRole = ParamRole.GENERIC


@dataclass(frozen=True)
class NoneEffect(Effect):
    """Consume but do nothing. Meaningful only with consume=True."""


@dataclass(frozen=True)
class BlendEffect(Effect):
    """Live interpolation via a BlendMode's InputController. Carries the
    controller directly (typed object — common/ must not import blend/) rather
    than a string lookup, since it's one specific stateful attachment, not a
    generic named action."""

    input_controller: object


@dataclass(frozen=True)
class BindingDecl:
    control: ControlRef
    event_kind: EventKind
    effects: tuple[Effect, ...]
    context: ContextRef
    enabled_when: Callable[[], bool] | None = None
    consume: bool = True
    autosync: bool = False
    # Badge honesty metadata: set by the resolver, never authored.
    shadow_state: ShadowState = ShadowState.ACTIVE


@dataclass
class ContextLayer:
    ref: ContextRef
    rows: dict[tuple[ControlClass, EventKind], list[BindingDecl]] = field(default_factory=dict)

    def add(self, decl: BindingDecl) -> None:
        """Register a row. Each row states its own context,
        which is what makes aggregating already-authored rows into
        an ad hoc layer (see dispatch.resolve_local) safe."""
        if (
            decl.control.cls is ControlClass.VOLUME
            and decl.context.kind is ContextKind.PANEL
            and not decl.context.override_volume
        ):
            raise ValueError(
                f"PANEL context {decl.context.name!r} declared a VOLUME row without "
                "override_volume=True on its ContextRef"
            )
        key = (decl.control.cls, decl.event_kind)
        self.rows.setdefault(key, []).append(decl)


# Per-class chain: which ContextKinds are consulted, top (highest precedence)
# to bottom, for a given ControlClass. NAV is intentionally absent — it is an
# axiom enforced by the base panel, never a row in any layer.
_CHAINS: dict[ControlClass, tuple[ContextKind, ...]] = {
    ControlClass.VOLUME: (ContextKind.PANEL, ContextKind.BLEND, ContextKind.PEDALBOARD),
    ControlClass.TWEAK: (ContextKind.PANEL, ContextKind.BLEND, ContextKind.PEDALBOARD),
    ControlClass.ANALOG: (ContextKind.BLEND, ContextKind.PEDALBOARD),
    ControlClass.FOOTSWITCH: (ContextKind.PANEL, ContextKind.PEDALBOARD),
}


@dataclass
class ContextStack:
    layers: list[ContextLayer]  # bottom (PEDALBOARD) -> top

    def layers_for(self, kind: ContextKind) -> list[ContextLayer]:
        return [layer for layer in self.layers if layer.ref.kind is kind]

    def resolve(self, control: ControlRef, event_kind: EventKind) -> BindingDecl | None:
        """Walk this class's chain top-down; return the first row whose
        enabled_when evaluates true. Tags shadow_state on every candidate row
        considered along the way (mutates in place; rows are the builder's
        cache, never author-set)."""
        chain = _CHAINS.get(control.cls)
        if chain is None:
            return None

        candidates: list[BindingDecl] = []
        for kind in chain:
            for layer in reversed(self.layers_for(kind)):
                for decl in layer.rows.get((control.cls, event_kind), []):
                    if decl.control.id is None or decl.control.id == control.id:
                        candidates.append(decl)

        winner: BindingDecl | None = None
        for decl in candidates:
            enabled = decl.enabled_when is None or decl.enabled_when()
            if winner is None and enabled:
                winner = decl
                object.__setattr__(decl, "shadow_state", ShadowState.ACTIVE)
            elif winner is not None:
                object.__setattr__(decl, "shadow_state", ShadowState.SHADOWED)
        return winner
