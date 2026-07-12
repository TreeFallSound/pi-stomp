# R2 — Declaration schema and precedence

A read-only research report for the pi-stomp input-contexts work. It defines the
vocabulary of a binding declaration and the precedence rules of the context
stack, given the A3 control-class policy table as fixed input, and proves the
schema by round-tripping every declarable row of the R1 census.

All file:line references are to the `refactor/input-sink-transport` branch the
charter starts from. R1 row numbers refer to `docs/r1-binding-census.md` §3; R3
section numbers refer to `docs/r3-binding-truth.md`.

---

## 1. Summary

A binding declaration is a single frozen row that answers four questions — *who
is claimed, on which event, with what effect(s), under which lifetime and state
predicate* — so that the effective binding table owned by the handler can be
built by overlaying rows from a small, ordered set of *contexts*. Precedence is
**per-control-class with strict stack order within each class's bindable
chain** (Emacs-keymap semantics: a higher context shadows a lower one only for
the keys it actually binds, never for the whole control class). The A3 policy
table installs class-level overrides that sit *above* the stack: NAV is never
bindable, ANALOG controls are pedalboard-scoped only, VOLUME is protected from
panel shadowing by default (with an explicit on-screen opt-in escape), and
FOOTSWITCH events pierce panel/blend layers unless a panel has declared an
explicit, enabled footswitch binding for that `(id, event_kind)`. Selection-
dependent bindings stay data-like by carrying a `target: selection.symbol`
placeholder that the badge renderer resolves by a pure read of the owning
panel's current selection — one static row, not N re-published rows. Twenty of
the twenty-two R1 pathways round-trip as declarations; the only genuine escape
hatch is the NAM capture state machine's side-effectful transitions (the
encoder *gating* is declarable via an `enabled_when` predicate, so the escape
hatch is narrower than R1 feared). Multi-binding (one CC → many params) is
expressed natively with an `effects: list[Effect]`. The footswitch-piercing rule
is written as a testable statement and walked against every `SwitchEvent`
pathway in the census.

---

## 2. Schema design

### 2.1 Core declaration

A `BindingDecl` is a frozen value. One row claims one `(control, event_kind)`
pair on behalf of one context and carries an ordered list of effects (the
list is what makes multi-binding native). State predicates and a consume flag
live on the row so "consume but do nothing" and "only active while
`CaptureState.CAPTURING`" are first-class.

```python
from dataclasses import dataclass
from enum import Enum, auto

class ControlClass(Enum):
    NAV      = auto()   # the meta-control; axiomatically unbindable
    VOLUME   = auto()   # audiocard.MASTER by default; protected
    TWEAK    = auto()   # freely bindable per context (v3-only today)
    ANALOG   = auto()   # pots / expression; pedalboard-scoped only
    FOOTSWITCH = auto()

class EventKind(Enum):
    ROTATE   = auto()   # EncoderEvent.rotations != 0  /  AnalogEvent
    PRESS    = auto()   # SwitchEvent(kind=PRESS)
    LONGPRESS = auto()  # SwitchEvent(kind=LONGPRESS)

@dataclass(frozen=True)
class ControlRef:
    cls: ControlClass
    id: int | None       # None = "any id of this class" (used by aliases)
                         # concrete id for TWEAK/FOOTSWITCH/ANALOG

@dataclass(frozen=True)
class BindingDecl:
    control: ControlRef
    event_kind: EventKind
    effects: tuple["Effect", ...]   # ordered; multi-binding is just >1 entry
    context: "ContextRef"           # who declared this row (for badge + precedence)
    enabled_when: "Predicate | None" = None   # state gate; None = always
    consume: bool = True             # False = fire effect AND fall through
    autosync: bool = False           # analog only: emit current value on load
    # Badge honesty metadata (set by the builder, not the author):
    shadow_state: "ShadowState = ShadowState.ACTIVE"
```

`ShadowState` is derived, not authored: `{ACTIVE, SHADOWED, ORPHANED}` (see
§4.4). `consume: false` is the dual of `effect: none` — `consume:false, effects:(ParamEffect,)`
means "commit the parameter *and* let the event keep walking the stack";
`consume:true, effects:(NoneEffect,)` means "swallow it here." A row that wants
the handler fallback (R1 #23 NAM `FAILED` fall-through) is expressed by *not
declaring a row* in the failing state — the absence of a binding *is* the fall-
through declaration (R1 §6, row #23).

### 2.2 Effect vocabulary

`Effect` is a closed tagged union. Every effect in the R1 census maps to exactly
one variant; the union exists so the dispatch code is exhaustive (pyright can
prove it).

```python
class Effect: ...  # base, never instantiated

@dataclass(frozen=True)
class ParamEffect(Effect):
    plugin: "PluginRef"          # instance_id (resolved at pedalboard load)
    symbol: str | "SelectionSymbol"   # "thr", ":bypass", or selection.symbol
    commit: bool = True          # WebSocket send_parameter on fire
    mirror: bool = True          # reconcile from inbound param_set echo

@dataclass(frozen=True)
class MidiCcEffect(Effect):
    cc_ref: "CcRef" | "SelectionSymbol"   # "channel:CC" or selection-resolved
    toggle: bool = False          # footswitch absolute toggle (127/0 alternation)
    value_source: "ValueSource" = ValueSource.EVENT  # event.new_midi_value / raw

@dataclass(frozen=True)
class AudioCardEffect(Effect):
    param_symbol: str            # "MASTER", "CAPTURE_VOLUME", ...
    card: str = "default"        # which audio card

@dataclass(frozen=True)
class CallbackEffect(Effect):
    name: str                     # resolved via Handler.get_callback (e.g. "next_snapshot")

@dataclass(frozen=True)
class RelayEffect(Effect):
    relays: tuple[str, ...]       # ("LEFT",) / ("LEFT","RIGHT")

@dataclass(frozen=True)
class PresetEffect(Effect):
    direction: str               # "UP" | "DOWN" | "<int>"

@dataclass(frozen=True)
class TapTempoEffect(Effect): ...

@dataclass(frozen=True)
class SelectionEditEffect(Effect):
    """Edit the symbol of the currently-selected widget of the owning panel.
    Resolved at fire time from panel.sel_ref.symbol. The badge renderer reads
    the same sel_ref to name the badge (§8 Q2)."""
    fallback_symbol: str | None = None   # None = no-op if selection has no symbol

@dataclass(frozen=True)
class AliasEffect(Effect):
    """Re-dispatch the event as if it came from a different control. The alias
    target's own bindings are NOT consulted (no second cascade); the alias
    fires the aliased control's *base* behavior. Used by NAM enc1→NAV (R1 #17-
    19), tweak-click→NAV-click fallback (R1 #26), and the footswitch-tile re-
    dispatch (R1 #37)."""
    target_control: ControlRef
    target_event_kind: EventKind | None = None   # None = same kind

@dataclass(frozen=True)
class NoneEffect(Effect):
    """Consume but do nothing. Meaningful only with consume=True (§8 Q5)."""
```

`SelectionSymbol` is a sentinel: `selection.symbol` — "resolve to the symbol
of the owning panel's current selection at fire/render time." It is the only
piece of late binding in the schema, and it is a pure read of panel state (no
re-registration), which is what keeps it data-like (§8 Q2).

### 2.3 Contexts

A `ContextRef` names a scope that owns a set of declarations. There are four
kinds; the stack order is fixed by the precedence spec (§4):

```python
@dataclass(frozen=True)
class ContextRef:
    kind: "ContextKind"            # PEDALBOARD | PANEL | SYSTEM | BLEND
    name: str | None               # panel/plugin name for PANEL; None for others
    priority: int = 0              # within-kind tiebreak; higher wins
```

The PEDALBOARD context is singleton and always at the bottom of the stack. PANEL
contexts are pushed/popped with their paint panel (one per `accepts_input`
panel on the `PanelStack`). The SYSTEM context (main panel chrome: footswitch
tiles, preset title) and BLEND context are also stack-resident. See §4.2 for
the per-class chain.

### 2.4 Worked examples

**(a) Static pedalboard** — footswitch 0 → pluginA `:bypass` (R1 #30):

```yaml
- control: { cls: FOOTSWITCH, id: 0 }
  event_kind: PRESS
  context: { kind: PEDALBOARD }
  effects:
    - MidiCcEffect: { cc_ref: "13:60", toggle: true }
  # The associated ParamEffect rows (pluginA/:bypass, pluginB/:bypass) are
  # registered by ControllerManager from TTL MIDI-learn as echo-only:
  #   effects: [ParamEffect(pluginA, ":bypass", commit=false, mirror=true)]
  # They ride the CC emit; the badge names all of them (§8 Q6).
```

**(b) Static panel** — compressor enc 2 → `thr` (R1 #5):

```yaml
- control: { cls: TWEAK, id: 2 }
  event_kind: ROTATE
  context: { kind: PANEL, name: "compressor" }
  effects:
    - ParamEffect: { plugin: selection.plugin, symbol: "thr" }
```

**(c) Selection-dependent** — compressor enc 1 → selected arc's symbol (R1 #4):

```yaml
- control: { cls: TWEAK, id: 1 }
  event_kind: ROTATE
  context: { kind: PANEL, name: "compressor" }
  effects:
    - SelectionEditEffect: {}
  # badge resolves to the selected ArcSelectable.symbol at render time
```

**(d) Consume-no-op** — graphic EQ enc 2/3 (R1 #11, #12):

```yaml
- control: { cls: TWEAK, id: 2 }
  event_kind: ROTATE
  context: { kind: PANEL, name: "graphic_eq" }
  effects: [ NoneEffect ]
  consume: true
- control: { cls: TWEAK, id: 3 }      # identical
  event_kind: ROTATE
  context: { kind: PANEL, name: "graphic_eq" }
  effects: [ NoneEffect ]
  consume: true
```

**(e) Alias** — NAM enc 1 → NAV (R1 #17–#19):

```yaml
- control: { cls: TWEAK, id: 1 }
  event_kind: ROTATE
  context: { kind: PANEL, name: "nam" }
  effects: [ AliasEffect: { target_control: { cls: NAV, id: null }, target_event_kind: ROTATE } ]
  consume: true
- control: { cls: TWEAK, id: 1 }
  event_kind: PRESS
  context: { kind: PANEL, name: "nam" }
  effects: [ AliasEffect: { target_control: { cls: NAV, id: null }, target_event_kind: PRESS } ]
- control: { cls: TWEAK, id: 1 }
  event_kind: LONGPRESS
  context: { kind: PANEL, name: "nam" }
  effects: [ AliasEffect: { target_control: { cls: NAV, id: null }, target_event_kind: LONGPRESS } ]
```

The alias fires the *base* NAV behavior (`input_step` / `input_event`) directly
— it does not re-enter the cascade, so NAV's "no badge" invariant is preserved
(R1 §6 note on #17; A3 NAV exclusion). The aliasing panel may badge the
aliasing control as "→ NAV" or omit it (§8 Q3).

**(f) Multi-binding** — one CC, two bypasses (R3 §7e):

```yaml
- control: { cls: FOOTSWITCH, id: 0 }
  event_kind: PRESS
  context: { kind: PEDALBOARD }
  effects:
    - MidiCcEffect: { cc_ref: "13:60", toggle: true }
    - ParamEffect: { plugin: pluginA, symbol: ":bypass", commit: false, mirror: true }
    - ParamEffect: { plugin: pluginB, symbol: ":bypass", commit: false, mirror: true }
  # The CC emit (effect 0) is the primary; the two ParamEffects are echo-only
  # (commit=false) because mod-host applies the bypass on the CC and echoes
  # param_set back. The badge names both plugins (R3 §7e desired).
```

**(g) State-conditional** — NAM enc 2/3 swallowed during CAPTURING (R1 #22, #24):

```yaml
- control: { cls: TWEAK, id: 2 }
  event_kind: ROTATE
  context: { kind: PANEL, name: "nam" }
  enabled_when: { predicate: "capture_state in (CAPTURING, DONE, ABORTED)" }
  effects: [ NoneEffect ]
  consume: true
- control: { cls: TWEAK, id: 2 }
  event_kind: ROTATE
  context: { kind: PANEL, name: "nam" }
  enabled_when: { predicate: "capture_state == IDLE" }
  effects:
    - AudioCardEffect: { param_symbol: "CAPTURE_VOLUME" }
# R1 #23 FAILED fall-through is expressed by NOT declaring a row for FAILED;
# the panel's capture_state==FAILED window has no enc-2 binding, so the event
# falls through the stack to the handler's parameter-dialog overlay.
```

The `enabled_when` predicate is a closed expression over a small set of named
panel-state enums (`capture_state`, `blend_active`, `tuner_active`, …). It is
evaluated by the precedence resolver, not by the panel's `on_event` — so the
declaration stays data-like and the NAM panel's `on_event` shrinks to just the
state-machine transitions (Start/Abort/Retry buttons and the side effects on
`routing.connect_monitor` / `_engine.start` / `_engine.abort`), see §6.

---

## 3. Census round-trip

Every declarable row of R1 §3 expressed in the schema. Rows marked **escape
hatch** are reclassified here with rationale (§6 collects them).

| R1 # | Declaration (sketch) | Notes |
|------|----------------------|-------|
| 1 | *(no declaration — NAV axiom)* | NAV is unbindable by A3; `Panel.handle` owns it (`uilib/panel.py:212-219`). The "declaration" is the A3 override, not a row. |
| 2 | *(no declaration — NAV axiom)* | Same; NAV CLICK → `input_event(CLICK)`. |
| 3 | *(no declaration — NAV axiom)* | Same; NAV LONGPRESS → `input_event(LONG_CLICK)`. |
| 4 | `TWEAK/1 ROTATE in compressor PANEL → SelectionEditEffect` | selection-dependent; badge resolves sel.symbol. |
| 5 | `TWEAK/2 ROTATE in compressor PANEL → ParamEffect(plugin, "thr")` | static panel. |
| 6 | `TWEAK/3 ROTATE in compressor PANEL → ParamEffect(plugin, "rat")` | static panel; **migrates off enc 3** if enc 3 is VOLUME-typed (§8 Q4). |
| 7 | `TWEAK/1 ROTATE in gx_cabinet PANEL → SelectionEditEffect` | selection-dependent. |
| 8 | `TWEAK/2 ROTATE in gx_cabinet PANEL → ParamEffect(plugin, "c_model")` | static panel. |
| 9 | `TWEAK/3 ROTATE in gx_cabinet PANEL → ParamEffect(plugin, "CLevel")` | static panel; same enc-3 caveat as #6. |
| 10 | `TWEAK/1 ROTATE in graphic_eq PANEL → SelectionEditEffect` (gain_sym of selected band) | selection-dependent. |
| 11 | `TWEAK/2 ROTATE in graphic_eq PANEL → NoneEffect, consume=true` | consume-no-op. |
| 12 | `TWEAK/3 ROTATE in graphic_eq PANEL → NoneEffect, consume=true` | consume-no-op. |
| 13 | `TWEAK/1 ROTATE in parametric_eq PANEL → SelectionEditEffect` (gain_sym, guard on non-null) | selection-dependent; `enabled_when: selection.gain_sym != null` or `SelectionEditEffect.fallback_symbol=None`. |
| 14 | `TWEAK/2 ROTATE in parametric_eq PANEL → SelectionEditEffect` (freq_sym) | selection-dependent. `SelectionEditEffect` reads the selected band's freq_sym. |
| 15 | `TWEAK/3 ROTATE in parametric_eq PANEL → SelectionEditEffect` (q_sym, guard on non-null) | selection-dependent. |
| 16 | `TWEAK/1 ROTATE in multiband_menu PANEL → SelectionEditEffect` (delegates to `ParamSlotWidget.on_encoder_rotation`) | selection-dependent; same row shape as #4. |
| 17 | `TWEAK/1 ROTATE in nam PANEL → AliasEffect(NAV, ROTATE)` | alias; A3-safe (no NAV badge). |
| 18 | `TWEAK/1 PRESS in nam PANEL → AliasEffect(NAV, PRESS)` | alias. |
| 19 | `TWEAK/1 LONGPRESS in nam PANEL → AliasEffect(NAV, LONGPRESS)` | alias. |
| 20 | `TWEAK/2 ROTATE in nam PANEL [IDLE] → AudioCardEffect(CAPTURE_VOLUME)` | `enabled_when: capture_state==IDLE`. |
| 21 | `TWEAK/3 ROTATE in nam PANEL [IDLE] → AudioCardEffect(MASTER)` | `enabled_when: capture_state==IDLE`. |
| 22 | `TWEAK/2 ROTATE in nam PANEL [CAPTURING] → NoneEffect, consume=true` | `enabled_when: capture_state in (CAPTURING, DONE, ABORTED)` (merged with #24). |
| 23 | *(no declaration — FAILED fall-through)* | The absence of an enc-2/3 binding in the FAILED state *is* the declaration; falls through to handler parameter dialog (R1 §6 #23). |
| 24 | `TWEAK/3 ROTATE in nam PANEL [DONE/ABORTED] → NoneEffect, consume=true` | merged with #22's predicate. |
| 25 | `TWEAK/? LONGPRESS (per-encoder config) in PEDALBOARD → CallbackEffect(name)` | encoder longpress → singleton callback (no chord resolver, per §8 Q6 note). |
| 26 | `TWEAK|VOLUME PRESS (no panel claim) in BASE_PANEL → AliasEffect(NAV, PRESS)` | the "tweak click == NAV click" convenience fallback, declared in the base panel context so it sits *below* plugin panels. |
| 27 | `ANALOG/? ROTATE in PEDALBOARD → MidiCcEffect(cc_ref)` | pedals pierce panels (A3) — enforced by ANALOG having no panel-chain entries (§4.3). |
| 28 | *(meta)* | #28 is the *echo* side of #27: TTL MIDI-learn adds echo-only `ParamEffect(plugin, symbol, commit=false, mirror=true)` onto the same control's effects list (multi-binding). |
| 29 | `VOLUME ROTATE in PEDALBOARD → AudioCardEffect(MASTER)` | VOLUME protected from panel shadowing (§8 Q4); panels can only override via explicit `override_volume` flag. |
| 30 | `FOOTSWITCH/? PRESS in PEDALBOARD → MidiCcEffect(toggle=true) + echo-only ParamEffects` | pierces panels (§5). |
| 31 | `FOOTSWITCH/? PRESS in PEDALBOARD → PresetEffect(UP/DOWN/n)` | pierces panels. |
| 32 | `FOOTSWITCH/? PRESS in PEDALBOARD → TapTempoEffect` | pierces panels; `enabled_when: taptempo.is_enabled()`. |
| 33 | `FOOTSWITCH/? PRESS in PEDALBOARD → MidiCcEffect(toggle=true)` (relay_list populated but short-press emits CC) | pierces panels; relay toggles only on LONGPRESS (#34). |
| 34 | `FOOTSWITCH/? LONGPRESS in PEDALBOARD → RelayEffect(relays)` | pierces panels; `enabled_when: relay_list non-empty`. Bypasses chord resolver (predicate on the row, not panel opt-in). |
| 35 | `FOOTSWITCH/? LONGPRESS in PEDALBOARD → CallbackEffect(name)` (chord-resolved) | pierces panels; the chord window is a transport concern, fired by `chord_helper.tick()`; the row's effect is the resolved callback name. |
| 36 | *(meta — dual-source)* | #36 is the collision case: enc-1 CC binding (PEDALBOARD) shadows selection-dependent enc-1 (compressor PANEL). Expressed as *two* rows at different contexts; the precedence resolver picks the panel row while the panel is open and marks the PEDALBOARD row `SHADOWED` (§4.4, §8 Q7). |
| 37 | `FOOTSWITCH tile NAV-click in SYSTEM → AliasEffect(FOOTSWITCH, PRESS)` | the footswitch tile in the main-panel chrome is a SYSTEM-context alias; the re-dispatched event re-enters the cascade and pierces per §5. |
| 38 | `plugin tile NAV-click in SYSTEM → CallbackEffect(show_fullscreen_panel \| toggle_plugin_bypass)` | the main-panel chrome owns plugin-tile actions; these are selection-CLICK actions on the tile widget, declarable as `CallbackEffect` rows keyed off the selected widget, not raw NAV bindings (NAV stays unbindable). |
| 39 | `preset title NAV-click in SYSTEM → CallbackEffect(draw_preset_menu)` | same — selection-CLICK action on the title widget. |
| 40 | `menu item NAV-click in SYSTEM → CallbackEffect(menu_action)` | the system menu is a PANEL context whose widgets carry `(label, callback, arg)`; selection-CLICK dispatch is the mechanism, not a NAV binding. |
| 41 | `ANALOG/? ROTATE in BLEND → (blend diff-map send)` | blend is a context row (§8 Q8); it sits in the ANALOG chain between PANEL (empty for analog) and PEDALBOARD. |

**Rows reclassified as escape hatches:** none beyond the NAM capture state
machine (§6). R1 §1 said "twenty of the twenty-two" were declarable; with
`enabled_when`, the count rises — the only non-declarable surface is the NAM
state machine's *side-effectful transitions* (Start/Abort/Retry + JACK routing
+ engine subprocess), which are not input→effect pathways at all (they are
widget `action=` lambdas, already outside the binding table). So **every R1
input→effect row round-trips as a declaration**; the escape hatch is a panel-
lifecycle concern, not an input pathway.

---

## 4. Precedence spec

### 4.1 The rule, in one sentence

At dispatch time the resolver walks an ordered, per-control-class chain of
contexts and fires the first row whose `enabled_when` evaluates true; lower
contexts are shadowed for that `(control, event_kind)` pair only — *never* for
the whole control class. The A3 policy table installs class-level overrides
that sit above every chain and either forbid binding (NAV), restrict scope
(ANALOG: PEDALBOARD only), protect by default with an opt-in escape (VOLUME), or
mandate piercing unless a panel explicitly opts in (FOOTSWITCH).

### 4.2 Per-class chains

Each chain is a list of contexts consulted in order. The leftmost context that
holds an enabled matching row wins. `∅` means "no context of this kind can
bind this class."

| Class | Chain (top → bottom) | A3 override |
|-------|----------------------|-------------|
| NAV | `BASE_PANEL(selection machinery)` | **unbindable** — no row may name `cls=NAV` as a control; the base owns it. Aliases *targeting* NAV are allowed (they fire the base behavior, not a binding). |
| VOLUME | `PANEL(opt-in: override_volume=true)` → `BLEND` → `PEDALBOARD` | **protected** — a PANEL row for `cls=VOLUME` is rejected at registration unless the panel authors `override_volume: true` and the panel carries unmistakable on-screen state for the override. Default config → PEDALBOARD `AudioCardEffect(MASTER)` fires. |
| TWEAK | `PANEL(top)` → `BLEND` → `PEDALBOARD` | freely bindable; the open panel wins, then blend, then pedalboard. |
| ANALOG | `BLEND` → `PEDALBOARD` | **pedalboard-scoped only** — `∅` for PANEL/SYSTEM. Blend is the only non-pedalboard context that can claim an analog control (§8 Q8). |
| FOOTSWITCH | `PANEL(opt-in: explicit fs row)` → `PEDALBOARD` | **pierce-by-default** — if no PANEL row matches `(FOOTSWITCH, id, kind)` and is enabled, the event skips PANEL and BLEND entirely and lands at PEDALBOARD (§5). |

### 4.3 Strict stack order vs per-control-class

Precedence is **per-control-class**, then *strict stack order within the
class's chain*. This is the answer to charter open question 3. A blanket
"strict stack order across all controls" would force a panel that wants
tweak-encoder-2 to also swallow the footswitch (it shouldn't), and a blanket
"per-control-class without stack order" would lose the panel-shadows-pedalboard
relationship. The per-class chain keeps the shadowing *local* to the controls a
context actually binds — Emacs-keymap semantics (§7.2).

### 4.4 Shadowed vs orphaned vs active

`ShadowState` is **derived at render time from precedence**, not stored per-row
by the author. The builder tags each row:

- `ACTIVE` — this row is the winner of its chain for the current context stack.
- `SHADOWED` — a higher context in this row's chain has an enabled matching
  row; this row exists in the table but will not fire while the higher context
  is up. (R3 §7b: panel context shadows TTL binding.)
- `ORPHANED` — the row's `ControlRef` is no longer present in the hardware
  `controllers` dict (e.g. config overlay reassigned the CC, R3 §7a). The row
  stays in the table for diagnostics; the badge either shows it in a shadowed
  state or omits it (charter requirement 5).

This answers R3 §10 Q2: state is *derived* from precedence + hardware presence
at render time; the schema does not require per-row authored state. The
`shadow_state` field on `BindingDecl` is the builder's cache, refreshed on
context-stack push/pop, pedalboard load, and CC reassignment.

### 4.5 Context stack structure

The input context stack is a **separate structure from the paint `PanelStack`**
(charter question 10; R1 §7 #10). The paint stack walks top-down for paint and
*does not* walk for input — only `pstack.current` is consulted
(`pistomp/lcd320x240.py:271-273`). The input context stack mirrors the paint
stack's lifetime for `accepts_input` panels (decorative `ShroudedPanel`s push
nothing) and adds the singleton PEDALBOARD context at the bottom and the BLEND
context as a layer between PANEL and PEDALBOARD for the classes blend can claim.

```python
@dataclass
class ContextStack:
    layers: list[ContextLayer]   # bottom (PEDALBOARD) → top
    # Each ContextLayer carries the ContextRef + that context's BindingDecl rows
    # indexed by (ControlClass, event_kind) for O(1) lookup per class chain.
```

Push/pop of a panel pushes/pops a `ContextLayer` in lockstep with the paint
`PanelStack`'s `accepts_input`-filtered current-pointer (which `pop_panel`
already maintains, `uilib/panel.py:569-575`). The resolver never walks the
paint stack for input; it walks the `ContextStack` per-class chain. This is the
fix for R1's finding that `PanelStack` is a paint stack, not an input stack.

---

## 5. Footswitch-piercing rule

### 5.1 Testable statement

> **Piercing rule.** For every `SwitchEvent` `e` such that
> `isinstance(e.controller, Footswitch)` is true, the dispatch cascade in
> `Modhandler.handle` (`modalapi/modhandler.py:248-263`) MUST satisfy all of:
>
> 1. Before offering `e` to `self._lcd.handle(e)` (which would route it to
>    `PanelStack.current`), the resolver consults the effective binding table
>    for any row with `control.cls == FOOTSWITCH`, `control.id == e.controller.id`,
>    `event_kind` matching `e.kind`, `context.kind == PANEL`, and
>    `enabled_when` evaluating true under the current panel state.
> 2. If **no** such PANEL-context row exists, the cascade MUST skip
>    `self._lcd.handle(e)` and `self.active_blend_mode.intercept(e)` and
>    dispatch `e` directly to `self._handle_switch(e)`
>    (`modalapi/modhandler.py:290`), which routes to `_handle_footswitch`.
> 3. If such a PANEL-context row exists and is enabled, the cascade routes `e`
>    through `self._lcd.handle(e)` as usual, so the panel can consume it.
> 4. The piercing decision is made **once per event**, at the top of
>    `Modhandler.handle`, before any panel or blend code runs. It is a
>    per-control-class rule, not a per-panel convention.

### 5.2 Enforcement point

A single guard at the top of `Modhandler.handle`, above the existing three-slot
cascade:

```python
def handle(self, event):
    if isinstance(event, SwitchEvent) and isinstance(event.controller, Footswitch):
        if not self._panel_claims_footswitch(event):
            # pierce — skip LCD and blend
            return self._handle_switch(event)
    # existing cascade (unchanged)
    if self._lcd is not None and self._lcd.handle(event): return True
    if self.active_blend_mode and self.active_blend_mode.intercept(event): return True
    match event: ...
```

`_panel_claims_footswitch` is a query over the effective binding table
(§4.5): "is there an active PANEL-context row for `(FOOTSWITCH, id, kind)`?"
This replaces today's structural accident (no panel `on_event` matches a
footswitch `SwitchEvent`, R1 §5) with an explicit opt-in, and it is the
single place the A3 footswitch policy is enforced.

### 5.3 Walk against every `SwitchEvent` pathway in R1

| R1 # | Pathway | Panel claims fs? | Result | Matches today? |
|------|---------|------------------|--------|----------------|
| 30 | fs short, `midi_CC` set | no | pierce → `_handle_footswitch` short path → CC 0/127 emit (`pistomp/handler.py:155-161`). ✓ | yes (R1 §5: today by structural accident) |
| 31 | fs short, `preset:` | no | pierce → preset callback (`handler.py:149-154`). ✓ | yes |
| 32 | fs short, `tap_tempo` enabled | no | pierce → `taptempo.stamp` (`handler.py:146-148`); `enabled_when: taptempo.is_enabled()`. ✓ | yes |
| 33 | fs short, relay_list populated | no | pierce → short path emits CC; relay is NOT toggled on short press (`handler.py:159-161` only does midi_CC). ✓ | yes (R1 #33 notes relay toggles only on longpress) |
| 34 | fs longpress, relay_list populated | no | pierce → longpress path → `toggle_relays` + `set_led`, **bypasses chord resolver** (`handler.py:132-139`); the row's `enabled_when: relay_list non_empty` describes the bypass. ✓ | yes |
| 35 | fs longpress, `longpress:` set | no | pierce → longpress path → `chord_helper.observe` → `tick()` resolves callback (`handler.py:140-142`, `footswitch_chords.py:58-60`). ✓ | yes |
| 37 | NAV-click on footswitch tile (re-dispatch) | initial event is NAV (consumed by base); re-dispatched event has `controller = Footswitch` and re-enters `handle` | pierce (no panel claims the re-dispatched footswitch) → `_handle_footswitch` exactly as #30. ✓ The alias row lives in the SYSTEM context (`pistomp/lcd320x240.py:613-616`), not a PANEL context, so it does not trigger the panel-claim check. | yes |

**Conclusion:** the rule is consistent with every `SwitchEvent` pathway in the
census and is enforced at exactly one cascade point. Today's behavior is
preserved *structurally* (no panel claims a footswitch today), and the rule
adds the explicit opt-in the charter requires (A3) without weakening the
existing pierce.

---

## 6. Escape hatches

The named list. Each entry is the reason it cannot be data.

### 6.1 NAM capture state machine (R1 #17–#24, partial)

**What stays imperative:** the `CaptureState` transitions
(`IDLE → CAPTURING → DONE|FAILED|ABORTED → IDLE`) and the side effects on
`routing.connect_monitor` / `_engine.start` / `_engine.abort`
(`pistomp/nam/panel.py`, `pistomp/nam/engine.py`).

**Why it cannot be data:**
- The transitions fire on **widget `action=` lambdas** (Start/Abort/Retry
  buttons), not on input→effect pathways. They cause *external* side effects
  (JACK port connect/disconnect, subprocess launch/abort, filesystem writes).
  The binding table's `Effect` vocabulary is closed over pi-stomp's own outputs
  (MIDI CC, WebSocket param, audio card, named callback, relay, preset, tap
  tempo). "Connect JACK monitor," "launch a subprocess," "write a WAV file" are
  not binding effects; they are panel lifecycle.
- The state machine is *driving* the `enabled_when` predicates, not *driven by*
  them. The declarations (#20–#24) read `capture_state`; only the panel's
  `on_event`/action code can *change* `capture_state`. That mutation is the
  irreducible imperative core.

**What does NOT need to stay imperative:** the encoder *gating* (#22, #24
swallow; #23 fall-through; #20–#21 IDLE audio nudge) is fully declarable via
`enabled_when` + `AudioCardEffect`/`NoneEffect`. After migration, the NAM
panel's `on_event` handles only the state-machine button actions and the state
transitions; the encoder pathways are declarations. This is the narrower
escape hatch R1 §6 hoped for.

The charter's A2 ("`on_event` survives only for genuinely modal panels that
are state machines") is satisfied: NAM is the canonical modal panel, and its
`on_event` shrinks but does not disappear.

### 6.2 (No others)

No other R1 row requires an escape hatch. The multiband-menu "slot identity
swap" R1 §1 alluded to is the selection-dependent dispatch of #16, which is
declarable as `SelectionEditEffect` (R1 §6 confirms this). The tuner panel has
no `on_event` of its own (R1 §2 lists `plugins/notes/panel.py` as "none — see
below" and the tuner is a separate fullscreen panel that is fully NAV-
operable). The system menu (#40) is declarable as `CallbackEffect` rows on
menu items, which are selection-CLICK actions — not raw NAV bindings.

---

## 7. Prior-art study

### 7.1 mod-ui "addressings"

**Findings.** The MOD pedalboard bundle carries an `addressings.json`
(`docs/lv2-ttl-guide.md:86`, `:250`, `:373`), referenced from the pedalboard
TTL as `pedal:addressings <addressings.json>`. The on-device shape, per
`lv2-ttl-guide.md:376-380`, is:

```json
{ "/bpm": [] }
```

— a mapping from pedalboard port path to a *list* of hardware-actuator
bindings. No pi-stomp code reads `addressings.json` today: a repository-wide
search for "addressing" (excluding docs) returns zero hits in `modalapi/`,
`pistomp/`, `uilib/`, or `blend/`. The TTL parser (`modalapi/pedalboard.py`)
parses `lv2:port midi:binding` into `Parameter.binding` (R3 §2) but does not
touch the pedalboard-level `addressings.json`. So mod-ui's addressings model is
the *upstream* hardware-actuator binding concept (per-port lists of bindings,
presumably for the MOD-UI UI's hardware-control assignment view), and pi-stomp's
binding truth today flows through the *plugin*-level `midi:binding` on
individual LV2 ports, not the pedalboard-level `addressings.json`.

**Decision: deliberate divergence.** mod-ui's addressings are per-port lists
owned by the pedalboard bundle; pi-stomp's contexts are per-control-class
chains owned by the handler, layered (pedalboard → panel → blend). They overlap
in *subject* (which hardware actuator drives which parameter) but not in
*authority*: pi-stomp is the single authority for its own hardware (A5), and
mod-host is the authority for what its MIDI-learn map contains. The schema here
does **not** mirror `addressings.json` — it diverges deliberately because:
1. pi-stomp needs panel-context shadowing that `addressings.json` (a flat
   per-pedalboard map) cannot express.
2. pi-stomp's multi-binding (one CC → many params) is expressed as an ordered
   `effects` list on a control-keyed row, not a port-keyed list.
3. `addressings.json` is not read today; importing it would create a second
   binding authority alongside the handler's table, violating A5.

**Interop note.** When MOD-UI broadcasts a `midi_map` message
(`modalapi/ws_protocol.py:143-156`), pi-stomp already applies it live
(`modalapi/modhandler.py:616-618` via `handler.py:224-241`). In the new schema,
that live-learn path becomes "add an echo-only `ParamEffect` to the
PEDALBOARD-context row for that control" — same effect, expressed as a table
mutation. This is the only interop surface; `addressings.json` itself stays
unparsed.

### 7.2 Keymap precedence (Emacs)

**Model.** Emacs resolves a keypress by consulting an ordered list of active
keymaps: `overriding-local-map` (highest), then the `keymap` text property, then
`local-key-map`, then `global-key-map`. The crucial property is that **a higher
map shadows a lower map only for the keys it actually defines** — it does not
"swallow" the whole keyboard. A higher map that is silent for a key lets the
lower maps answer. Separately, `overriding-local-map` is a class-level override
that is installed *above* the normal order and shadows everything for its keys
without the lower maps being consulted at all.

**Adaptation.** The per-control-class chain (§4.2) is the Emacs keymap list,
applied once per control class: a PANEL context (like `local-key-map`) shadows
the PEDALBOARD context (like `global-key-map`) *only* for the `(control,
event_kind)` pairs the panel declares. A panel binding tweak-encoder-2 does
not shadow the pedalboard binding of tweak-encoder-1 — the unanswered key falls
through. The A3 policy table is the `overriding-local-map`: an axiom-level
override installed above the chain. NAV's "unbindable" rule is an
`overriding-local-map` that *no context may clear*; ANALOG's "pedalboard-scoped
only" is an `overriding-local-map` that forbids PANEL entries entirely (the
chain is just `BLEND → PEDALBOARD`); FOOTSWITCH pierce-by-default is an
`overriding-local-map` that routes the event around PANEL unless the panel
itself has declared an opt-in row (which clears the override for that one
control).

**Why not VS Code `when` clauses.** VS Code's model is "filter all keybindings
by a boolean `when` expression, last definition wins for a given key." That
collapses the precedence to a flat filter — it cannot express "the panel wins
for tweak-2 but the pedalboard still wins for tweak-1 while the panel is open."
Emacs's per-key fall-through is exactly the shadowing R1 §5 describes (panel
wins for the encoders it claims; the rest fall through to blend/handler).
`enabled_when` (§2.1) is the VS Code contribution — a per-row boolean gate;
the *ordering* is the Emacs contribution.

---

## 8. Answers to the 10 specific design questions

### Q1. State-conditional consumes (NAM enc 2/3 swallow during CAPTURING/DONE/ABORTED)

**Recommendation: the schema carries `enabled_when: Predicate`.** R1's
borderline rows (#22, #24) become declarable: one row per `(control,
event_kind, state)` with a `NoneEffect` and `consume: true`. The predicate is a
closed expression over a small set of named panel-state enums registered by the
panel (e.g. `capture_state`, `blend_active`, `tuner_active`). The NAM panel
*registers* `capture_state` as a predicate operand; it does not hand-author
per-state rows manually — the panel's declaration block lists them, and the
schema's builder emits one `BindingDecl` per (state, effect) pair. The escape
hatch (§6.1) narrows to the state-machine *transitions* and side effects, not
the encoder consumption. This is the design R1 §7 #1 asked R2 to decide; the
answer is "support `enabled_when`, and the NAM encoder gating is declarable."

### Q2. Selection-dependent declarations

**Recommendation: the declaration carries `target: selection.symbol` (a
placeholder), resolved at render/fire time by a pure read of the owning panel's
current selection.** R1 §7 #3 and R3 §10 #5 asked which of "placeholder row" or
"panel publishes resolved binding on focus change" is more data-like. The
placeholder is more data-like because:
- One static row per `(control, event_kind)` per panel, not N rows re-pushed on
  every NAV move. No diff churn in the binding table.
- The badge renderer reads `panel.sel_ref.symbol` (already maintained by the
  selection machinery, `uilib/panel.py:57-60`) at paint time — a pure read, no
  registration.
- The panel emits an invalidation signal on selection change (it already redraws
  on selection change), and the badge re-resolves. No binding-table mutation.

`SelectionEditEffect` (§2.2) and `ParamEffect(plugin, symbol=selection.symbol)`
both use the placeholder. The resolved value is computed in the badge layer, so
the binding table stays a static description of the panel's *capability*, not a
log of its *current* selection — which is what "data-like" means (R1 §7 #3).

### Q3. Cross-control aliases (NAM enc 1 → NAV)

**Recommendation: `AliasEffect(target_control, target_event_kind)` re-dispatches
the event as the aliased control's base behavior, with no second cascade and
no badge for the NAV target.** The alias row lives in the NAM PANEL context for
`(TWEAK, 1, ROTATE|PRESS|LONGPRESS)`. Because the alias fires the base
`input_step`/`input_event` directly (not a binding lookup), NAV's "no badge"
invariant (A3) is preserved: the alias does not create a NAV binding row, so
the badge renderer never sees NAV as bound. The aliasing control (tweak-1) may
be badged as "→ NAV" or omitted — a render-time choice, not a schema concern.
This matches R1's "single-key alias" classification (#17–#19).

### Q4. VOLUME encoder protection

**Recommendation: protect VOLUME from panel shadowing by default, with an
explicit `override_volume: true` panel opt-in that must carry unmistakable
on-screen state.** R1 §5 found the compressor/gx_cabinet/tap_reverb panels
silently shadow the volume encoder (`plugins/compressor_base.py:106-107`,
`plugins/gx_cabinet/panel.py:162-164`, `plugins/tap_reverb/panel.py:~158`).
This is a footgun: a v3 user with the default config (enc 3 = VOLUME) loses
output-volume control whenever one of these panels is open.

**Migration cost (deliberate, and worth stating):** the static panel-scoped
rows on enc 3 for `rat` (compressor), `CLevel` (gx_cabinet), and `decay`
(tap_reverb) — R1 #6, #9, and the tap_reverb enc-3 row — must either:
- rebind to a different tweak encoder id (enc 2 or enc 1) where available, or
- become selection-dependent on enc 1 (the A4 edit-in-place path), or
- the panel must author `override_volume: true` and show on-screen state that
  the volume encoder is *borrowed* — the only honest opt-out.

**Where enforced:** at registration time — a row with `control.cls == VOLUME`
and `context.kind == PANEL` is rejected unless the panel's context metadata
carries `override_volume: true`. At dispatch time, the chain (§4.2) already
places PANEL(opt-in) above PEDALBOARD, so an opted-in panel wins and any other
panel's VOLUME row is dead-on-arrival. This is a small breaking change for the
three named panels and is the *explicit* form of the "make the conflict
explicit" option R1 §5 offered. **If a report is allowed to kill part of a
plan, this kills the "panels may freely bind the volume encoder" reading of
A3's "tweak encoders freely bindable" row** — VOLUME is a distinct control
class from TWEAK, and A3's table lists it separately for a reason.

### Q5. "Consume but do nothing" bindings

**Confirmed: `consume: true, effects: (NoneEffect,)` is a first-class
declaration.** R1 #11, #12 (graphic EQ enc 2/3), #22, #24 (NAM enc 2/3 in
capture states) all use it. **Badge policy (charter requirement 5):** a
`NoneEffect` row is shown in its shadowed/inactive state or not shown — never
as live. Concretely: the badge for `(TWEAK, 2)` on an open graphic EQ panel
renders *nothing* (or a dim "—" tick), because the row's effect is `NoneEffect`
— it is honestly inactive. It must not render the *pedalboard's* shadowed
binding for enc 2 as if it were live. The precedence resolver tags the panel's
`NoneEffect` row `ACTIVE` and the pedalboard's enc-2 row `SHADOWED`; the
renderer shows the active row (which is a no-op) and hides or dims the shadowed
row. This is the "honest case the charter calls out."

### Q6. Multi-binding (one CC → many params)

**Recommendation: the schema allows a control to bind to multiple effects;
`effects: tuple[Effect, ...]` is the native representation.** R3 §7e found two
plugins' bypass on one footswitch CC. Today `controller.parameter` (single)
cannot represent it; the schema replaces that single field with the ordered
effects list. For the footswitch case, the primary effect is `MidiCcEffect(toggle)`
and the echo-only `ParamEffect(plugin, ":bypass", commit=false, mirror=true)`
rows for each MIDI-learned plugin are appended (the CC emit is what mod-host
applies; the params reconcile via the inbound `param_set` echo, exactly as
today). The badge renderer names all `ParamEffect` targets on the row — showing
both plugin names or a "multi" indicator (R3 §7e desired). This is *not* a
constraint; it is a capability, and it fixes the "display lie of omission" R3
§7e identified.

### Q7. Shadowed vs orphaned vs active state

**Recommendation: state is *derived* from precedence + hardware presence at
render time; the schema stores per-row metadata as a builder cache, not as
authored fields.** R3 §10 Q2 asked whether the table records state per entry or
derives it. Derive it:
- `ACTIVE` — the row is the winner of its chain for the current stack.
- `SHADOWED` — a higher context has an enabled matching row; this row stays in
  the table for badge rendering (shown dimmed or omitted, per §4.4).
- `ORPHANED` — the row's `ControlRef` is no longer in `hardware/controllers`
  (R3 §7a: config overlay reassigned the CC). The row is retained for
  diagnostics; the badge omits it or shows a small "orphaned" marker in a
  debug view.

The `shadow_state` field on `BindingDecl` (§2.1) is the builder's cache,
refreshed on: context-stack push/pop, pedalboard load, CC reassignment, and
MIDI-learn live-application. Authors never set it. This keeps the authored row
a pure description of *capability*; the *current* effective state is always a
function of (row, stack, hardware).

### Q8. Blend as a binding or a shadowing layer

**Recommendation: blend is a context — a row in the table — sitting in the
ANALOG and TWEAK chains between PANEL and PEDALBOARD.** R3 §7c/§7d found blend
consuming events upstream of the handler. Making blend a context (rather than a
layer above the table) means:
- The blend row for `(ANALOG, id, ROTATE)` lives in the `BLEND` context. In the
  ANALOG chain (`BLEND → PEDALBOARD`, §4.2) it shadows the PEDALBOARD CC row
  for that control while blend is active. The pedalboard row is tagged
  `SHADOWED` — honest.
- The R3 §7d bug (blend input's CC equals a TTL MIDI-learned CC → the
  MIDI-learned param goes silent because blend consumes the event before
  `_handle_encoder`) becomes *visible*: both rows exist, the blend row is
  `ACTIVE` and the TTL `ParamEffect` row is `SHADOWED by blend` — the badge
  shows the shadow state instead of silently dropping the param. The fix
  (reject blend input config that collides with a TTL binding, or reject the
  TTL binding) is a *registration-time* check the builder can do, which is
  impossible today because blend's claim lives outside the binding table.
- Blend still excludes MIDI-bound params from its diff maps
  (`blend/manager.py:199-210`); that exclusion is now a derived property of the
  table ("any `ParamEffect` on a PEDALBOARD row for a different control is
  MIDI-bound") rather than a hand-maintained set.

### Q9. Footswitch piercing

Written as a testable statement and walked against every `SwitchEvent` pathway
in R1 (#30–#35, #37) in **§5** above. The cascade enforcement point is a
single guard at the top of `Modhandler.handle`
(`modalapi/modhandler.py:248`), before the LCD/blend slots. The piercing
decision is a query over the effective binding table ("does any active
PANEL-context row claim this `(FOOTSWITCH, id, kind)`?"), not a convention.

### Q10. Context stack structure

**Recommendation: the input context stack is a *separate structure* from the
paint `PanelStack`, maintained in lockstep with the paint stack's
`accepts_input`-filtered current-pointer.** R1 §7 #10 found `PanelStack` does
not walk its stack for input — only `pstack.current` is consulted
(`pistomp/lcd320x240.py:271-273`), and `pop_panel` already walks backwards past
non-input panels to find the new `current` (`uilib/panel.py:569-575`). So the
paint stack is *almost* an input stack, but it carries decorative panels and
has no per-class chain. The fix:
- A `ContextStack` (§4.5) holds the layered `ContextLayer`s (PEDALBOARD bottom,
  PANEL layers for `accepts_input` panels, BLEND layer, SYSTEM layer). It is
  pushed/popped with the paint stack but only for `accepts_input` panels.
- The resolver consults the `ContextStack` per-class chain; it never walks the
  paint stack for input.
- The paint stack's `current` and the `ContextStack`'s top PANEL layer stay in
  sync because the same push/pop calls drive both.

This makes the charter's "context stack on top of the transport" a real
structure rather than a reinterpretation of the paint stack, and it removes the
R1 finding that the input stack "doesn't exist" as a structural concern.

---

## 9. Recommendation (final spec)

The implementation plan should build, in order:

1. **`BindingDecl` + `Effect` union + `ContextRef` + `ContextStack`** as the
   core abstraction (§2). Frozen dataclasses; pyright-exhaustive `match` on
   `Effect`. No `getattr`/`hasattr`.

2. **The per-class chains** (§4.2) as the precedence resolver. One method:
   `resolve(control_class, event) -> BindingDecl | None` that walks the
   appropriate chain top-down and returns the first enabled row. The
   `shadow_state` cache (§4.4) is recomputed on every stack mutation and every
   hardware-CC reassignment.

3. **The footswitch-piercing guard** (§5.2) at the top of `Modhandler.handle`.
   This is the single enforcement point for A3's footswitch policy and is
   covered by a dedicated test that asserts the guard runs before
   `_lcd.handle` for every footswitch `SwitchEvent`.

4. **The VOLUME protection** (§4.2, §8 Q4) at registration time: panic/reject
   a PANEL-context row with `control.cls == VOLUME` unless
   `override_volume: true` is declared. Migrate the three named panels
   (compressor `rat`, gx_cabinet `CLevel`, tap_reverb `decay`) off enc 3 —
   this is a deliberate breaking change and the implementation plan must list
   it as an acceptance item.

5. **Migration of the R1 census** panel by panel (charter: compressor and
   parametric EQ first). Each migration replaces an `on_event` override with
   a declaration block; the R1 table tracks declared / escape-hatched /
   remaining. The NAM panel keeps a *narrow* `on_event` (state-machine buttons
   + transitions, §6.1) and migrates its encoder gating to declarations.

6. **`Controller.parameter` → effects list** (R3 §10 Q7):
   `Controller.parameter` (single) becomes a denormalized cache of the
   `ACTIVE` row's first `ParamEffect`, kept for the
   `plugin.set_param_value` → `controller.set_value` reconcile path
   (`plugin.py:135-137`). The authoritative view is the table; the cache is
   rebuilt on stack mutation. Multi-binding (R3 §7e) is the reason a list is
   required, not a single field.

7. **Badge renderer reads only the table** (R3 §9 "what is already correct"):
   the LCD keeps reading `current.analog_controllers` + `footswitches`, which
   become views *projected from the table* by the builder. The one current
   drift point (R3 §6d #2 — the BlendMode object substituted into the analog
   icon slot) becomes a table-driven badge: the blend row's `ACTIVE` state
   tells the renderer to show the blend snapshot name instead of the
   parameter, eliminating the local decision.

**What this report kills:** the reading of A3 that lets panels freely bind the
VOLUME encoder (§8 Q4). The three named panels must migrate off enc 3. The
report does *not* kill the footswitch-pierce-by-default (preserved), the NAV
axiom (preserved), or the pot/expression pedalboard-scoping (preserved). The
NAM escape hatch is narrower than R1 §1 feared — the encoder gating is
declarable; only the state-machine transitions are imperative.