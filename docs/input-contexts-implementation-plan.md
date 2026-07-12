# Input Contexts: Implementation Plan

**Audience:** the agent building this. This document consumes the accepted
research (`docs/r1-binding-census.md`, `docs/r2-schema-precedence.md`,
`docs/r3-binding-truth.md`) and the charter (`docs/input-contexts-charter.md`)
into a build order. It does **not** fold in `docs/r4-badge-surfaces.md` —
that report is long, has specific geometry/placement decisions we don't want
duplicated here, and isn't needed until the badge-rendering step (§7). Read it
fresh when you get there.

A1 (NAV unhijackable) is already applied and verified — `uv run pytest` and
`uv run pyright` are green on `refactor/input-sink-transport`.

---

## 1. Core abstraction (build first)

Module: **`common/contexts.py`**. `common/` today holds only plain,
dependency-light modules (`token.py`, `color.py`, `parameter.py`, `util.py`) —
no classes with behavior, just constants and pure functions. That makes it the
right home for now: both `uilib` (panels) and `pistomp`/`modalapi` (the
handler) need to import these types without creating a cycle. Revisit the
location once the first panel migration shows where the real center of
gravity is — likely `pistomp/input/` alongside `InputSink`/event types.

From R2 §2, verbatim shape (frozen dataclasses, pyright-exhaustive `Effect`
match, no `getattr`/`hasattr`):

```python
class ControlClass(Enum):
    NAV = auto()        # unbindable axiom
    VOLUME = auto()     # protected by default, opt-in override
    TWEAK = auto()       # freely bindable (v3 only today)
    ANALOG = auto()      # pedalboard-scoped only
    FOOTSWITCH = auto()

class EventKind(Enum):
    ROTATE = auto()
    PRESS = auto()
    LONGPRESS = auto()

@dataclass(frozen=True)
class ControlRef:
    cls: ControlClass
    id: int | None   # None = "any id of this class" (aliases only)

@dataclass(frozen=True)
class BindingDecl:
    control: ControlRef
    event_kind: EventKind
    effects: tuple["Effect", ...]     # >1 entry = multi-binding, native
    context: "ContextRef"
    enabled_when: "Predicate | None" = None
    consume: bool = True
    autosync: bool = False
    shadow_state: "ShadowState" = ShadowState.ACTIVE   # builder-set, not authored
```

`Effect` is a closed union: `ParamEffect`, `MidiCcEffect`, `AudioCardEffect`,
`CallbackEffect`, `RelayEffect`, `PresetEffect`, `TapTempoEffect`,
`SelectionEditEffect`, `AliasEffect`, `NoneEffect` (R2 §2.2). Each variant maps
1:1 to an effect kind found in the R1 census — no new kind should be needed
for existing panels; if one comes up mid-migration, that's a signal the
census missed a row.

`SelectionSymbol` is the one sentinel: "resolve to `panel.sel_ref`'s symbol at
fire/render time." It's what keeps selection-dependent bindings (compressor
enc1, graphic/parametric EQ enc1-3, multiband enc1) data-like without
publishing N rows per widget (R2 §8 Q2).

## 2. Context stack (build second, before the resolver)

A **separate structure from the paint `PanelStack`** (R2 §4.5, R1 §7 #10).
`PanelStack` only ever consults `.current` for input dispatch today — it was
never a real input stack, just paint order that happens to look like one.

```python
@dataclass
class ContextLayer:
    ref: "ContextRef"
    rows: dict[tuple[ControlClass, EventKind], list[BindingDecl]]

@dataclass
class ContextStack:
    layers: list[ContextLayer]   # bottom (PEDALBOARD) -> top
```

Lifecycle: pushed/popped in lockstep with the paint stack's
`accepts_input`-filtered current-pointer — the same `push_panel`/`pop_panel`
calls in `uilib/panel.py` drive both. The singleton `PEDALBOARD` layer sits
permanently at the bottom; a `BLEND` layer sits between `PANEL` and
`PEDALBOARD` for the control classes blend can claim (`ANALOG`, `TWEAK`); a
`SYSTEM` layer (main-panel chrome: footswitch tiles, preset title) is also
stack-resident.

A panel populates its layer via an optional method mirroring the existing
`build_widgets()` / spec-object convention already in this codebase (see
`plugins/layouts/compressor_spec.py`'s `build_arc_specs`, and the
`PluginPanel` subclass checklist in `plugins/base.py`):

```python
class Panel:
    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        """Static + selection-dependent bindings for this panel. Called once
        by the base at attach-time to populate this panel's ContextLayer.
        Base returns (); override to add tweak/footswitch bindings."""
        return ()
```

This is the same shape as `build_widgets()` (an overridable, base-called-once
method) and `build_arc_specs(spec)` (a builder returning frozen declarative
rows) — no new idiom introduced.

## 3. Precedence resolver (build third)

One method per the per-class chains in R2 §4.2 (Emacs-keymap semantics: a
higher context shadows a lower one only for the `(control, event_kind)` pairs
it actually declares, never the whole class — R2 §7.2):

| Class | Chain (top → bottom) | A3 override |
|---|---|---|
| NAV | `BASE_PANEL` only | Unbindable axiom. No row may name `cls=NAV`. Aliases may *target* NAV (fire base behavior, not a binding). |
| VOLUME | `PANEL(opt-in)` → `BLEND` → `PEDALBOARD` | Protected by default; a PANEL row is accepted only with `override_volume: true` **and** visible on-screen state while active (see §4 — this is a deliberate *use* of the escape hatch, not a migration away from it). |
| TWEAK | `PANEL(top)` → `BLEND` → `PEDALBOARD` | Freely bindable. Open panel wins, then blend, then pedalboard. |
| ANALOG | `BLEND` → `PEDALBOARD` | Pedalboard-scoped only; `∅` for PANEL/SYSTEM. |
| FOOTSWITCH | `PANEL(opt-in)` → `PEDALBOARD` | Pierce-by-default; PANEL must declare an explicit enabled row for `(id, kind)` to intercept (see §5). |

```python
def resolve(control_class: ControlClass, event) -> BindingDecl | None:
    """Walk this class's chain top-down; return the first row whose
    enabled_when evaluates true. Also tags shadow_state on every row seen."""
```

`shadow_state` (`ACTIVE` / `SHADOWED` / `ORPHANED`) is derived, not authored
(R2 §4.4): `ACTIVE` = chain winner; `SHADOWED` = a higher context has an
enabled matching row; `ORPHANED` = the row's `ControlRef` is no longer present
in `hardware.controllers` (e.g. config overlay reassigned the CC). Recompute
on stack push/pop, pedalboard load, and CC reassignment.

## 4. VOLUME: the enc-3 dual-purpose case

**Decision (supersedes an earlier draft of this plan):** Tweak3/Volume is
physically one knob, labeled `Tweak3/Volume` on the chassis — it must stay
freely assignable, not migrated away from panels. Compressor (`rat`),
gx_cabinet (`CLevel`), and tap_reverb (`decay`) keep their enc-3 bindings, but
each now declares `override_volume: true` on that row. The badge renderer
(deferred to the R4 read, §7) must show unmistakable on-screen state while the
override is active — e.g. a distinct tint or an explicit "volume overridden"
indicator — satisfying A3's "panel-level shadowing is explicit opt-in and
must carry unmistakable on-screen state" without removing the binding.

## 5. Footswitch-piercing guard

Testable statement (R2 §5.1) and enforcement point (R2 §5.2) — a single guard
at the top of `Modhandler.handle`, above the existing three-slot cascade:

```python
def handle(self, event):
    if isinstance(event, SwitchEvent) and isinstance(event.controller, Footswitch):
        if not self._panel_claims_footswitch(event):
            return self._handle_switch(event)   # pierce: skip LCD and blend
    if self._lcd is not None and self._lcd.handle(event): return True
    if self.active_blend_mode and self.active_blend_mode.intercept(event): return True
    match event: ...
```

`_panel_claims_footswitch` queries the effective binding table: "is there an
active PANEL-context row for `(FOOTSWITCH, id, kind)`?" This replaces today's
structural accident (no panel's `on_event` currently matches a footswitch
`SwitchEvent`) with an explicit, testable opt-in. Walked against every
`SwitchEvent` pathway in the R1 census (#30–#35, #37) in R2 §5.3 — all
preserved.

Write a dedicated test asserting the guard runs before `_lcd.handle` for every
footswitch `SwitchEvent` (requirement 3's "a test proves it" applies here as
well as to the NAV invariant).

## 6. Binding truth and the effective table (R3)

Today binding truth is dispersed across four stores with no merge view: the
TTL parser's `Parameter.binding`, `Hardware.controllers` (config overlay),
`ControllerManager.bind` (the *de facto* but not *owned* merge point), and
`Hardware.external_routing`. The handler becomes the single owner:

1. **`ControllerManager.bind` becomes a builder of the effective table**, not
   a silent mutator of `controller.parameter`. The silent-skip at a CC not
   found in `controllers` (today: orphaned TTL binding, no warning) becomes a
   table entry marked `ORPHANED`.
2. **Multi-binding.** `Controller.parameter` (single) becomes a denormalized
   cache of the `ACTIVE` row's first `ParamEffect`, kept only for the
   `plugin.set_param_value` → `controller.set_value` reconcile path
   (`plugin.py:135-137`). The table is authoritative; the cache rebuilds on
   stack mutation. Needed because R3 §7e shows two plugins' bypass sharing one
   CC — a single-valued field can't represent that.
3. **Blend is a context, not a shadowing layer above the table** (R2 §8 Q8).
   Its row lives in the `BLEND` layer for `(ANALOG/TWEAK, id, ROTATE)`. This
   makes the R3 §7d bug (blend's CC claim silently kills a co-located
   MIDI-learned parameter) *visible*: the TTL row gets tagged `SHADOWED by
   blend` instead of just going silent. Fix the bug as part of this step —
   reject the blend-input config or the TTL binding at registration time, not
   both silently colliding.
4. **The LCD stays a pure consumer.** No change needed to
   `lcd320x240.py`'s reads of `current.analog_controllers` /
   `hardware.footswitches` — those become projections *of* the table rather
   than `ControllerManager`'s ad hoc output. The one existing drift point (the
   `BlendMode` object substituted into the analog icon slot, R3 §6d #2)
   becomes table-driven: the blend row's `ACTIVE` state tells the renderer to
   show the snapshot name.
5. **mod-ui's `addressings.json` is not read or mirrored** (R2 §7.1,
   deliberate divergence) — pi-stomp remains the single authority for its own
   hardware; the live MIDI-learn interop path (`midi_map` broadcast) becomes
   "add an echo-only `ParamEffect` to the PEDALBOARD row for that control,"
   same effect as today, expressed as a table mutation instead of a field set.

## 7. Badge rendering — stop here, read R4 fresh

Once §1–6 exist, the effective table has everything the badge renderer needs.
**Read `docs/r4-badge-surfaces.md` in full at this point** for the geometry,
placement-per-surface table, degradation ladder (L0 full badge → L1 dot → L2
nothing+coach-mark → L3 generic MIDI), and the measured SPI-budget numbers
(0.75ms/badge, 5.3ms worst-case tick — requirement 6 headroom confirmed). One
correction to make while there: R4's surface-census table cites
`pistomp/lcd340x240.py` for the footswitch strip — the file is
`pistomp/lcd320x240.py`; fix the typo when you copy any reference out of it.

Nothing in §1–6 depends on badge geometry, so there's no cost to deferring
this reading.

## 8. Escape hatches

Only one survives migration: the **NAM capture state machine**
(`pistomp/nam/panel.py`) — the `IDLE → CAPTURING → DONE|FAILED|ABORTED → IDLE`
transitions and their side effects on `routing.connect_monitor` /
`_engine.start` / `_engine.abort` stay imperative (widget `action=` lambdas
driving a real state machine, not a binding set). Everything else about NAM
becomes declarations:

- enc1 → NAV mirror, enc1-click/longclick → NAV click/longclick: `AliasEffect`
  rows (R1 #17–19).
- enc2/enc3 audio nudges in IDLE: `AudioCardEffect` rows (R1 #20–21).
- enc2/enc3 swallowed during CAPTURING/DONE/ABORTED: `enabled_when` predicates
  gating a `NoneEffect` row, rather than hand-written `if state == ...: return
  True` branches (R1 #22, #24; R2 §6.1's finding that this narrows the escape
  hatch to just the transitions, not the gating).

Nail the exact line-by-line split when you do this migration — it's
mechanical once the state-predicate mechanism exists, not a design question.

## 9. Build order

```
1. common/contexts.py — BindingDecl, Effect union, ControlRef, ContextRef,
   ContextStack, ContextLayer. Pure data + the resolve() chains (§1-3).
2. Footswitch-piercing guard wired into Modhandler.handle (§5), with its
   dedicated test.
3. VOLUME opt-in mechanism: override_volume registration check + visible
   on-screen state requirement (§4).
4. Migrate compressor and parametric EQ panels first (charter's choice —
   they exercise static + selection-dependent bindings and the densest
   screens). Each migration replaces on_event with declare_bindings();
   track against the R1 census table (declared / escape-hatched / remaining).
5. Controller.parameter -> effects-list / multi-binding support (§6.2),
   ControllerManager.bind becomes the table builder (§6.1), blend becomes a
   context (§6.3).
6. Read docs/r4-badge-surfaces.md; wire the badge renderer off the effective
   table (§7).
7. tests/v2/conftest.py v2_system fixture, built now that a real migrated
   panel exists to drive under it (charter requirement 2) — the
   failing-behavior inventory gathered here becomes the acceptance-test list.
8. Continue migrating remaining panels (gx_cabinet, tap_reverb, graphic EQ,
   multiband menu, NAM per §8) against the R1 checklist until every row is
   either declared or explicitly escape-hatched (requirement 4).
```

## 10. Acceptance gate (charter requirements, unchanged)

1. v2 parity — every custom panel fully NAV-operable.
2. v2 observable in CI — `v2_system` fixture (step 7 above).
3. NAV invariant enforced by a test, not convention (already true post-A1;
   keep it true).
4. Migration total — every R1 row declared or escape-hatched, no third
   category.
5. Badge honesty — badges render only from the effective table; shadowed/
   inactive bindings shown shadowed or not at all, never live.
6. Render budget holds — confirmed by R4's measurements (§7); re-verify if
   badge placement changes during implementation.
7. House rules: pyright zero, no `getattr`/`hasattr`, DAG dependencies,
   deliberate snapshot updates (fix real failures first).
