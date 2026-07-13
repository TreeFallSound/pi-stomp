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
`SelectionEditEffect`, `NoneEffect` (R2 §2.2). Each variant maps
1:1 to an effect kind found in the R1 census — no new kind should be needed
for existing panels; if one comes up mid-migration, that's a signal the
census missed a row.

**`AliasEffect` removed (deviates from R2 §2.2).** R2 originally specified an
`AliasEffect` (re-dispatch to a target control's own base behavior, e.g. "NAV
mirror") for exactly one row: NAM's Tweak1. Since no other panel ever needed
it, and NAM's Tweak1 is being swallowed rather than mirrored (see §8), the
whole variant — plus `fire()`'s case for it and `PanelOps.input_step` — was
deleted rather than built for a single now-unused call site. If a future
panel genuinely needs re-dispatch-as-another-control semantics, reintroduce
it then, informed by that panel's actual requirements rather than NAM's.

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

**Status: first slice landed (L0 badge only, two surfaces), revised after
first-pass review.** The first attempt prepended a Unicode circled-number
glyph (①②③) straight into the knob's label string. Rejected on review for
three reasons: (1) a badge for the *currently selected* control doesn't
belong on the control's own widget at all — it's transient context that
belongs in the panel's status bar, next to the value it's currently editing;
(2) prepending into a centred label string nudges the label to make room,
which is exactly the "in the flow" placement R4 explicitly rejected in favor
of the parameter-menu's out-of-flow left-margin badge; (3) the arc-label font
at 11pt renders the circled-digit glyph too small to read, and every surface
should share one legible size, not one sized to whatever font the label
happens to use.

**Golden rule established (second pass, after a live walkthrough of
gx_cabinet):** ① is special — every migrated panel binds enc1 to
`SelectionEditEffect` ("edit whatever is currently selected"), so ① belongs
**in the status bar only, shown persistently** whenever a selection exists,
never on the selected widget itself. This teaches the invariant ("enc1 always
edits your selection") the same way the main menu's brief top-left flash
teaches a selection change, except here it's persistent because the
association needs to be learned, not just confirmed. enc2/enc3 are the
opposite case in `gx_cabinet`/`tap_reverb`: both are **fixed** bindings
(`c_model`, `CLevel`/`decay`) that don't depend on what's selected, so they
badge the widget they're permanently bound to, not the status bar. The status
bar is reserved for enc2/enc3 only on panels where *those* are themselves
contextual/selection-dependent (parametric EQ's freq/Q-of-selected-band is
the one example so far, not yet migrated to badges).

Mechanism, reusing `uilib/glyphs/badge.py`'s `BadgeGlyph` (a fixed-size white
disc with a baked black character — the same glyph already used by
`Menu`/`TextWidget`'s out-of-flow left-margin badge, R4 §5) everywhere:
- **`Widget` itself** (`uilib/widget.py`) now hosts a generic
  `set_badge(BadgeGlyph | None)` / `_draw_corner_badge()`, called from
  `do_draw` after selection/outline. Default placement is the top-left
  corner. This is the answer to "can a widget join our hierarchy" — any
  widget gets a badge for free by calling `set_badge()`; no per-widget
  plumbing required. (`uilib.glyphs.badge` is imported under `TYPE_CHECKING`
  only in `widget.py` to avoid a real cycle: `uilib/glyphs/__init__.py`
  already imports `ArcDialWidget`, which imports `Widget` — `widget.py`
  importing `uilib.glyphs.badge` at module scope would import the whole
  `uilib.glyphs` package first and deadlock. Same pattern `_draw_selection`
  already uses for `RoundedRectGlyph`.)
- **`ArcDialWidget`** overrides `_draw_corner_badge` to place its badge
  centred on the ring's horizontal axis, on the opposite side from the label
  (bottom if `label_pos="top"`, and vice versa) — "the one other symmetric
  spot on the widget," not a corner, since the ring itself is centred.
- **`ModeSelectorWidget`** needed zero changes — it inherits the default
  left-edge (vertically centred) placement from `Widget` and just calls
  `set_badge()`.
- **`ReadoutBar`** (`plugins/layouts/readout_bar.py`) shadows the base
  `Widget.set_badge` with its own (stored as `_readout_badge` to avoid
  colliding with the base `_badge` field, which stays permanently `None` and
  inert here) — its badge tracks whichever text is currently displayed, so
  it's drawn immediately left of that text rather than in a fixed corner.

Applied to `gx_cabinet`/`tap_reverb` (identical three-row shape):
- **enc3/Volume** (fixed, e.g. `CLevel`/`decay`) — `BadgeGlyph` on the arc
  knob itself, set once at `build_widgets` time, opposite the label.
- **enc2** (fixed, `c_model`/`mode`) — `BadgeGlyph` on the mode selector
  itself, set once at `build_widgets` time, default left-edge placement.
- **enc1** (`SelectionEditEffect`) — `ReadoutBar.set_badge`, shown beside
  whatever readout text is current, for *every* selection state (an
  `ArcKnobWidget` or the `ModeSelectorWidget` alike — enc1 does something
  meaningful in both, so the badge's claim is true in both).

All three verified visually (cropped/zoomed snapshot PNGs), not just by
pyright/pytest: ① persists in the status bar across every selection state, ②
and ③ sit fixed on their respective widgets regardless of what's selected,
and nothing collides when a knob carries both its own fixed badge and the
selection ring simultaneously.

Deliberately out of scope for this slice, left as gaps:
- **No L1/L2/L3 degradation** (shadowed-dot, no-binding coach mark, generic
  MIDI badge) and no `enabled_when`/`ShadowState` read at all yet — this
  slice reads only the panel's own static `declare_bindings()` shape, not the
  resolver's shadow tagging. Both panels here happen to have every row
  always-`ACTIVE` (no `enabled_when`), so there was nothing to distinguish.
  NAM (§8), which does have real `enabled_when` shadowing, is the natural
  next target to force L1 into existence.
- **Other surfaces** (`Parameterdialog`, edit-in-place, main-panel plugin
  grid, multiband menu slots, NAM setup-view knobs) still unbadged. Each
  needs its own placement per §5.1's table; the mechanism generalizes to any
  of them directly, and the golden rule (① in the status bar only; fixed
  tweaks on their own widget) decides placement without further debate.

**Status: second slice landed — EQ readout strips (the worst-case density
panels R4 called out) and the badge mechanism itself unified.** Two threads:

1. **Badge mechanism unification.** Building the EQ badges surfaced a real
   footgun: `ReadoutBar` and a hand-copied `GraphicReadoutWidget` version each
   shadowed `Widget.set_badge()` with their own field (`_readout_badge`) to
   get text-relative positioning instead of the base's fixed-corner spot —
   documented as deliberate, but the *documentation* didn't stop a second
   copy from re-introducing the exact bug the first one was written to avoid:
   naming its shadow field `_badge` (the base class's own field), which made
   `do_draw()`'s automatic corner-badge paint fire *in addition to* the
   widget's own manual paste, rendering the glyph twice. Fixed by collapsing
   to one call site: `Widget.do_draw()` now calls a single `_draw_badge(ctx)`
   hook (renamed from `_draw_corner_badge`) unconditionally after `_draw()`;
   any widget needing custom placement overrides that hook directly instead
   of adding a second, parallel draw call. `ArcDialWidget` (already an
   overrider) just got renamed; `TextWidget` (the parameter-menu/footswitch
   row badge, pre-existing R4 work) and `ReadoutBar`/`GraphicReadoutWidget`
   were migrated onto the shared `_badge`/`set_badge()` storage, deleting
   their shadow fields entirely. All 1144 tests pass byte-identical — the
   unification is behavior-preserving, not a visual change.
2. **Graphic EQ** (`GraphicReadoutWidget`) gets a single ① badge, prepended
   to "Band X/Y" in the readout strip, shown whenever a band is selected
   (enc1 is its only live binding — enc2/enc3 are permanent `NoneEffect`s per
   the existing `declare_bindings()`) and hidden for chrome-button selection.
3. **Parametric EQ** (`ReadoutWidget`) is the first panel to exercise the
   golden rule's other half, flagged as an open gap in the first badge slice:
   a genuinely contextual enc2/enc3 (gain/freq/Q of the selected band are
   *all three* simultaneously live and selection-dependent — no other
   migrated panel has more than one). One widget, three badges at once,
   which doesn't fit the base class's single-slot `_badge`/`set_badge()` — so
   `ReadoutWidget` stores its own `dict[str, BadgeGlyph]` keyed by readout
   column and overrides `_draw_badge` to paint all three (①=gain, ②=freq,
   ③=Q), leaving the inherited single-slot field untouched and unused on
   this class, same non-collision pattern as before but now built on the one
   canonical hook instead of a second one. Each badge sits in its column's
   left gutter without shifting that column's fixed-position text (`name` is
   unbadged — it's the band's identity, not something an encoder edits).
   Badges show/hide together via `set_badged(bool)`, in lockstep with the
   panel's `on_event` guard that already governs whether these encoders are
   live for the current selection state. All snapshots regenerated and
   visually confirmed (band-selected: `②158 Hz　③Q 1.00　①disabled`;
   chrome-selected: no badges).

4. **Multiband menu** (`MultibandWindow`) gets a static ① badge on the
   window's title-bar text (`self.decorator.title`, a `TextWidget` — set once
   in `build_widgets()`). enc1 is a single, permanently-live
   `SelectionEditEffect` here and every slot resolves a real symbol (no
   per-selection toggling needed, unlike the EQ readouts), and the window has
   no persistent status-bar element to piggyback on the way gx_cabinet/
   tap_reverb do — the title strip, always visible and never repainted per
   selection, stands in for one.
5. **NAM setup view** (`pistomp/nam/panel.py`) gets ②/③ on the input-gain/
   headphone-volume knobs (`_knob_gain`/`_knob_vol`), set once at construction
   — both rows' `enabled_when` is `idle()` and the setup view is only ever
   shown in `IDLE` state (the capture view swaps the knobs out entirely), so
   a static badge is accurate for as long as it's visible. This one needed
   real debugging, not just wiring: the base `ArcDialWidget._draw_badge`
   places the badge on the ring's opposite side from the label, which is
   fine for gx_cabinet/tap_reverb's taller knob boxes but got clipped by
   NAM's tighter `_KNOB_H` — first at the bottom (badge painted past the
   box's bottom edge), then, after switching to a left-of-label placement
   instead, at the *top* (the label's own ink sits with zero headroom above
   the box's top edge by construction of `ArcDialWidget._cy()`'s clamp, and
   a 13px badge centred on a 10px-tall label line pokes ~1.5px above that).
   Fixed by giving `_KNOB_H` a few px of slack (114→124, comfortably clear
   of the `_BTN_Y` row below) and overriding `_draw_badge` on NAM's
   `KnobWidget` subclass specifically, rather than changing the shared
   `ArcDialWidget` default that gx_cabinet/tap_reverb already rely on.

**`Parameterdialog` and the parameter menu's tweak badges: done.** Both read a
new `tweak_badge_number(plugin, param)` helper (`pistomp/lcd320x240.py`),
mirroring `footswitch_badge_letter` but over the effective table's
`(ControlClass.ANALOG, EventKind.ROTATE)` rows instead of `FOOTSWITCH`/
`PRESS`. This is the *legacy* TTL/config binding path (`param.binding` →
`Hardware.controllers`) — the fallback `Modhandler._handle_encoder` uses when
no open custom panel's `declare_bindings()` claims the encoder first. TWEAK
rows themselves are always panel-scoped (never pedalboard-level), so this
ANALOG-class row is the *only* way a bare `Parameterdialog` or the generic
parameter menu (both reachable only for plugins without a `panel_cls`) can
ever show a live encoder binding. `Parameterdialog` gets a single top-left
badge (`_draw_badge` override, since the base `Widget` default — left-edge,
vertically centred — lands inside the bar graph); the parameter menu reuses
the row's existing single badge slot (`footswitch_badge_letter` or
`tweak_badge_number`, never both — `param.binding` names exactly one physical
controller, so the two are mutually exclusive per row). New helper
`_badge_letter(plugin, param)` picks whichever applies.

**Found and fixed a real framework bug along the way:** `ContainerWidget`
(`uilib/container.py`) — the base every `Panel`/`Dialog` inherits — has its
own `refresh()`/`do_draw()` paint paths that never called `_draw_badge()`.
Every prior badge consumer (`ArcDialWidget`, `ModeSelectorWidget`,
`ReadoutBar`, `TextWidget`) happened to be a plain `Widget`, so the gap was
unexercised until `Parameterdialog.set_badge()` (a `ContainerWidget`) painted
nothing. Fixed by adding the `_draw_badge()` call to all three of
`ContainerWidget`'s paint paths (virtual refresh, non-virtual refresh, the
dirty-rect rebuild inside `do_draw`), right after `_draw_selection()`, same
ordering as the base `Widget.do_draw()`. Verified inert everywhere else — all
1144 pre-existing snapshots stayed byte-identical; only the new
badge-carrying snapshots changed.

**Edit-in-place: not a badging gap, a missing feature.** Charter A4 ("click a
value widget to edit it directly, no dialog") isn't implemented anywhere in
the codebase — `Panel.input_event`/`Widget.input_event` have no edit-mode
state at all. There's nothing to badge until A4 itself gets built; revisit
then.

**Main-panel plugin grid: rejected, not deferred.** R4's table entry assumed
a free top-right gutter per tile (`60,2..72,12` in a 74×28 tile). The actual
rendered grid (`test_main_panel_snapshot/0.png`) shows tiles as solid-color
blocks with centred labels already spanning most of the tile width — no
reserved gutter exists, so a corner badge would collide with the label or
float on bare fill with no anchor. The tile is too tight for that to be worth forcing in footswitches or analog inputs bound to its parameters, but we should consider how we want to show this in the future as it helps someone learn the pedalboard. Need to think through where an overall "MIDI Map" would live.

**L1/L2/L3 degradation ladder: rejected, not deferred.** Reconsidered after a
walkthrough and dropped, not just postponed:
- L1 (shadowed → dot): the shadowing context (blend, a modal) occupies the
  screen while it's active, so there's no stale badge for a user to be
  misled by — the case the dot was meant to solve doesn't arise in practice.
- L2 (no binding → blank, first-time coach mark): blank is already the
  correct, unambiguous default for "nothing bound here." No change needed.
- L3 (unnamed external MIDI → generic disc): legitimate future need, but
  premature now — pi-stomp has no defined MIDI-flow map across the whole
  ecosystem yet, so there's no ground truth to render honestly against.
  Revisit once that map exists.

More basic functionality gaps outrank this work; don't pick the ladder back
up without a concrete trigger (e.g. the MIDI-flow map landing for L3).

## 8. Escape hatches

Only one survives migration: the **NAM capture state machine**
(`pistomp/nam/panel.py`) — the `IDLE → CAPTURING → DONE|FAILED|ABORTED → IDLE`
transitions and their side effects on `routing.connect_monitor` /
`_engine.start` / `_engine.abort` stay imperative (widget `action=` lambdas
driving a real state machine, not a binding set). Everything else about NAM
becomes declarations:

- enc1 (rotation + click + longclick) is swallowed outright — a `NoneEffect`
  row, consumed, no-op (R1 #17–19). **Deviates from the original plan**,
  which had enc1 mirror the NAV encoder's own behavior via an `AliasEffect`.
  Simpler: Tweak1 does nothing on the NAM screen; NAV is still there for
  navigation on any board that has both. Not worth a whole `Effect` variant
  for one row.
- enc2/enc3 audio nudges in IDLE: `AudioCardEffect` rows (R1 #20–21).
  `AudioCardEffect` fires through the *same* `ops.edit_symbol(symbol,
  rotations)` call as `ParamEffect` (merged into one `fire()` match arm) —
  CAPTURE_VOLUME/MASTER aren't LV2 params, but "rotations → commit" is the
  identical shape, and no migrated panel's `edit_symbol` ever consulted
  `event.multiplier` anyway, so there was nothing left to justify a separate
  `PanelOps.audio_nudge` member.
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
2. **Deferred: footswitch-piercing guard.** §5's guard and `Panel.declare_bindings()`
   were prototyped and reverted — no panel claims a footswitch today, so the
   guard has no caller and would be dead code. Build it when the first panel
   in step 4/8 actually needs to opt in to a footswitch row, not before.
3. VOLUME opt-in mechanism: override_volume registration check + visible
   on-screen state requirement (§4).
4. Migrate compressor and parametric EQ panels first (charter's choice —
   they exercise static + selection-dependent bindings and the densest
   screens). Each migration replaces on_event with declare_bindings();
   track against the R1 census table (declared / escape-hatched / remaining).

   **Scoping decision (this slice only, revisit at step 5):** don't wire
   `ContextStack` into `PanelStack` push/pop yet. Until step 5,
   `ControllerManager` still owns pedalboard-level TWEAK bindings the old way,
   so a panel is the only context ever in play while it's open — there is no
   cross-context shadowing to resolve, and building the full stack now would
   be scaffolding with no caller (same mistake as the footswitch guard in
   step 2). Instead:
   - `Panel.declare_bindings()` returns this panel's own rows; a
     `resolve_local(rows, control, event_kind)` helper in
     `pistomp/input/dispatch.py` walks just that list (reusing
     `ContextStack`'s single-layer logic, not duplicating it) and returns the
     first row whose `enabled_when` is true — same semantics as worked
     example (g) (two rows, same key, mutually exclusive predicates, e.g.
     parametric EQ's gain/q guards).
   - `fire(decl, ops, event)` executes `ParamEffect`/`SelectionEditEffect` via
     `ops.edit_symbol(symbol, rotations)` (panel-owned value math — see
     below) and `NoneEffect` (consume, no-op).
   - `ops: PanelOps` is a small structural `Protocol` (`sel_ref`,
     `edit_symbol`), not the concrete `Panel` type —
     `pistomp/input/` must not import `uilib.Panel` back (`uilib` already
     imports `pistomp.input.event`/`sink`; importing the other direction
     would cycle).
   - **Schema addition: `ParamRole`** (`common/param_roles.py`) — GENERIC,
     GAIN_DB (additive, fixed dB step), FREQUENCY_HZ (multiplicative,
     equal-tempered step), Q_FACTOR (additive, fixed step). One vocabulary
     used two ways: (1) `SelectionEditEffect.role` — which symbol to pull off
     `sel_ref` (`sel_ref.symbol_for(role)`; a compressor arc returns the same
     symbol for any role, an EQ band selection returns a different symbol per
     role); (2) `PluginCustomization.param_roles: dict[str, ParamRole]` —
     which step math applies to a resolved symbol, a classification
     supplementing the LV2 port's range/type ground truth (the same seam
     `panel_cls`/`tile_border`/etc. already use). Originally built as two
     separate mechanisms (an ad hoc `attr` string on the effect, a separate
     enum for step math) and collapsed into one after review — they were the
     same classification spelled two ways. `PluginPanel.edit_symbol` is the
     one place that reads `param_roles`; a panel overrides it only to add a
     widget refresh or, for a per-band lookup like parametric EQ, to resolve
     which band field a symbol belongs to before delegating to
     `common.param_roles.edit_value`.
   - The VOLUME opt-in guard (step 3) got its first real exercise here:
     compressor's enc-3 `rat` row is declared with `control.cls =
     ControlClass.VOLUME` and the row's own `context=ContextRef(
     override_volume=True)`, per §4's decision that Tweak3/Volume stays
     freely assignable. This also fixed a bug in the guard itself: it must
     check the *row's* declared `context`, not the containing layer's `ref`
     — `resolve_local` rebuilds an ad hoc layer from already-authored rows on
     every call, so a shared layer-level flag can't carry per-row intent.
   - **Schema gap found, not yet generalized:** parametric EQ's Tweak3 (Q)
     must fall through to the volume encoder when no band is selected (chrome
     focused), while Tweak1/2 (gain/freq) stay silently absorbed — a
     per-row, state-conditional *consume* the schema only expresses via
     `enabled_when` on the *effect* row, not on whether the event is
     consumed at all when no row matches. Handled with a small imperative
     guard in `ParametricEqPanel.on_event` before falling into declarative
     resolution, documented inline. Revisit if a third panel needs the same
     shape — that would be the signal to add real schema support rather than
     a third copy of the guard.
   - Panels never declare `ANALOG` rows (§4.2: chain is `BLEND → PEDALBOARD`
     only) — enforced by absence, not by a check in this slice.

   **Status: compressor and parametric EQ migrated, all tests + pyright
   green.** Remaining census panels (gx_cabinet, tap_reverb, graphic EQ,
   multiband menu, NAM) are step 8.
5. Controller.parameter -> effects-list / multi-binding support (§6.2),
   ControllerManager.bind becomes the table builder (§6.1), blend becomes a
   context (§6.3).

   **Status: §6.1 (table builder) landed as an additive slice; §6.2/§6.3
   deferred.** `ControlRef.id` widened to `int | str` — panel rows keep the
   `1-3` tweak/volume slot ints, pedalboard-level ANALOG/FOOTSWITCH rows use
   the same `"channel:CC"` string already keying `Hardware.controllers`, so
   one `ControlRef` shape covers both without a second identity field.
   `ControllerManager.bind` now builds `self.effective_table` (a
   `ContextStack` with one `PEDALBOARD` layer) alongside the legacy
   `current.analog_controllers` / `controller.parameter` writes — same
   traversal, no behavior change, nothing yet reads the table. The one new
   behavior: a TTL `param.binding` with no matching physical controller
   (previously silently dropped via `if controller is None: continue`) now
   also appends a `BindingDecl` tagged `ShadowState.ORPHANED` (test:
   `test_orphaned_ttl_binding_recorded_in_effective_table`).

   **§6.3 (blend as a context) also landed, in the same slice.** Added
   `BlendEffect(input_controller: object)` to the closed union — a typed
   reference to the live `InputController`, not a string-keyed
   `CallbackEffect` lookup, since it's one specific stateful attachment, not
   a generic named action. `Modhandler` now owns a `_blend_layer:
   ContextLayer` (`ContextKind.BLEND`), rebuilt by `_rebuild_blend_layer()`
   after every `activate()`/`deactivate()`/failed-activate from
   `_handle_blend_mode_snapshot_change`, keyed by the attached controller's
   own `f"{midi_channel}:{midi_CC}"` — the same identity space as pedalboard
   rows (blend's config `input_id` is a display-position int in a *different*
   space; the row is built from the live attached `Controller` object after
   `attach_to_input`, not straight from config). `Modhandler.handle`'s old
   `active_blend_mode.intercept(event)` short-circuit is replaced by
   `_fire_blend_row`, which resolves `ContextStack(layers=[*effective_table.
   layers, blend_layer])` and fires only if the winner is a `BlendEffect` —
   a pedalboard-only control (no blend row) falls through to legacy dispatch
   unchanged. Because `ControlClass.ANALOG`'s chain is `(BLEND, PEDALBOARD)`
   (`common/contexts.py` `_CHAINS`), a blend row now correctly wins over a
   co-located pedalboard TTL row and tags it `SHADOWED` via the resolver's
   normal side effect — fixing R3 §7d (the pedalboard row no longer goes
   silent with no trace). `BlendMode.intercept()` itself is untouched and
   still unit-tested directly (`tests/input_router/test_blend_interception.
   py`); the new integration coverage is
   `tests/input_router/test_blend_context_shadowing.py`.

   **Multi-binding cache (§6.2) still deferred** — even with §6.3 landed, no
   code path produces two genuinely `ACTIVE` `ParamEffect` rows on the same
   control at once (the blend/pedalboard collision above is a consumption
   decision made by `_fire_blend_row`, not a change to `Controller.
   parameter`; the pedalboard row's controller keeps its plugin binding for
   the LED/display reconcile path regardless of blend). Revisit only if a
   real two-plugins-share-one-CC case surfaces (R3 §7e).
6. Read docs/r4-badge-surfaces.md; wire the badge renderer off the effective
   table (§7).
7. tests/v2/conftest.py v2_system fixture, built now that a real migrated
   panel exists to drive under it (charter requirement 2) — the
   failing-behavior inventory gathered here becomes the acceptance-test list.
8. Continue migrating remaining panels (gx_cabinet, tap_reverb, graphic EQ,
   multiband menu, NAM per §8) against the R1 checklist until every row is
   either declared or explicitly escape-hatched (requirement 4).

   **Status: gx_cabinet migrated** (`plugins/gx_cabinet/panel.py`) — enc1 is
   `SelectionEditEffect()` (resolved via the focused `ArcKnobWidget`'s or
   `ModeSelectorWidget`'s new `symbol_for`), enc2 is a fixed `ParamEffect`
   on `c_model` (cycles the cab model regardless of focus, matching the old
   `on_event`), enc3 is `CLevel` on a `VOLUME`/`override_volume=True` row
   (chassis Tweak3/Volume, same opt-in shape as compressor's `rat`). Step
   math for `CLevel`/`CBass`/`CTreble` doesn't fit an existing `ParamRole`
   (fixed additive steps of 0.05/0.4, not GAIN_DB's 0.5 or Q_FACTOR's 0.05
   with different range), so `edit_symbol` is overridden to apply the
   panel's own step table and delegates to `super().edit_symbol` only for
   `c_model`-shaped GENERIC editing it doesn't otherwise handle. All 8
   snapshot sagas in `tests/v3/test_gx_cabinet_panel.py` pass byte-identical,
   no snapshot regeneration needed — the migration is behavior-preserving.

   **tap_reverb migrated** (`plugins/tap_reverb/panel.py`) — same three-row
   shape as gx_cabinet: enc1 `SelectionEditEffect()`, enc2 a fixed `ParamEffect`
   on `mode`, enc3 `decay` on a `VOLUME`/`override_volume=True` row (chassis
   Tweak3/Volume). `decay`/`drylevel`/`wetlevel` steps (100ms / 0.8dB) don't
   fit an existing `ParamRole`, so `edit_symbol` is overridden the same way —
   panel step table first, `super().edit_symbol` only as the `mode`-shaped
   fallback path is unreachable here since `mode` is handled explicitly too
   (kept symmetric with gx_cabinet's `c_model` branch for consistency). The
   old `on_event`/`_edit_knob`/`_cycle_mode` trio (each rebuilding
   `TapReverbState` by hand) collapsed into `edit_symbol` +
   `_sync_after_edit`, matching gx_cabinet's post-migration shape. All 11
   snapshot sagas in `tests/v3/test_tap_reverb_panel.py` pass byte-identical.

   **Graphic EQ migrated** (`plugins/eq/graphic.py`) — enc1 is
   `SelectionEditEffect(role=GAIN_DB)` (`GraphicBandSelectable.symbol_for`
   returns the focused band's `gain_sym`, `None` for band-less), enc2/enc3 are
   declared `NoneEffect()` rows (always-consumed no-ops — graphic EQ bands have
   no freq/Q to tweak, unlike parametric). This is the **second** panel
   needing the "no band selected → Tweak3 falls through, others absorbed"
   guard the plan flagged as a signal to generalize at a third occurrence
   (§9 step 4's schema-gap note) — kept as a second copy of the same small
   `on_event` guard for now, one occurrence short of that threshold.
   `edit_symbol` overrides to route through `_replace_band`/`_bar_widget`
   sync, same shape as gx_cabinet/tap_reverb/parametric. All 7 snapshot sagas
   in `tests/v3/test_graphic_eq_panel.py` pass byte-identical.
   `graphiceq`/`barkgraphiceq` subclasses inherit unchanged.

   **Multiband menu migrated** (`plugins/multiband_menu/__init__.py`) — the
   shared `MultibandWindow` base (arc-ring grid, one `ParamSlotWidget` per
   band) gets a single `declare_bindings()`/`edit_symbol` pair covering all
   seven subclasses at once (mdamultiband, mdabandisto, three_band_eq,
   three_band_splitter, caps_noisegate, capseq10x2, system_compressor) since
   none override `on_event`. enc1 is `SelectionEditEffect()` (generic role —
   `ParamSlotWidget.symbol_for` returns `self.slot.symbol` unconditionally,
   same shape as `ArcKnobWidget`); enc2/enc3 have no declared rows (unchanged:
   unconsumed, falls through). No guard needed — unlike the EQ panels, every
   selectable here already resolves to a real symbol, and a chrome-button
   selection silently absorbing enc1 (rather than falling through) matches
   the precedent already accepted in gx_cabinet/tap_reverb. `edit_symbol`
   delegates to the existing `ParamSlotWidget.on_encoder_rotation` (which
   already did the clamp + widget refresh) rather than duplicating its step
   math. `tests/v3/test_caps_noisegate_menu.py` (the one exercised subclass
   with a snapshot suite) passes byte-identical.

   **NAM migrated** (`pistomp/nam/panel.py`) — the state-machine transitions
   stay imperative per §8; everything else is `declare_bindings()`. This is
   the first real use of `enabled_when` in production code (previously only
   exercised by `tests/test_contexts.py` — parametric EQ's "no band selected"
   guard turned out to be hand-written `on_event` code, not an `enabled_when`
   row, despite §9 step 4 describing it that way). Three states per control
   for enc2/enc3 need three different rows at the same `(control, event_kind)`
   key: `AudioCardEffect` enabled in IDLE, `NoneEffect` enabled in
   CAPTURING/DONE/ABORTED, and — the interesting case — *neither* enabled in
   FAILED, so `resolve_local` returns `None` and `on_event` falls through
   unconsumed, exactly reproducing the old `if state == FAILED: return False`
   passthrough to the vanilla parameter overlay. See the appendix below on
   what this pattern implies architecturally. `NamCapturePanel` isn't a
   `PluginPanel` (no LV2 plugin backing it), so it implements `declare_bindings`
   /`edit_symbol` itself rather than inheriting them, and calls
   `resolve_local`/`fire` directly from its own `on_event`.

   Census complete: every panel from R1 is now either declared
   (`declare_bindings`) or the one accepted escape hatch (NAM's state
   machine, §8).
```

### Appendix: NAM's `enabled_when` rows are a sub-panel smell

Noted during NAM's migration (step 8), not acted on — logged so it isn't
re-discovered from scratch later.

NAM's enc2/enc3 rows need three mutually-exclusive `enabled_when` predicates
per control because the same physical control means something different in
IDLE vs CAPTURING/DONE/ABORTED vs FAILED. But `NamCapturePanel` already models
that exact split internally: `_switch_to_capture_view()`/
`_switch_to_setup_view()` swap widget visibility and rebuild `sel_list` for
"setup mode" vs "capture mode" — all inside one `Panel` instance, never
pushed/popped on the `PanelStack`. The `enabled_when` predicates are a second,
parallel place tracking the same mode.

The architecturally cleaner shape: split `NamCapturePanel` into real
sub-panels (e.g. an idle/setup panel and a capturing panel) pushed/popped
together with the existing view switch. Each would declare its rows
unconditionally — no `enabled_when` anywhere, because `declare_bindings()` is
re-evaluated fresh per panel per §2's "called once at attach-time" model.

Not done now because it means restructuring NAM's view-switching mechanism
itself, which is a materially bigger change than any other panel migration in
this plan, and NAM's state machine is already the one deliberate exception
carved out in §8. Revisit if `enabled_when` grows a second real use case
elsewhere — two independent occurrences of "same control, mode-dependent
behavior inside one panel" would be the signal that the sub-panel refactor is
worth doing generally, not just for NAM.

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
