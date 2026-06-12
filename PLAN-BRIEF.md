# Input Router Completion Plan

## Problem

The input-router branch established a uniform event-dispatch architecture — Controllers emit events, Handlers consume them via `InputSink.handle()` — but the migration stopped halfway. Encoders still have a dual-path `callback` vs `sink` branch. Footswitches still dispatch MIDI inline and bypass the event pipeline entirely. Encoder buttons still route through legacy callbacks. The v1 handler (`Mod`) doesn't implement `InputSink`, so v1 controllers carry a `sink is None` fallback that sends MIDI directly via per-controller `ExternalMidiOut` wrappers. Blend mode hijacks `value_change_callback` on controllers instead of receiving events through the pipeline. The nav encoder's button is wired as a separate `AnalogSwitch` rather than being absorbed into its `EncoderController`. And the `Footswitch` chord resolver is class-level global state instead of an instance-scoped helper on the handler. These half-migrations mean that every new feature (panels, blend, external routing) must navigate a maze of special cases instead of targeting a single dispatch path.

## Solution

Every hardware input control becomes a Controller that dispatches typed events (`EncoderEvent`, `AnalogEvent`, `SwitchEvent`) through its `sink` field (inherited from the base class), the Handler implements `InputSink` for all hardware versions, and all per-controller inline dispatch paths, `ExternalMidiOut` wrappers, `value_change_callback` hijacks, and class-level chord state are deleted — leaving a single uniform pipeline where the handler's `handle()` is the sole arbiter, with blend mode and panels intercepting at the handler level.

## Design principle

Event dispatch is synchronous — same call stack, same poll cycle. No queue, no deferred processing. `GpioSwitch._gpio_down()` queues a timestamp from the GPIO interrupt thread; that timestamp flows through to `SwitchEvent.timestamp`, which the handler uses for tap tempo. Single source of truth for timing.

## Implementation Tree

```
pistomp/
  controller.py              [MODIFY] sink on base; midiout removed (step 8)
  encoder.py                 [NEW] hardware quadrature decoder
  encoder_controller.py      [NEW] from encoder.py; Controller + quantizer + button
  footswitch.py              [MODIFY] dispatch SwitchEvent via sink; extract chord state
  footswitch_chords.py       [NEW] instance-scoped chord resolver
  analogmidicontrol.py       [MODIFY] always dispatch AnalogEvent; remove midiout
  gpioswitch.py              [MODIFY] callback gains timestamp; remove taptempo
  analogswitch.py             [MODIFY] add longpress_callback; callback gains timestamp; remove taptempo
  hardware.py                [MODIFY] register_sink no hasattr guard; __resolve_midiout returns virtual only
  handler.py                 [MODIFY] handle() no longer raises
  pistomp.py / pistompcore.py / pistomptre.py  [MODIFY] nav encoders get type=NAV; absorb encoder buttons; register_sink
  input/event.py             [MODIFY] SwitchEvent gains timestamp; remove RELEASE from SwitchEventKind
modalapi/
  mod.py                     [MODIFY] implement InputSink.handle()
  modhandler.py              [MODIFY] _handle_switch real dispatch; blend interception; nav branch
  external_midi.py           [MODIFY] delete ExternalMidiOut
blend/
  types.py                   [MODIFY] remove value_change_callback from BlendInputProtocol
  input_controller.py        [MODIFY] handle_event() replaces value_change_callback hijack
common/
  token.py                   [MODIFY] add NAV = "nav"
```

## Detailed Solution

### Step 1 — Extract hardware Encoder, rename EncoderController

Split `pistomp/encoder.py`'s `Encoder` into:

- **`Encoder`** (`pistomp/encoder.py`) — hardware quadrature decoder. Owns GPIO pins, direction lock, `_process_gpios()`, `_gpio_callback()`. Public API: `read_rotary() -> int` (returns accumulated direction, clears accumulator). No `sink`, `parameter`, `midi_value`, or `callback`.
- **`EncoderController`** (`pistomp/encoder_controller.py`) — `Controller` subclass owning one `Encoder`, quantizer, `parameter`, `midi_value`, `sink`, speed multiplier, absorbed button, event dispatch. `poll_hw()` reads direction from `self._hw_encoder.read_rotary()`, then calls `self.refresh(direction)`.

Remove the `callback` parameter. Nav encoders dispatch `EncoderEvent` through the sink; handler distinguishes by `controller.type == Token.NAV`. The `longpress` field becomes public (`self.longpress`, string name) — handler resolves at dispatch time via `self.get_callback(enc.longpress)`.

The `_shortpress`/`_longpress` callback fields are removed. All button presses dispatch `SwitchEvent`.

`AnalogSwitch` gains `longpress_callback` parameter (matching `GpioSwitch`'s API), needed for encoder button absorption.

### Step 2 — Token.NAV, sink on Controller base, timestamp on SwitchEvent

Add `NAV = "nav"` to `common/token.py`. All hardware classes set `type=Token.NAV` on nav encoders.

Add `self.sink: InputSink | None = None` to `Controller.__init__()`. Remove separate `sink` declarations from `EncoderController` and `AnalogMidiControl`. Remove `hasattr` guard from `Hardware.register_sink()`.

Add `timestamp: float = 0.0` to `SwitchEvent`. `GpioSwitch` captures `time.monotonic()` in the interrupt thread and passes it through `poll()` to the callback. `AnalogSwitch` passes `self.start_time` (original press moment). Both gain `timestamp: float` in their callback signature. Remove `RELEASE` from `SwitchEventKind` — hardware `RELEASED` maps to `PRESS` (short-press completion is the user event).

### Step 3 — Remove dual paths, v1 handler gets InputSink

Delete all `if self.sink is None` fallbacks and `if self.callback is not None` branches. Every controller dispatches events through `sink`. Every handler implements `InputSink.handle()`.

`Mod.handle()` routes by event type: `EncoderEvent` with `type == NAV` → state machine callbacks; `AnalogEvent` → `_emit_midi()`; `SwitchEvent` → footswitch/encoder button dispatch. `Modhandler._handle_encoder()` gains a `type == NAV` branch calling `universal_encoder_select()`.

`GpioSwitch` and `AnalogSwitch` no longer call `self.taptempo.stamp()` directly. Tap tempo stamping moves to the handler using `event.timestamp`. Remove `taptempo` from both classes.

`AnalogSwitch` callback signature becomes `callback(state, timestamp)` and `longpress_callback(state, timestamp)`.

### Step 4 — Footswitch SwitchEvent + FootswitchChords

`Footswitch._on_switch(state, timestamp)` maps hardware state to `SwitchEventKind` (`LONGPRESSED` → `LONGPRESS`, `RELEASED` → `PRESS`) and dispatches `SwitchEvent(controller=self, kind=kind, timestamp=timestamp)` via `self.sink`. No inline MIDI, relay, LED, or parameter logic.

**Switch event kind mapping**: `GpioSwitch` fires `RELEASED` on short-press release (never fires `PRESSED`). `AnalogSwitch` fires `LONGPRESSED` and `RELEASED`. Both map `RELEASED` → `PRESS` — the short-press completion IS the user press event. `LONGPRESSED` → `LONGPRESS`.

Handler's `_handle_footswitch()` preserves current behavior:
- **Longpress + relay**: toggle relay immediately, set LED, update LCD, return.
- **Longpress without relay**: observe for chord resolution.
- **Short press**: tap tempo (stamps with `event.timestamp`), preset callback, or normal toggle (LED, MIDI via `_emit_midi`, parameter, LCD).

`Footswitch.set_value()` unchanged — it's an external value change path, not a user input event.

`FootswitchChords` (new file) replaces class-level `all_longpress_groups` / `callbacks` / `check_longpress_events()`. Instance state on the handler, rebuilt on pedalboard change. `observe(fs, timestamp)` logs timestamps; `tick()` resolves chords and returns callback names. Handler fires callbacks by name.

`EncoderController` button dispatch: shortpress → `universal_encoder_sw()`, longpress → resolved callback name.

### Step 5 — Delete ExternalMidiOut

`ExternalMidiOut` class deleted. `Hardware.__resolve_midiout()` always returns virtual `MidiOut`. `Controller.midiout` is always the virtual port. `_emit_midi()` in the handler reads `hardware.external_routing` for external routing. Remove `midiout` from `Controller`, `AnalogMidiControl`, `Footswitch` constructors.

### Step 6 — Blend mode migration

`InputController.attach_to_input()` no longer sets `value_change_callback`. Stores `self.controlled_input` reference. `InputController.handle_event(event)` reads `event.controller.get_normalized_value()`, resolves position, sends diff map. `BlendMode.intercept(event)` delegates to `InputController.handle_event()` if the event's controller matches the blend input.

`Modhandler.handle()` checks `self.active_blend_mode.intercept(event)` after LCD, before normal dispatch. `BlendInputProtocol` drops `value_change_callback`.

### Step 7 — Encoder button unification

All encoder buttons absorbed into `EncoderController`. `sw_adc_chan` parameter creates internal `AnalogSwitch` (matching `sw_pin` → `GpioSwitch` pattern). v1/v3 nav encoder `AnalogSwitch` objects removed from hardware init; nav encoders get `sw_adc_chan` instead. `AnalogSwitch` needs `spi` parameter passed through.

### Step 8 — Controller.midiout removal

Remove `self.midiout` from `Controller.__init__()`. `Hardware.__route_section()` only updates `self.external_routing`, never sets `ctrl.midiout`. Handler accesses `self.hardware.midiout` for virtual-port sends.

### Step 9 — Test sweep

Comprehensive verification of all existing tests plus new `tests/input_router/` covering: default cascade, encoder events, analog events, switch events, chord resolution, blend interception, v1 dispatch.

### Commit order

| # | Commit | Risk |
|---|--------|------|
| 1 | Extract hardware Encoder, rename EncoderController | Medium (many files) |
| 2 | Token.NAV, sink on Controller base, timestamp on SwitchEvent | Low |
| 3 | Remove dual paths, v1 handler gets InputSink | High (core unification) |
| 4 | Footswitch SwitchEvent + FootswitchChords | High (user-facing) |
| 5 | Delete ExternalMidiOut | Low |
| 6 | Blend mode migration | Medium |
| 7 | Encoder button unification | Medium |
| 8 | Controller.midiout removal | Low |
| 9 | Test sweep | Low |