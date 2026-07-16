# Input dispatch

Every hardware input — footswitch, encoder, knob, expression pedal — flows through one path, identical across hardware versions. A control reads its own pins, advances its own state, packages what happened into an immutable event, and hands that event to a single sink. There is no `InputRouter` class and no global stack: the "router" is just the `sink` field every controller inherits, plus whatever code each sink writes inside `handle`.

## Controllers are sources, sinks are actors

A `Controller` (`controller.py`) owns one raw detector — an `Encoder`, `GpioSwitch`, `AnalogSwitch`, or ADC channel — and a `sink: InputSink`. On each 10ms tick `poll_hw()` reads the detector, packages what physically happened into an event, and calls `self.sink.handle(event)`. The event reports a **completed physical action, not an instruction** — a pot that reached ADC value N, an encoder that turned +3 detents.

**A controller may own state that is intrinsically its own** — a pot's ADC reading, an encoder's detent count and timing — **but never a copy of a value that belongs to something else** (a parameter, blend's sweep position, a menu selection). That is the owner's to hold and the owner's to integrate. So a pot reports an absolute `midi_value` (its reading *is* its own fact), but an encoder reports only a **delta**. The one value an encoder does own is the unbound-CC fallback (below) — it has no owner, so it keeps its own accumulator.

An `InputSink` (`sink.py`) is one abstract method, `handle(event) -> bool`. `True` means "fully handled; the controller does nothing further." `False` is informational — there is no automatic forwarding, no framework. Sinks compose by writing the forwarding they want, in plain code.

The detectors underneath a controller (`Encoder.read_rotary()`, the GPIO/ADC switch callbacks) only sense raw edges and rotation. They never call `sink.handle` themselves — the owning controller builds the event.

## Events

Three immutable dataclasses (`event.py`), all carrying their source `controller`; sinks discriminate by `isinstance` / `match`:

* `EncoderEvent` — `rotations` this tick and the speed `multiplier`. A delta, not a value; the owner integrates it.
* `AnalogEvent` — `raw_value` (ADC) and the already-converted `midi_value`.
* `SwitchEvent` — `kind` (`PRESS` | `LONGPRESS`) and a `timestamp`.

There is no `consumed` field; that's the return of `handle`. There is no `RELEASE` kind: GPIO footswitches fire only on short-press-release or long-press, so a completed short press *is* `PRESS` — the user-meaningful event. `SwitchEvent.timestamp` is the `time.monotonic()` captured at the moment of detection (the GPIO interrupt, the ADC press), threaded all the way through to tap-tempo stamping so timing reflects the press, not when the handler got around to it.

## The handler is the sink

For every controller the sink is the handler — `Modhandler` — wired once by `Hardware.register_sink(self)`. Its `handle` is a fixed cascade: ask the **LCD** first (so an open panel can intercept inputs for the encoder it cares about), then the active **blend mode**, then run the handler's own logic by event type — write the local parameter value (so reactive observers repaint), display the parameter dialog, and emit MIDI.

Push/pop semantics live on the LCD, next to the only thing that needs them: a panel pushes itself when it opens and pops when it closes, and the LCD's `handle` walks that stack top-down. Blend mode likewise intercepts at the handler instead of hijacking a controller callback — `intercept(event)` reads the source controller's normalized position and sends its diff map.

Encoders are split to keep this clean: `Encoder` is the pure quadrature decoder, `EncoderController` is the `Controller` that owns it plus the quantizer and the absorbed push-button. The nav encoder's button is not a standalone switch — it lives inside its controller and dispatches a `SwitchEvent` like any other. Footswitch chords (longpress groups) are the one piece of genuinely cross-controller, timing-deferred state, so they live in `footswitch_chords.py` as a handler-owned helper rather than a sink: `observe()` records a press, `tick()` resolves the 400ms window once per poll and names the callbacks that fired.

## What fires: declared bindings, resolved by precedence

Handler logic used to decide "what does this control do" with per-panel `if`
chains inside `on_event`. That worked until the same physical control could
mean different things depending on what's open (a panel, blend mode, the bare
pedalboard) — nothing could answer "what's actually bound right now" without
re-running that code, which is also what made on-screen binding badges
impossible to render honestly. So what a control does is now **declared
data**, resolved by a fixed per-`ControlClass` precedence chain, and the same
resolved answer drives both dispatch and badges.

The schema (`BindingDecl`, the closed `Effect` union, `ControlRef`/
`ContextRef`) and the precedence resolver (`ContextStack.resolve`) live in
`common/contexts.py` — read its module docstring and the type definitions
themselves, which carry the field-level rationale inline. This doc only
covers how `pistomp/input`'s own pieces consume that schema.

## Emission is below the table (the MIDI-learn axiom)

The table governs the **local semantic response** to a control — commit a plugin
parameter, toggle bypass, change snapshot, fire a callback. It does **not** gate
the raw MIDI CC. A control with a `midi_CC` emits its CC on every actuation
whether or not any row resolves, and the emit is layered on top of the
resolved effect, never gated by it (`Modhandler._handle_encoder` emits after the
resolve; the footswitch `MidiCcEffect` arm emits inside the fire path).

This is deliberate and load-bearing: **an unbound control has no row, and its
unconditional emit is the only way mod-ui can see it to MIDI-learn it.** Wiggle a
fresh tweak encoder, mod-ui sees CC70 on the wire, you map it. If emission were
row-gated, a control could never reach the state where it earns a row — the
chicken with no egg. So the correct reading of "everything goes through the
table" is *every local action* goes through the table; raw CC is hardware
behavior beneath it. Do not "fix" the unconditional emit into the resolved
branch — that breaks learn.

The bound case still emits too, and must: the CC has to reach the external port
(or mod-host's virtual port) regardless of what the row does locally.

## Where a panel plugs in

A `Panel` states its bindings once, as data:

```python
def declare_bindings(self) -> tuple[BindingDecl, ...]:
    """Base returns (); override to declare this panel's rows."""
    return ()
```

`PluginPanel.on_event` (`plugins/base.py`) is the base implementation every
migrated panel gets for free: for a `TWEAK` or `VOLUME` control, it calls
`pistomp/input/dispatch.py`'s `resolve_local(rows, control, event_kind)` —
which walks just *this panel's own* declared rows (no cross-context chain;
a panel only ever competes with itself) — and `fire(decl, self, event)` to
execute the winner's effects. `fire` reaches into the panel through
`PanelOps`, a small structural `Protocol` (`sel_ref`, `edit_symbol`) rather
than the concrete `Panel` type — `pistomp/input` cannot import `uilib.Panel`
back without creating a cycle (`uilib` already imports `pistomp.input.event`/
`sink`).

A panel only needs real imperative `on_event` when it's a genuine state
machine, not a binding set — the NAM capture flow
(`pistomp/nam/panel.py`) is the one example: its `IDLE → CAPTURING →
DONE|FAILED|ABORTED → IDLE` transitions stay hand-written, but even there
most of the panel's *bindings* are still declared, gated by `enabled_when`
predicates that read the current state (e.g. an encoder nudges audio-card
volume only in `IDLE`).

`SelectionEditEffect` carries a `ParamRole` (`common/param_roles.py`:
`GENERIC`, `GAIN_DB`, `FREQUENCY_HZ`, `Q_FACTOR`) used two ways: which symbol
to resolve off the current selection (`sel_ref.symbol_for(role)` — a
compressor arc always returns the same symbol regardless of role, an EQ band
selection returns a different symbol per role), and which step math applies
once resolved (`PluginPanel.edit_symbol`, overridden by a panel only to add a
widget refresh or a band-lookup indirection).

## Pedalboard-level rows and blend as a context

Two things build layers into the same `ContextStack` outside of any open
panel:

* **`ControllerManager.bind`** (`pistomp/controller_manager.py`) builds the
  `PEDALBOARD` layer into `self.effective_table` while it does its existing
  work of mapping `controllers["{channel}:{CC}"]` to plugin parameters. A TTL
  `param.binding` with no matching physical controller — previously silently
  dropped — now still appends a row, tagged `ORPHANED`.
* **Blend** is a `BLEND`-kind layer, not a shadowing mechanism bolted on top
  of the table. `Modhandler` rebuilds `self._blend_layer` after every
  activate/deactivate (`_rebuild_blend_layer`), keyed by the attached
  controller's own `"{channel}:{CC}"` identity — the same identity space as
  pedalboard rows — holding a `BlendEffect`. `_fire_blend_row` resolves
  `ContextStack(layers=[*effective_table.layers, self._blend_layer])` and
  fires only if the winner is a `BlendEffect`; a control blend doesn't claim
  falls through to legacy dispatch unchanged. Because `VOLUME`/`TWEAK`/
  `ANALOG`'s chains all consult `BLEND` above `PEDALBOARD`, this is also what
  makes a blend claim correctly outrank — and visibly shadow, not silently
  kill — a co-located MIDI-learned pedalboard parameter.

## NAV edit-in-place

Tweak encoders are a fast accelerator, never the only path: every panel must
be fully operable from NAV alone (the only control v2 hardware has). CLICK on
the current selection opens whatever editor the generic parameter menu would
open for the same symbol(s):

* `Panel.input_event`'s `CLICK` branch (`uilib/panel.py`) calls
  `self._open_editor_for_selection()` — base no-op, since plain menus/system
  screens have nothing to edit.
* `PluginPanel._open_editor_for_selection` (`plugins/base.py`) implements it:
  a `MultiSelectable` selection (e.g. an EQ band — gain/freq/Q are three live
  symbols at once) opens a `Menu` submenu over `menu_rows()`; a plain
  `Selectable` opens a single `Parameterdialog` for
  `symbol_for(ParamRole.GENERIC)`. Both go through
  `Handler.open_parameter_dialog`/`open_parameter_submenu`
  (`pistomp/handler.py` → `Lcd320x240.draw_parameter_dialog`/
  `draw_symbol_menu`).
* Both take an `on_change` callback wired to `self.apply_state(self.
  snapshot_state())` — the same resync call the mod-ui `ParamSetMessage` echo
  handler uses. Needed because the generic dialog commits straight to
  `plugin.parameters[symbol].value` with no notion of a specific panel's own
  widget-sync methods; without the callback a panel's own widgets go stale
  after editing through this path even though the underlying parameter
  updated correctly.

## LCD push: the adaptive size gate

The push to the LCD is **synchronous and blocking** (`lcd_ili9341.update` → `disp.image`), and its cost scales with the dirty-rect area: a selection highlight (~78×29px) is ~2ms — well inside the 10ms tick — while the EQ curve (up to 320×178px) is tens of ms at 24MHz, which on its own overruns the tick. Because the write blocks, *deferring* a too-large transfer to a later slot can't make it cheaper; it only moves when you pay it.

So `PanelStack.propagate_dirty` always composes the change to its in-memory surface (cheap), then asks the LCD how long the push would take — `lcd.transfer_ms(clip)` — and gates on `PanelStack.INLINE_BUDGET_MS` (8ms, headroom under the tick):

- **`transfer_ms ≤ budget`** → push inline, right now. Each change is its own frame. Nav selection clips are small, so a fast spin scans visibly; param dialogs render their progress immediately.
- **`transfer_ms > budget`** → coalesce into `_pending_lcd_clip` (union) and let the next `poll_updates` flush slot push it once. Intermediate states are skipped to the latest — the EQ curve "jumps to the end" instead of grinding through every interstitial.

Each LCD driver answers `transfer_ms` from its own SPI clock (`LcdIli9341` from `baudrate`, the emulator's `LcdPygame` from `spi_hz`); the `LcdBase` default is 0 (stub LCDs are free → always inline). **A faster SPI clock means cheaper transfers, so more interstitial frames clear the budget and get drawn** — exactly the "draw more when we can afford it" goal.

The nav encoder is capped at one detent per tick (`max_drain=1` in `pistomptre.init_encoders`); tweak encoders keep the default 8. So `enc_step` applies one selector step per detent and the small-clip gate paces the scan naturally — no separate queue or divisor override. Fullscreen plugin panels still drop `lcd_poll_divisor` to 1 so their coalesced redraws flush promptly.
