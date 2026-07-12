# Input Contexts: Charter

**Audience:** the agent implementing this work. This document is the contract:
it states where the codebase stands, the architecture that has been *decided*
(not up for re-litigation), the requirements the result must meet, and the
research reports that are **mandatory before any production coding beyond the
baseline fix in A1**.

**Goal.** A declarative, hierarchical input-binding system ("contexts") on top
of the unified input-sink transport, rendered to the user as binding badges
(①②③ for tweak encoders, (A)–(D) for footswitches), with a NAV-complete
editing model so every panel is fully operable on v2 hardware (single NAV
encoder, no tweak encoders).

---

## Where the codebase stands

- **Branch:** `refactor/input-sink-transport`, child of `prerelease-for-v2`
  (git-town lineage is set). Commit `0b66e297` is a clean cherry-pick of
  `f85ebd87` from the superseded `refactor/full-input-sink` branch. It is the
  **transport layer**: one typed event stream through the `InputSink` cascade;
  the legacy `enc_step`/`enc_sw`/`universal_encoder_*` side channel is
  deleted; tests dispatch real events via `tests/v3/nav_helpers.py`.
- **Known defect in that commit, fixed by A1 below:** `Panel.handle` offers
  every event — NAV included — to `on_event()` first, and its docstring
  advertises repurposing NAV as a feature. This is the opposite of the decided
  architecture and must be fixed before anything is built on top.
- The old branch `refactor/full-input-sink` (local and `origin`) is
  superseded. Delete it only after the test suite passes on this branch.

---

## Decided architecture

These are decisions, not questions. Research reports may inform *how* they are
built, never *whether*.

### A1. NAV is constitutionally unhijackable — first task, do this before anything else

pi-Stomp is friendly because NAV's **vocabulary** is invariant: rotate always
operates on the highlighted thing, click always confirms it, longpress is
always the context action on it. NAV's *effect* is contextual, but only ever
through the selection model's sanctioned override points (`input_step`, the
selected widget's `input_event`) — never by a panel consuming raw NAV events.

Required change, to be **amended into commit `0b66e297`**:

1. In `uilib/panel.py`, reorder `Panel.handle()` so NAV `EncoderEvent`/
   `SwitchEvent`s (matched on `controller.type == Token.NAV`) are dispatched
   directly to the base selection machinery **before** `on_event()` is
   consulted. `on_event()` must never receive a NAV event. The existing
   tweak/volume `PRESS` → `InputEvent.CLICK` fallback stays *after*
   `on_event()`, unchanged.
2. Rewrite the docstrings that advertise the anti-feature: `Panel.handle`,
   `Panel.on_event` (both in `uilib/panel.py`), and `PluginPanel.on_event` +
   subclass-checklist item 4 in `plugins/base.py`. They must state the
   invariant: panels drive their own (non-NAV) controls in `on_event`; NAV is
   owned by the base and shaped only through the selection model.
3. No current panel consumes NAV in `on_event` (all filter on encoder ids
   1–3; the NAM panel *mirrors* tweak1 onto NAV semantics, which is fine), so
   this is behavior-preserving. Verify with the full suite.
4. Amend with this commit message:

   ```
   Input sink transport: one event stream, NAV owned by the base panel

   Retire the legacy enc_step/enc_sw/universal_encoder_* side channel so every
   control flows through the typed InputSink cascade, and tests dispatch real
   events through handler.handle. NAV events are dispatched by the base Panel
   directly to the selection machinery: panels shape what NAV operates on
   (selection contents, input_step overrides) but can never consume raw NAV
   events. on_event() is the escape hatch for a panel's own non-NAV controls.

   (cherry picked from commit f85ebd876ee908a9758080a78a4c6a1bde14e1c6)
   ```

Verification: `uv run pytest` green, pyright zero. Then delete
`refactor/full-input-sink` locally and on origin.

### A2. `on_event` is a modal escape hatch, nothing more

The long-term shape: bindings are *declared* (see R2) and resolved by the
base; `on_event` survives only for genuinely modal panels that are state
machines, not binding sets (the NAM capture flow is the canonical example).
Every migration that moves a panel from imperative `on_event` code to a
declaration is a win; new panels must not reach for `on_event` when a
declaration would do.

### A3. Control-class policy table

The context stack does not apply to all controls uniformly. Above the stack
sits a fixed policy per control class:

| Control class | Bindable by contexts? | Policy |
|---|---|---|
| NAV (rotation + button) | **Never.** Axiom, not policy. | The meta-control that operates the system. Corollary: NAV needs no badge — the selection highlight *is* its badge. |
| Footswitches | Yes, but **pierce panel contexts by default**. | Performance controls: a player stomps without looking. Panel-level shadowing is explicit opt-in and must carry unmistakable on-screen state. Enforced at the handler cascade (route footswitch `SwitchEvent`s around the LCD/panel layer unless a context has opted in), not by convention. |
| Tweak encoders (v3) | Yes, freely, per context. | This is what the stack is for. |
| Pots / expression (v2) | Pedalboard-scoped only. | Never borrowed by panels: absolute-position controls would need value-jump or invisible pickup modes. Pickup mode is rejected for now. |

### A4. NAV-complete edit-in-place (the v2 baseline)

Every panel must be fully operable with NAV alone. Tweak encoders are labeled
accelerators onto the same model, never the only path. The interaction model,
implemented **once at the base `Panel` level** so all panels inherit it:

- **Rotate** = move selection (existing behavior).
- **Click on a value widget** = enter *edit mode* on it: visible state change
  (selection ring treatment + value styling), rotation now edits the value
  through the same `ParameterSteps` grid the tweak encoders and
  `Parameterdialog` use (grid parity is already solved — reuse it, including
  the external-change resync logic in `Parameterdialog`).
- **Click again or timeout** = exit edit mode back to selection.
- **Longpress** = context action on the selected widget (e.g. reset symbol —
  already the convention in `ArcSelectable`).

Mechanism: an `edit_target` on `Panel` — when set, `input_step` routes detents
to that widget instead of `_step_sel`, and CLICK toggles it. Per-widget CLICK
semantics: value widgets enter edit; action buttons fire; modal panels own
their flow. The known offender to fix: `ArcSelectable.input_event` swallows
`CLICK` and does nothing (`plugins/layouts/arc_column.py`) — it must enter
edit mode. Custom panels edit in place (their live visualization is the
point; don't cover it with a dialog); the standard parameter-list flow keeps
`Parameterdialog`.

### A5. Bypass as a row; badges as a view of one binding table

- `:bypass` is promoted from chrome button to a parameter row. It *is* a
  parameter in the MOD protocol; the row treatment restores that, gives
  NAV-only users bypass access through the same select→click vocabulary, and
  gives footswitch badges a natural anchor.
- Badges (①②③, (A)–(D)) are **one renderer over one effective binding
  table**. The handler is the single authority that owns the merged view
  (pedalboard TTL MIDI-learn + config overlay + context declarations); the
  LCD renders *from* it and never computes its own idea of what's bound.
  Never render a binding that won't fire. Bindings we cannot name (external
  controllers on the same CC space) get a generic MIDI badge, not a guess.

---

## Requirements

The implementation is done when all of these hold:

1. **v2 parity.** Every custom panel is fully operable on v2 hardware
   (NAV-only). No panel assumes encoder ids 1–3 exist.
2. **v2 is observable in CI.** A `v2_system` fixture in `tests/v2/conftest.py`
   analogous to `v3_system` (CLAUDE.md prescribes the shape; today only the
   system menu is covered). Every custom panel is driven under it. The
   failing-behavior inventory gathered while building it becomes the
   acceptance-test list.
3. **NAV invariant is enforced, not conventional.** No code path allows a
   panel to consume raw NAV events; a test proves it.
4. **Migration is total.** Every input→effect pathway found in the R1 census
   ends up either expressed as a declaration or explicitly listed as an
   `on_event` escape hatch. No third category.
5. **Badge honesty.** Badges render only from the handler's effective binding
   table; a shadowed or inactive binding is either shown in its shadowed state
   or not shown, never shown as live.
6. **Render budget holds.** Badge paints and edit-mode state changes stay
   within the dirty-rect/SPI budget on the 10ms tick (R4 measures this).
7. House rules: pyright zero, no `getattr`/`hasattr`, dependencies form a DAG,
   LCD snapshot baselines regenerated deliberately (fix real failures first,
   then `--snapshot-update`).

---

## Research reports — mandatory before production coding

Beyond the A1 baseline fix, **no production code is written until these four
reports are accepted.** Spike/prototype code produced during research is
disposable by definition: never merged, only its findings are. Each report is
1–3 pages: findings, evidence, recommendation. A report that kills part of a
plan is a successful report.

### R1 — Binding census

**Unknown.** The complete inventory of input→effect pathways across v2 and
v3, each classified: static pedalboard-scoped (footswitch → CC), static
panel-scoped (compressor enc2 → `thr`), selection-dependent (compressor enc1
→ selected arc), or modal/imperative (NAM capture).

**Method.** Audit every `on_event` override (`plugins/`, `pistomp/nam/`,
`pistomp/tuner/`); every branch of `Modhandler.handle`/`_handle_switch`/
`_handle_encoder`; footswitch action configs and longpress chord groups
(`FootswitchChords`); blend-mode input claims; `external_midi` routing; and
every config key that creates or modifies a binding
(`setup/config_templates/`, `pistomp/config.py`). Record input, effect, scope,
and today's shadowing behavior for each.

**Exit.** A table with zero "unknown" rows, each row classified *declarable*
or *escape hatch*; an explicit statement of which pathways exist on v2 and
which v3 pathways have no v2 equivalent. This table is later consumed as the
migration checklist (requirement 4).

### R2 — Declaration schema and precedence

**Unknown.** The vocabulary of a binding declaration and the precedence rules
of the context stack, *given* the A3 control-class table as fixed input (NAV
exclusion is an axiom, not a question). Open: how a selection-dependent
binding stays data-like enough for the badge renderer; whether a context can
express "consume but do nothing"; whether precedence is strict stack order or
per-control-class; where exactly the footswitch-piercing rule is enforced in
the cascade.

**Method.** Express every *declarable* row of the R1 census in a candidate
schema, on paper, iterating until 100% express or are consciously
reclassified as escape hatches. Prior-art study: **mod-ui's "addressings"
model** (its existing hardware-actuator binding concept — nowhere in our code
today; decide mirror / interop / deliberate divergence) plus one keymap-style
precedence system for shadowing semantics.

**Exit.** Schema + precedence spec that round-trips the census; the
footswitch-piercing rule written as a testable statement and walked against
every `SwitchEvent` pathway; a named list of escape hatches with the reason
each cannot be data.

**Depends on:** R1 (hard), R3 (merge semantics must be representable).

### R3 — Binding truth and reconciliation

**Unknown.** Where binding truth lives today and what happens on collision.
How TTL MIDI-learn bindings parsed by LILV map onto
`controllers["{channel}:{CC}"]`; what happens when the config overlay and a
plugin's MIDI binding target the same CC; what we can honestly know about
external controllers sharing the CC space; whether the LCD currently derives
any independent idea of what's bound (drift risk).

**Method.** Trace `modalapi/pedalboard.py` (TTL parse),
`ControllerManager.bind`, `Hardware.reinit` overlay, and `external_midi`
resolution end to end. On-device: MIDI-learn a parameter from MOD-UI, inspect
the TTL, observe what pi-Stomp binds; construct a deliberate CC collision and
record behavior. Enumerate the collision matrix (config vs TTL vs context vs
blend), current and desired behavior per cell.

**Exit.** A data-flow document naming the handler as (or correcting) the
single authority, the merge rules, the collision matrix, and the "what we
badge when we don't know what's on the other end" rule.

### R4 — Badge surfaces, space budget, and degradation

**Unknown.** (A) every surface where a contextual binding must be shown, (B)
whether there is room at 320×240, (C) the degradation policy when there
isn't. Surfaces: parameter-list menu with `:bypass` as a row,
`Parameterdialog`, the edit-in-place state, every custom panel (worst cases:
10-band graphic EQ, dense parametric EQ), the main panel's footswitch strip.
Also: render cost of badge repaints against the SPI budget.

**Method.** Screenshot census via the existing snapshot-test harness,
annotating candidate positions and free pixels. Static mockups on the two
worst-case panels; verify physical-position correspondence (badge nearest the
actual encoder/footswitch). Measure incremental dirty-rect cost of a badge
repaint using the SPI-timing tests as the yardstick.

**Exit.** Badge spec (geometry, placement, physical-correspondence rule), a
degradation ladder (full badge → dot/tick → nothing + one-time coach mark,
with the coach-mark counter in `settings.yml`), and a measured statement that
requirement 6 holds.

---

## Sequencing

```
A1 (baseline fix, immediate — the one coding task exempt from research gating)
   │
R1 (census) ─────────► R2 (schema & precedence)
R3 (truth/merge) ────►
R4 (badges/space)      — parallel, independent
   │
Implementation plan (written only after R1–R4 accepted; consumes them:
   R2 → core abstraction, R3 → authority/merge design, R4 → UI spec,
   R1 → migration checklist = the mechanical definition of done)
   │
Build, migrating panel by panel (compressor and parametric EQ first — they
exercise static + selection-dependent bindings and the densest screens),
with the R1 table tracking declared / escape-hatched / remaining.
```

## Order of operations for the implementing agent

1. Apply A1 (reorder + docstrings), amend `0b66e297` with the prescribed
   message, run `uv run pytest` and pyright, then delete
   `refactor/full-input-sink` (local + origin).
2. Produce R1 and R3 (parallelizable), then R2; R4 anytime.
3. Write the implementation plan from the accepted reports; get it reviewed
   before coding.
4. Build to the Requirements list; it is the acceptance gate.
