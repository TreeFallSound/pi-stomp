# Input Router — Architecture

Single dispatch path for every hardware input event, across all hardware
versions. Replaces `value_change_callback` slots, `consume_tweak_rotation`,
the per-controller `ExternalMidiOut` wrapper, the `callback` vs `sink`
dual path on encoders, inline footswitch MIDI dispatch, and class-level
footswitch chord state.

## Branch graph

```
feat/external-midi
  feat/controller-routing
    feat/encoder-controller
      feat/input-router      ← this document
        feat/plugin-panels   ← uses LCD-as-sink to intercept
          feat/x42-eq        ← rewrites EQ on the base

feat/blend-mode              ← folded in (Step 6)
```

## Dispatch model

```
Hardware tick (10ms poll)
  → Controller.poll_hw()
      → reads its raw detector (Encoder / GpioSwitch / AnalogSwitch / ADC)
      → builds event (EncoderEvent | AnalogEvent | SwitchEvent)
      → controller already advanced its own state (quantizer,
        parameter.value, midi_value)
      → self.sink.handle(event)  →  bool (True = consumed)
```

- **Controllers are sources.** Each carries one field, `sink: InputSink`,
  inherited from the `Controller` base. Before dispatching, the controller
  has already written `parameter.value` and `midi_value` — the event
  carries facts, not requests.
- **InputSinks are actors.** A sink implements `handle(event) -> bool`.
  Returning `True` means the sink fully handled the event; the controller
  does nothing further. Returning `False` is informational only — there is
  no automatic forwarding, no stack, no framework. Composition is whatever
  the sink's `handle` chooses to write.
- **The handler is the sink** for every controller, on every hardware
  version. v3/v2 use `Modhandler`; v1 uses `Mod`. Both implement
  `InputSink`. The handler asks the LCD first (so panels can intercept),
  then blend mode, then runs its own cascade in plain code: display the
  parameter dialog, commit to mod-host unless externally routed, emit MIDI.
- **LCD owns its panel stack.** Push/pop semantics live where they
  actually mean something — opening and dismissing a panel. The LCD's
  `handle` walks that stack and returns True if any panel consumed.
- **Helpers** (`Encoder`, `GpioSwitch`, `AnalogSwitch`) sit underneath
  their owning Controller. They detect raw edges/rotation; the Controller
  builds the event. They never call `sink.handle`.

There is no `InputRouter` class. There is no global sink stack. The
"router" is the single `sink` field on each controller plus whatever code
each sink chooses to write inside `handle`.

## Scope: all hardware versions

This migration unifies v1 (`Mod` + `Pistomp`), v2 (`Modhandler` +
`Pistompcore`), and v3 (`Modhandler` + `Pistomptre`) onto one path. Every
handler implements `InputSink.handle()`. There is **no** `sink is None`
inline fallback — that dual path is deleted. `Hardware.register_sink(self)`
is called from `add_hardware()` on every version and assigns the sink to
all controllers by base-class inheritance.

## Event types

```python
@dataclass
class ControllerEvent:
    controller: Controller

@dataclass
class EncoderEvent(ControllerEvent):
    rotations: int = 0
    multiplier: float = 1.0
    new_value: float = 0.0      # already-quantized parameter value
    new_midi_value: int = 0     # already-renormalized MIDI value

@dataclass
class AnalogEvent(ControllerEvent):
    raw_value: int = 0          # ADC reading
    midi_value: int = 0         # already-converted MIDI value

@dataclass
class SwitchEvent(ControllerEvent):
    kind: SwitchEventKind        # PRESS | LONGPRESS
    timestamp: float = 0.0       # time.monotonic() at hardware detection
```

Events are immutable carriers. They have no `consumed` field — that's the
return value of `handle`. Sinks discriminate by `isinstance` or `match`.

`SwitchEventKind.RELEASE` does **not** exist. GPIO footswitches fire only
on release-after-short-press or on long-press, so `RELEASED` (short-press
completion) maps to `PRESS` — that is the user-meaningful event. The ADC
`AnalogSwitch` initial-press detection also maps to `PRESS`. Add a real
`RELEASE` kind only if momentary-hold semantics are ever needed.

`SwitchEvent.timestamp` carries the exact `time.monotonic()` captured at
hardware detection (the GPIO interrupt moment, or the ADC press moment).
It threads through to `TapTempo.stamp()` so tap-tempo timing reflects the
press, not the moment the handler happens to process the event.

## InputSink protocol

```python
class InputSink(abc.ABC):
    @abc.abstractmethod
    def handle(self, event: ControllerEvent) -> bool: ...
```

One method. Sinks are free to do anything: forward to another sink,
ignore some event types, run a cascade, check `event.controller.type`,
match on event class, etc. No base class machinery — the freedom *is* the
design.

## Default cascade in `Modhandler.handle` (v2/v3)

```python
def handle(self, event):
    if self._lcd is not None and self._lcd.handle(event):
        return True
    if self.active_blend_mode and self.active_blend_mode.intercept(event):
        return True
    match event:
        case EncoderEvent(controller=c):
            return self._handle_encoder(event)
        case AnalogEvent(controller=c):
            if c.type == Token.VOLUME:
                self.audio_card.set_volume(c.midi_value)
                return True
            self._emit_midi(c)
            return True
        case SwitchEvent():
            return self._handle_switch(event)
    return False
```

`_handle_encoder` discriminates by `controller.type`:

- `Token.NAV` → `universal_encoder_select(event.rotations)` (direction
  only; `new_value` / `new_midi_value` ignored — nav encoders have no
  quantizer/parameter).
- `Token.VOLUME` → audio-card volume.
- otherwise (param encoder) → `display_parameter_value`, commit to
  mod-host unless externally routed, `_emit_midi`.

`_emit_midi(c, value)` reads `hardware.external_routing` for `c`: emits to
the external port if routed there, else to MIDI Through. Plain function,
not a sink. v1's `Mod.handle` follows the same shape, routing nav
encoders to `top_encoder_select` / `bot_encoder_select` by controller id.

## Encoder: hardware decoder + controller

The old single `Encoder` class is **split**:

- **`Encoder`** (`pistomp/encoder.py`) — pure quadrature decoder. Owns
  `d_pin`, `clk_pin`, the direction lock and accumulator, `_process_gpios`,
  `_gpio_callback`. Public API: `read_rotary() -> int` returns the
  accumulated direction (-1, 0, +1) and clears the accumulator. No `sink`,
  no `parameter`, no `midi_value`. Mirrors `GpioSwitch` / `AnalogSwitch`:
  a raw detector the Controller owns.
- **`EncoderController`** (`pistomp/encoder_controller.py`, a `Controller`
  subclass) — owns one `Encoder`, the quantizer (`step_values`,
  `current_step`, `_recalculate_steps`, `_move_steps`), `parameter`,
  `midi_value`, `sink`, the speed multiplier, and the absorbed button.
  `poll_hw()` calls `self._hw_encoder.read_rotary()`, then `refresh(dir)`.
  `refresh()` advances the quantizer, writes `parameter.value`, sets
  `midi_value`, builds an `EncoderEvent` with `new_value` /
  `new_midi_value` already filled in, and dispatches. Sinks never reach
  into encoder internals; `_move_steps` / `_value_to_midi` stay private.

`encoder_controller.py` is **kept** (renamed from the original
`encoder.py`); `encoder.py` becomes the hardware decoder.

Same dispatch shape for `AnalogMidiControl._send_value()`: compute
`midi_value`, stash it on `self`, build the event with `midi_value` set,
dispatch. No `sink is None` branch.

### Absorbed encoder button

The button lives inside its `EncoderController` — there are no standalone
`AnalogSwitch` objects for encoder buttons. The constructor takes either
`sw_pin` (creates a private `GpioSwitch`) or `sw_adc_chan` + `spi`
(creates a private `AnalogSwitch`). Both wire to `self._on_button` /
`self._on_button_longpress`, which emit `SwitchEvent(controller=self,
kind=PRESS|LONGPRESS, timestamp=...)` through the sink. No `_shortpress` /
`_longpress` callable fields.

`longpress` is stored as the **string callback name** from config
(`EncoderController.longpress`, public). The handler resolves it at
dispatch time via `self.get_callback(enc.longpress)` — matching the
footswitch convention. Short press routes to UI navigation
(`universal_encoder_sw`); for nav encoders the press drives the state
machine.

`AnalogSwitch` gains a `longpress_callback` parameter (matching
`GpioSwitch`) so it can serve as the absorbed button's detector. Both
switch callbacks gain the `timestamp` argument.

Hardware wiring:

- v1 `Pistomp.init_encoders()` — top/bottom encoders get
  `sw_adc_chan=…`, `spi=self.spi`, `type=Token.NAV`; the old standalone
  encoder-button `AnalogSwitch` objects are removed.
- v2 `Pistompcore.init_encoders()` — single encoder keeps `sw_pin=1`,
  adds `type=Token.NAV`.
- v3 `Pistomptre` — nav encoder gets `sw_adc_chan=NAV_ADC_CHAN`,
  `spi=self.spi`, `type=Token.NAV`; the special-case nav-button
  `AnalogSwitch` in `init_analog_controls()` is removed.

## Footswitch dispatch + chord helper

`Footswitch.pressed()` becomes `Footswitch._on_switch(state, timestamp)` —
the callback `GpioSwitch`/`AnalogSwitch` invokes. It maps hardware state
to `SwitchEventKind` and dispatches `SwitchEvent(controller=self,
kind=kind, timestamp=timestamp)` through `self.sink`. No inline MIDI,
relay, LED, or parameter logic — all of that moves into the handler.

The footswitch retains hardware methods the handler calls:
`toggle_relays(enabled)`, `set_led(enabled)`, `current_toggle_state()`.
`set_value()` (called by `ControllerManager.bind()` on an inbound MOD-UI
bypass change) is unchanged — it is not a user input and never enters the
event pipeline.

`Modhandler._handle_switch(event)` is real dispatch:

```python
def _handle_switch(self, event):
    c = event.controller
    if isinstance(c, EncoderController):
        return self._handle_encoder_button(c, event.kind)
    if isinstance(c, Footswitch):
        return self._handle_footswitch(c, event.kind, event.timestamp)
    return False
```

`_handle_footswitch` preserves today's `pressed()` behavior exactly:
relay + longpress toggles the relay immediately; no-relay longpress is
handed to the chord resolver; short press stamps tap tempo
(`fs.taptempo.stamp(event.timestamp)`), fires a preset callback, or
toggles state/LED/MIDI/parameter and updates the LCD.

Tap-tempo stamping is now **handler-owned**: `GpioSwitch` / `AnalogSwitch`
no longer call `taptempo.stamp()` themselves, and `gpioswitch.py` /
`analogswitch.py` drop their own taptempo handling. The handler is the
single source of truth for tap-tempo timing, using `event.timestamp`.

### `FootswitchChords` helper

The chord resolver moves off `Footswitch` classvars
(`all_longpress_groups`, `callbacks`, `check_longpress_events`,
`LongpressInfo`) into `pistomp/footswitch_chords.py` — instance state
owned by the handler:

```python
class FootswitchChords:
    def rebuild(self, callbacks): ...          # on pedalboard change
    def register(self, fs, longpress_names): ...  # group membership
    def observe(self, fs, timestamp): ...      # from _handle_switch
    def tick(self) -> list[str]: ...           # from poll_controls
```

`observe()` records a per-switch timestamp; `tick()` (once per poll
cycle) resolves chords inside the 400 ms window and returns the callback
names that fired, which the handler invokes via `self.get_callback(name)()`.
Behavior is identical to today (see Appendix A). `register()` is called
during pedalboard load from `fs.longpress_groups`.

## Blend mode (folded in — Step 6)

Blend mode no longer hijacks `value_change_callback`; it intercepts at the
handler level.

- `BlendInputProtocol` drops `value_change_callback`, keeping only `id`
  and `get_normalized_value()`.
- `InputController.attach_to_input()` stores `self.controlled_input =
  control` and nothing else; the controller keeps dispatching through its
  sink. `detach_from_input()` just clears `controlled_input`.
- `InputController.handle_event(event) -> bool` reads
  `event.controller.get_normalized_value()`, resolves position, sends the
  diff map; returns `True` when consumed.
- `BlendMode.intercept(event) -> bool` checks the event is an
  `AnalogEvent`/`EncoderEvent` for the blend input and delegates to
  `handle_event`. The handler calls `active_blend_mode.intercept(event)`
  right after the LCD check.

## Push/pop lives on the LCD

When a panel opens, it pushes itself on the LCD's panel stack; when it
closes, it pops. The LCD's `handle` walks the stack top-down; a panel
returns True if it consumes the event for that controller. This is the
only place stack semantics exist, next to the thing that needs them.

Per-controller targeting is free: a panel that only cares about encoder
#2 checks `event.controller is self.target_encoder` and returns False for
everything else.

## File layout

```
pistomp/
  controller.py            # sink: InputSink | None on base; no midiout (Step 8)
  encoder.py               # hardware quadrature decoder (read_rotary)
  encoder_controller.py    # Controller subclass; owns Encoder + button
  footswitch.py            # _on_switch dispatch; toggle_relays/set_led
  footswitch_chords.py     # instance-scoped chord resolver
  analogmidicontrol.py     # always dispatches AnalogEvent
  gpioswitch.py            # callback gains timestamp; taptempo removed
  analogswitch.py          # gains longpress_callback; timestamp; taptempo removed
  input/
    event.py               # event dataclasses (SwitchEvent.timestamp)
    sink.py                # InputSink ABC
common/
  token.py                 # adds NAV = "nav"
modalapi/
  mod.py                   # v1 implements InputSink.handle()
  modhandler.py            # _handle_switch real dispatch; blend intercept
  external_midi.py         # ExternalMidiOut deleted
blend/
  types.py                 # BlendInputProtocol drops value_change_callback
  input_controller.py      # handle_event() replaces callback hijack
```

## What this replaces

- The `callback` vs `sink` dual path on encoders, and every `sink is None`
  inline fallback (encoders, analog, footswitches) — deleted. All
  controllers dispatch through `sink`; all handlers implement it.
- The per-controller `ExternalMidiOut` wrapper — deleted.
  `Hardware.__resolve_midiout()` always returns the virtual `MidiOut`;
  `Hardware.external_routing` is the sole routing authority, read by the
  handler's `_emit_midi`.
- `Controller.midiout` — removed (Step 8). The virtual `MidiOut` lives on
  `Hardware.midiout`; the handler reaches it via `self.hardware.midiout`.
  `Footswitch` / `AnalogMidiControl` no longer take a `midiout` arg.
- `value_change_callback` on `Encoder`/`AnalogMidiControl` — deleted; blend
  mode now intercepts at the handler.
- Class-level footswitch chord state — replaced by the `FootswitchChords`
  instance.
- `SwitchEventKind.RELEASE` — removed (RELEASED maps to PRESS).

## Commit order

| # | Commit | Risk |
|---|--------|------|
| 1 | Extract hardware `Encoder`, rename `EncoderController` | Medium |
| 2 | Add `Token.NAV`, `sink` on `Controller` base, `timestamp` on `SwitchEvent` | Low |
| 3 | Remove callback/`sink is None` dual paths; v1 handler gets `InputSink` | High |
| 4 | Footswitch `SwitchEvent` dispatch + `FootswitchChords` | High |
| 5 | Delete `ExternalMidiOut` | Low |
| 6 | Blend mode migration | Medium |
| 7 | Encoder button unification (absorb `AnalogSwitch`) | Medium |
| 8 | `Controller.midiout` removal | Low |
| 9 | Test sweep | Low |

`tests/input_router/` covers the default cascade, encoder/analog/switch
events, chord resolution, blend interception, and v1 dispatch. Snapshot
(LCD) tests must still pass.

## Out of scope

- EQ panel rewrite — `feat/plugin-panels` → `feat/x42-eq`.
- Tuner panel — doesn't intercept inputs today; untouched.
- MIDI Learn coordination — mod-host owns the learn map.
- LCD / output side — input dispatch only.

---

## Appendix A — Footswitch chords (longpress groups)

Pre-existing behavior that has to survive the migration. Today lives in
`pistomp/footswitch.py` as class-level state; moves to the
`FootswitchChords` helper owned by the handler.

### What it is

Each footswitch's YAML `longpress` field names a group (or a list of
groups). Every footswitch naming the same group is a member; the group
name is also the key into the resolver's callbacks. Hardcoded valid
groups: `next_snapshot`, `previous_snapshot`, `toggle_bypass`,
`set_mod_tap_tempo`, `toggle_tap_tempo_enable`, `toggle_tuner_enable`.

Resolution runs once per poll cycle inside a 400 ms window:

- Two switches in the same group both longpressed within 400 ms → fire
  the group callback once; suppress both solos.
- Singleton group (`number_in_group == 1`) → solo longpress fires
  400 ms after the press.
- Multi-member group, no partner within 400 ms → nothing fires.

The list form (`longpress: [a, b]`) is the only configuration where a
switch keeps its solo action *and* contributes to a chord.

### Where it lives now

`FootswitchChords` helper owned by the handler. Instance state: group
membership map, pending-longpress timestamps. Rebuilt on
`pedalboard_changed` after `hardware.reinit(cfg)`. `tick()` called from
`poll_controls`. When `handle` gets a footswitch `LONGPRESS` with no
relay, it hands it to `chord_helper.observe(fs, event.timestamp)`; the
helper decides what fires on the next `tick`.

Not a sink. Plain helper. Two reasons it stays internal to the handler:

1. Cross-controller state (timestamps from multiple footswitches).
2. Consume-vs-fire is timing-dependent and deferred — wants direct
   access to the resolver, not a generic protocol.
