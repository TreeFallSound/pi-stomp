# Input Router Completion Plan

## Problem

The input-router branch established a uniform event-dispatch architecture — Controllers emit events, Handlers consume them via `InputSink.handle()` — but the migration stopped halfway. Encoders still have a dual-path `callback` vs `sink` branch. Footswitches still dispatch MIDI inline and bypass the event pipeline entirely. Encoder buttons still route through legacy callbacks. The v1 handler (`Mod`) doesn't implement `InputSink`, so v1 controllers carry a `sink is None` fallback that sends MIDI directly via per-controller `ExternalMidiOut` wrappers. Blend mode hijacks `value_change_callback` on controllers instead of receiving events through the pipeline. The nav encoder's button is wired as a separate `AnalogSwitch` rather than being absorbed into its `EncoderController`. And the `Footswitch` chord resolver is class-level global state instead of an instance-scoped helper on the handler. These half-migrations mean that every new feature (panels, blend, external routing) must navigate a maze of special cases instead of targeting a single dispatch path.

## Solution

Every hardware input control becomes a Controller that dispatches typed events (`EncoderEvent`, `AnalogEvent`, `SwitchEvent`) through its `sink` field (inherited from the base class), the Handler implements `InputSink` for all hardware versions, and all per-controller inline dispatch paths, `ExternalMidiOut` wrappers, `value_change_callback` hijacks, and class-level chord state are deleted — leaving a single uniform pipeline where the handler's `handle()` is the sole arbiter, with blend mode and panels intercepting at the handler level.

## Design principle: synchronous dispatch, no queuing

Event dispatch is a synchronous method call within the same poll-cycle call stack. `Controller.refresh()` detects a change, builds an event, and calls `self.sink.handle(event)`. The handler processes it immediately and returns. No queue, no next-cycle delay. This matches the pre-input-router architecture: `GpioSwitch.poll()` → callback, `AnalogMidiControl.refresh()` → inline send, `Encoder.read_rotary()` → callback. The only thread boundary is `GpioSwitch._gpio_down()` which queues a timestamp from the GPIO interrupt thread — this is a hardware necessity, not a design choice, and it already exists.

## Implementation Tree

```
pistomp/
  controller.py                    [MODIFY] add sink: InputSink | None to __init__,
                                       remove midiout from Controller (step 8)
  encoder.py                       [NEW] hardware quadrature decoder (d_pin, clk_pin,
                                       direction, read_rotary() → int)
  encoder_controller.py            [NEW] renamed from encoder.py; Controller subclass
                                       owning an Encoder, quantizer, absorbed button,
                                       sink dispatch, speed multiplier
  footswitch.py                    [MODIFY] pressed() → _on_switch(), dispatch SwitchEvent
                                       via sink; remove class-level chord state;
                                       add toggle_relays(), set_led() as handler-callable methods
  footswitch_chords.py             [NEW] FootswitchChords helper — instance state,
                                       observe(SwitchEvent), tick(), rebuilt on pedalboard change
  analogmidicontrol.py             [MODIFY] remove sink-is-None fallback, always dispatch
                                       AnalogEvent; remove midiout parameter
  gpioswitch.py                    [MODIFY] remove taptempo; callback signature gains
                                       timestamp: float argument
  analogswitch.py                  [MODIFY] add longpress_callback param (matching
                                       GpioSwitch's API); callback signature gains
                                       timestamp: float; remove taptempo
  hardware.py                      [MODIFY] register_sink() removes hasattr guard;
                                       __resolve_midiout() returns only virtual MidiOut;
                                       nav encoder creation passes type=Token.NAV
  handler.py                       [MODIFY] Handler.handle() no longer raises
  lcd.py                           [NO CHANGE] handle() returns False — correct for now
  pistomp.py                       [MODIFY] v1: create nav encoders with type=Token.NAV,
                                       absorb encoder AnalogSwitches into EncoderController,
                                       register_sink(self) in add_hardware()
  pistompcore.py                   [MODIFY] v2: same pattern as pistomp.py
  pistomptre.py                    [MODIFY] v3: nav encoder gets type=Token.NAV,
                                       absorb nav AnalogSwitch into EncoderController,
                                       remove separate AnalogSwitch for nav button
  input/
    event.py                       [MODIFY] SwitchEvent gains timestamp: float = 0.0;
                                       SwitchEventKind.RELEASE removed (hardware RELEASED
                                       maps to PRESS — short-press completion is the user event)
    sink.py                        [NO CHANGE]

modalapi/
  mod.py                           [MODIFY] implement InputSink.handle(), remove
                                       direct-callback wiring for encoders/analog/footswitches
  modhandler.py                    [MODIFY] _handle_switch() becomes real dispatch;
                                       blend interception; FootswitchChords instance;
                                       tap tempo stamping uses event.timestamp
  external_midi.py                 [MODIFY] delete ExternalMidiOut class

blend/
  types.py                         [MODIFY] remove value_change_callback from BlendInputProtocol
  input_controller.py              [MODIFY] remove attach_to_input/detach_from_input
                                       value_change_callback hijack; add handle_event()
                                       that reads controller.get_normalized_value()

common/
  token.py                         [MODIFY] add NAV = "nav"

tests/
  input_router/                    [NEW] test suite (see step details)
```

## Detailed Solution

### Step 1 — Extract hardware Encoder, rename EncoderController

**Current**: `pistomp/encoder.py` contains a single `Encoder` class that mixes hardware decoding (GPIO pins, direction tracking, quadrature state machine) with controller concerns (quantizer, parameter binding, MIDI values, event dispatch, speed multiplier, absorbed button).

**Target**: Split into two classes:

- **`Encoder`** (`pistomp/encoder.py`) — pure hardware quadrature decoder. Owns `d_pin`, `clk_pin`, direction lock, `_process_gpios()`, `_gpio_callback()`. Public API: `read_rotary() -> int` (returns accumulated direction: -1, 0, or +1). No `sink`, no `parameter`, no `midi_value`, no `callback`.
- **`EncoderController`** (`pistomp/encoder_controller.py`, `Controller` subclass) — owns one `Encoder` instance, the quantizer (`step_values`, `current_step`, `_recalculate_steps`, `_move_steps`), `parameter`, `midi_value`, `sink`, speed multiplier (`_compute_multiplier`), absorbed button (`GpioSwitch` or `AnalogSwitch`), and event dispatch. On `refresh()`, advances quantizer, writes parameter value, builds `EncoderEvent`, dispatches via `self.sink.handle()`. On `poll_hw()`, calls `self._hw_encoder.read_rotary()` to get accumulated direction, then calls `self.refresh(direction)`.

The `Encoder` hardware class mirrors `GpioSwitch` / `AnalogSwitch` — a raw detector that the Controller owns. This completes the pattern where hardware primitives sit underneath their Controller wrappers.

**Constructor**: `EncoderController.__init__()` creates `self._hw_encoder = Encoder(d_pin, clk_pin)` and delegates direction accumulation to it. All other parameters (quantizer, parameter, button) stay on `EncoderController`.

**Accumulation**: Current `Encoder.read_rotary()` reads direction from the lock and calls `self.refresh(d)`. New `Encoder.read_rotary()` just returns the accumulated direction integer and clears the accumulator. `EncoderController.poll_hw()` calls `self._hw_encoder.read_rotary()` to get the direction, then calls `self.refresh(direction)`. The lock and direction accumulation stay in the hardware `Encoder`.

**Nav mode removal**: The `callback` parameter is removed from `EncoderController.__init__()`. Nav encoders dispatch `EncoderEvent` through the sink like all others. The handler distinguishes nav from param encoders by `event.controller.type == Token.NAV`. Nav encoders have no quantizer — they have `step_values = []` or a simple 2-step quantizer. The handler uses `event.rotations` for nav (direction only) and ignores `event.new_value` / `event.new_midi_value`.

**Absorbed button**: `EncoderController` supports both `sw_pin` (GPIO) and `sw_adc_chan` (ADC) for its button. Currently only `sw_pin` is supported. Adding `sw_adc_chan` allows v1/v2 encoder buttons (which use `AnalogSwitch`) to be absorbed into the `EncoderController`, matching the existing pattern where v3 tweak encoders absorb a `GpioSwitch`. The constructor checks: if `sw_pin` is provided, creates `GpioSwitch`; if `sw_adc_chan` is provided, creates `AnalogSwitch` (requires `spi` parameter); otherwise no button. Both call `self._on_button` / `self._on_button_longpress` as the callback.

**The `_shortpress` and `_longpress` callback fields are removed**. All button presses dispatch `SwitchEvent(controller=self, kind=PRESS or LONGPRESS, timestamp=...)` via `self.sink`. The handler resolves what to do — for tweak encoders, shortpress triggers UI navigation and longpress triggers a named callback from config; for nav encoders, button presses dispatch to the state machine.

**`longpress` stored as string name, not resolved callable**: Currently `set_longpress()` stores a resolved callable from `handler.get_callback(name)`. After the migration, `EncoderController` stores the string name as `self.longpress` (public attribute, renamed from `self._longpress`). The handler resolves the name at dispatch time via `self.get_callback(enc.longpress)`. This matches the footswitch pattern where `longpress` config values are handler-resolved callback names.

**`AnalogSwitch` gains `longpress_callback` parameter**: Currently `AnalogSwitch` has only `callback`, while `GpioSwitch` has both `callback` and `longpress_callback`. When `AnalogSwitch` is absorbed into `EncoderController` (step 7), it needs to support separate short/long callbacks. Add `longpress_callback` to `AnalogSwitch.__init__()`. `AnalogSwitch.refresh()` calls `self.longpress_callback(switchstate.Value.LONGPRESSED, self.start_time)` when the long-press threshold is exceeded, and `self.callback(switchstate.Value.RELEASED, time.monotonic())` on release.

**Tests**: Update all imports from `pistomp.encoder` to `pistomp.encoder_controller`. Update `Encoder` references to `EncoderController`. Update hardware construction in test fixtures. Verify encoder event dispatch still works.

### Step 2 — Add Token.NAV, move sink to Controller base, add timestamp to SwitchEvent

Add `NAV = "nav"` to `common/token.py`. All hardware classes set `type=Token.NAV` on their navigation encoders:

- `Pistomp.init_encoders()`: both top and bottom encoders get `type=Token.NAV`
- `Pistompcore.init_encoders()`: the single encoder gets `type=Token.NAV`
- `Pistomptre.init_encoders()`: the nav encoder gets `type=Token.NAV`

Add `self.sink: InputSink | None = None` to `Controller.__init__()`. Remove the separate `sink` declarations from `EncoderController` and `AnalogMidiControl`. Remove the `hasattr` guard from `Hardware.register_sink()` — now all Controllers have `sink` by inheritance.

Add `timestamp: float = 0.0` to `SwitchEvent` dataclass. `GpioSwitch` and `AnalogSwitch` capture `time.monotonic()` at the moment of hardware detection and pass it to their callback. `Footswitch._on_switch(state, timestamp)` and `EncoderController._on_button(state, timestamp)` / `_on_button_longpress(state, timestamp)` receive the timestamp and include it in the `SwitchEvent`. This preserves the exact timing that `TapTempo.stamp()` needs — no latency added.

**Tests**: Verify `Controller` base class has `sink`. Verify `SwitchEvent` has `timestamp`. Verify `Hardware.register_sink()` assigns sink to all controller types.

### Step 3 — Remove callback/sink-is-None dual paths, v1 handler gets InputSink

This is the core unification step. Every controller dispatches events through `sink`; every handler implements `InputSink.handle()`.

**`EncoderController.refresh()`**: Remove the `if self.callback is not None: self.callback(rotations); return` branch. Always compute quantized value and dispatch `EncoderEvent`. For nav encoders (no parameter, no quantizer), `new_value` and `new_midi_value` will be default values (0); the handler uses only `rotations`.

**`EncoderController._on_button()` / `_on_button_longpress()`**: Remove the `if self.sink is not None` / legacy fallback branches. Always dispatch `SwitchEvent`. The `timestamp` argument from `GpioSwitch`/`AnalogSwitch` flows through.

**`AnalogMidiControl._send_value()`**: Remove the `if self.sink is None: self.midiout.send_message(cc)` branch. Always dispatch `AnalogEvent`.

**`Footswitch._on_switch()`**: Remove the `if self.sink is None` fallback. Always dispatch `SwitchEvent`.

**`Mod.handle()`** (v1) implements `InputSink`:

```python
def handle(self, event: ControllerEvent) -> bool:
    if isinstance(event, EncoderEvent):
        c = event.controller
        if c.type == Token.NAV:
            if c.id == TOP_ENCODER_ID:
                self.top_encoder_select(event.rotations)
            else:
                self.bot_encoder_select(event.rotations)
            return True
        # Param encoder (v1 has none currently, but future-proof)
        if c.parameter is not None:
            self.lcd.display_parameter_value(c.parameter, event.new_value)
        self._emit_midi(c, event.new_midi_value)
        return True

    if isinstance(event, AnalogEvent):
        self._emit_midi(event.controller, event.midi_value)
        return True

    if isinstance(event, SwitchEvent):
        return self._handle_switch_v1(event)

    return False
```

`Mod.add_hardware()` calls `hardware.register_sink(self)`.

**`Modhandler._handle_encoder()`** (v3) also needs the nav-encoder branch — currently it only handles param and volume encoders:

```python
def _handle_encoder(self, event: EncoderEvent) -> bool:
    c = event.controller
    # Nav encoder: route to state machine
    if c.type == Token.NAV:
        self.universal_encoder_select(event.rotations)
        return True
    # Volume encoder: direct audio card control
    if c.type == Token.VOLUME and c.parameter is not None:
        ...
    # Param encoder: display, commit, emit MIDI
    ...
```

This is the same pattern for v2, which also uses `Modhandler`.

**v1 encoder buttons**: v1 hardware creates nav encoders with `sw_adc_chan=<channel>` and `type=Token.NAV`. The separate `AnalogSwitch` objects for encoder buttons are removed — they're absorbed into the `EncoderController`.

**v1 state machine methods** (`top_encoder_select`, `bot_encoder_select`, `universal_encoder_select`, `top_encoder_sw`, `bottom_encoder_sw`, `universal_encoder_sw`) remain unchanged. They're called from `handle()` based on controller identity, not from direct callbacks.

**`GpioSwitch` and `AnalogSwitch` callback signatures**: Gain a `timestamp: float` argument. `GpioSwitch._gpio_down()` captures `t = time.monotonic()` in the interrupt thread; `poll()` passes `t` to `callback(state, t)`. `AnalogSwitch.refresh()` passes `self.start_time` (the original press moment) as the timestamp for both LONGPRESSED and RELEASED events. This preserves the exact hardware press time for tap tempo accuracy.

**`AnalogSwitch` gains `longpress_callback`**: Currently `AnalogSwitch` has only `callback`. Adding `longpress_callback` matches `GpioSwitch`'s API and is needed when `AnalogSwitch` is absorbed into `EncoderController` as a button detector. On longpress detection: `self.longpress_callback(switchstate.Value.LONGPRESSED, self.start_time)`. On release: `self.callback(switchstate.Value.RELEASED, time.monotonic())`. Both callbacks gain the `timestamp` argument.

**Tap tempo**: `TapTempo` stays on `Footswitch`. The handler calls `fs.taptempo.stamp(event.timestamp)` using the event's timestamp — the exact moment of hardware detection, not the moment the handler processes it. `GpioSwitch` and `AnalogSwitch` no longer call `self.taptempo.stamp()` directly — tap tempo stamping moves to the handler. This is the single source of truth for tap tempo timing.

**Tests**: Add `tests/input_router/test_v1_dispatch.py` verifying `Mod.handle()` routes nav/analog/switch events correctly. Update `tests/test_analog_midi_control.py` to always assign a sink (remove `sink is None` path tests). Verify v3 tests still pass.

### Step 4 — Footswitch dispatches SwitchEvent, FootswitchChords helper

**Switch event kind mapping**: `GpioSwitch` and `AnalogSwitch` detect two meaningful hardware states: long-pressed and released-after-short-press. `RELEASED` from `GpioSwitch` IS the short-press event (GPIO footswitches only fire on release or long-press, never on initial press). The mapping is:

- `LONGPRESSED` → `SwitchEventKind.LONGPRESS`
- `RELEASED` (short press release) → `SwitchEventKind.PRESS`
- `AnalogSwitch` PRESSED state (initial press detection, used for ADC-based buttons) → `SwitchEventKind.PRESS`

There is no `SwitchEventKind.RELEASE` in practice — the release of a short press is the press event from the user's perspective. If we later need release detection (e.g., momentary holds), we can add it, but current hardware doesn't distinguish release from short-press-completion.

**`Footswitch._on_switch(state, timestamp)`** (renamed from `pressed`) is the callback that `GpioSwitch`/`AnalogSwitch` calls. It:

1. Maps the hardware state to `SwitchEventKind` using the mapping above.
2. Dispatches `SwitchEvent(controller=self, kind=kind, timestamp=timestamp)` via `self.sink.handle()`.

No inline MIDI, relay, LED, or parameter logic — all of that moves to the handler.

**Footswitch retains hardware methods** that the handler calls:
- `toggle_relays(enabled: bool)` — iterates `self.relay_list`, calls `r.enable()` / `r.disable()`
- `set_led(enabled: bool)` — wraps LED and pixel control (current `_set_led`)
- `current_toggle_state() -> bool` — returns `self.toggled`

**`Modhandler._handle_switch(event)`** — real dispatch:

```python
def _handle_switch(self, event: SwitchEvent) -> bool:
    controller = event.controller
    kind = event.kind

    if isinstance(controller, EncoderController):
        return self._handle_encoder_button(controller, kind)

    if isinstance(controller, Footswitch):
        return self._handle_footswitch(controller, kind, event.timestamp)

    return False

def _handle_encoder_button(self, enc: EncoderController, kind: SwitchEventKind) -> bool:
    if kind == SwitchEventKind.LONGPRESS:
        callback_name = enc.longpress  # resolved from config during pedalboard load
        callback = self.get_callback(callback_name)
        if callback:
            callback()
        return True
    # Short press: UI navigation
    self.universal_encoder_sw(kind)
    return True

def _handle_footswitch(self, fs: Footswitch, kind: SwitchEventKind, timestamp: float) -> bool:
    # Relay + longpress: toggle relay immediately, don't enter chord resolver
    if kind == SwitchEventKind.LONGPRESS:
        if fs.relay_list:
            new_toggled = not fs.toggled
            fs.toggled = new_toggled
            fs.toggle_relays(new_toggled)
            fs.set_led(new_toggled)
            self.update_lcd_fs(bypass_change=True)
            return True
        # No relay — log timestamp for chord resolution
        self.chord_helper.observe(fs, timestamp)
        return True

    # Short press (kind == PRESS)
    if fs.taptempo and fs.taptempo.is_enabled():
        fs.taptempo.stamp(timestamp)
        return True
    if fs.preset_callback is not None:
        if fs.preset_callback_arg is not None:
            fs.preset_callback(fs.preset_callback_arg)
        else:
            fs.preset_callback()
        return True
    # Normal toggle
    new_toggled = not fs.toggled
    fs.toggled = new_toggled
    fs.set_led(new_toggled)
    if fs.midi_CC is not None:
        self._emit_midi(fs, 127 if new_toggled else 0)
    if fs.parameter is not None:
        fs.parameter.value = not fs.toggled
    self.update_lcd_fs(footswitch=fs)
    return True
```

This preserves the current `pressed()` behavior exactly:
- Relay + longpress → toggle relay, set LED, update LCD, return immediately
- No relay + longpress → observe for chord resolution
- Tap tempo active → stamp with event timestamp, return
- Preset callback → call it, return
- Normal toggle → toggle state, LED, MIDI, parameter, LCD

**`Footswitch.set_value()` unchanged**: This method is called externally by `ControllerManager.bind()` when MOD-UI sends a bypass parameter change. It updates `toggled` state, LED, and LCD directly — it does NOT go through the event pipeline because it's not a user input. This path is unchanged by the migration.

**`FootswitchChords`** in `pistomp/footswitch_chords.py`:

```python
class FootswitchChords:
    """Instance-scoped chord resolver. Rebuilt on pedalboard change."""

    def __init__(self):
        self.groups: dict[str, LongpressGroup] = {}
        self.callbacks: dict[str, Callable] = {}

    def rebuild(self, callbacks: dict[str, Callable]):
        self.callbacks = callbacks
        self.groups = {}

    def register(self, fs: Footswitch, longpress_names: list[str]):
        for name in longpress_names:
            if name not in self.groups:
                self.groups[name] = LongpressGroup()
            self.groups[name].number_in_group += 1

    def observe(self, fs: Footswitch, timestamp: float):
        for group_name in fs.longpress_groups:
            group = self.groups.get(group_name)
            if group is not None:
                group.timestamps[fs.id] = timestamp

    def tick(self) -> list[str]:
        """Resolve chords. Called once per poll cycle. Returns list of
        callback names that fired."""
        now = time.monotonic()
        fired = []
        for name, group in list(self.groups.items()):
            num_ts = len(group.timestamps)
            if num_ts > 1:
                # Chord: two switches in same group pressed within 400ms
                last = group.timestamps.popitem()[1]
                first = group.timestamps.popitem()[1]
                if abs(last - first) < 0.4:
                    fired.append(name)
                self._clear_all()
                return fired  # only one chord fires per cycle
            elif num_ts == 1 and group.number_in_group == 1:
                # Singleton: one member, 400ms timeout
                ts = list(group.timestamps.values())[0]
                if now >= ts + 0.4:
                    fired.append(name)
                    group.timestamps.clear()
        return fired
```

Replaces `Footswitch.all_longpress_groups`, `Footswitch.callbacks`, `Footswitch.check_longpress_events()`, and `LongpressInfo`. The handler owns a `FootswitchChords` instance, calls `chord_helper.observe(fs, timestamp)` from `_handle_switch()`, and calls `chord_helper.tick()` from `poll_controls()`. When `tick()` returns callback names, the handler fires them via `self.get_callback(name)()`.

`Footswitch.set_longpress_groups()` stores `self.longpress_groups` (the list of group names). The handler calls `chord_helper.register(fs, fs.longpress_groups)` during pedalboard load.

**Tests**: Add `tests/input_router/test_switch_event.py` (Footswitch + EncoderController button dispatch). Add `tests/input_router/test_footswitch_chords.py` (chord timing, resolution, singleton vs pair, relay+longpress behavior). Update `tests/test_footswitch.py` to test `_on_switch()` event dispatch instead of `pressed()`.

### Step 5 — Delete ExternalMidiOut

`ExternalMidiOut` is a per-controller wrapper that intercepts `send_message()` and tries the external port before falling back to virtual. With all MIDI now flowing through `_emit_midi()` (which reads `hardware.external_routing`), this wrapper is redundant.

1. Remove `class ExternalMidiOut` from `modalapi/external_midi.py`.
2. `Hardware.__resolve_midiout()` returns `(self.midiout, RoutingInfo.virtual())` or `(self.midiout, RoutingInfo.external(port_name))`. The first element is always the virtual `MidiOut`.
3. `Controller.midiout` is always the virtual port. `Hardware.is_external()` / `external_port_name()` are the sole routing authority.
4. `ControllerManager._bind_external_controllers()` no longer wraps controllers with `ExternalMidiOut`. External routing display info comes from `Hardware.external_routing`.
5. Remove `midiout` from `Controller.__init__()`, `AnalogMidiControl.__init__()`, and `Footswitch.__init__()`. Hardware construction no longer passes `midiout` to these classes.
6. `Hardware.__route_section()` no longer sets `ctrl.midiout` — it only updates `self.external_routing`.
7. `AnalogMidiControl._send_value()` no longer needs `self.midiout`.

**Tests**: Update `tests/test_hardware.py` — `__resolve_midiout()` returns `(self.midiout, RoutingInfo)` always, no more `ExternalMidiOut` wrapping assertions. Update `tests/test_external_midi.py` — remove `ExternalMidiOut` test class.

### Step 6 — Blend mode migration

**Current**: `InputController.attach_to_input()` sets `control.value_change_callback = self.handle_value_change`. On every input change, the controller calls this callback, which reads `control.get_normalized_value()` and sends interpolated parameters.

**Target**: Blend mode intercepts events at the handler level.

1. **`BlendInputProtocol`** drops `value_change_callback`. Becomes:
   ```python
   class BlendInputProtocol(Protocol):
       id: int
       def get_normalized_value(self) -> float: ...
   ```

2. **`InputController.attach_to_input()`** no longer sets `value_change_callback`. It finds the controller matching `input_id` and stores `self.controlled_input = control`. The controller continues dispatching events through its sink normally.

3. **`InputController.handle_event(event: ControllerEvent) -> bool`**: New method. For `AnalogEvent` or `EncoderEvent`, reads `event.controller.get_normalized_value()`, resolves position, sends diff map. Returns `True` (consumed). Returns `False` for other event types or wrong controller.

4. **`InputController.detach_from_input()`**: Just sets `self.controlled_input = None`. No callback cleanup.

5. **`BlendMode.intercept(event) -> bool`**: Checks if `event` is an `AnalogEvent` or `EncoderEvent` whose controller is the blend input. Delegates to `InputController.handle_event(event)`. Returns `True` if consumed.

6. **`Modhandler.handle()`** checks for blend interception right after the LCD check:
   ```python
   def handle(self, event: ControllerEvent) -> bool:
       if self._lcd is not None and self._lcd.handle(event):
           return True
       if self.active_blend_mode and self.active_blend_mode.intercept(event):
           return True
       # Normal dispatch...
   ```

**Tests**: Replace `enc.value_change_callback is not None` assertions with `handler.active_blend_mode.input_controller.controlled_input is enc`. Replace `ic.handle_value_change(raw, enc)` calls with `ic.handle_event(AnalogEvent(controller=enc, raw_value=raw, midi_value=enc.midi_value))` or `ic.handle_event(EncoderEvent(...))`. Add `tests/input_router/test_blend_interception.py`.

### Step 7 — Encoder button unification

All encoder buttons are absorbed into their `EncoderController`. The `sw_adc_chan` parameter creates an internal `AnalogSwitch`, just as `sw_pin` creates a `GpioSwitch`.

1. `EncoderController.__init__()` gains `sw_adc_chan: Optional[int] = None` and `spi: Optional[object] = None` alongside `sw_pin`. If `sw_adc_chan` is provided, creates `AnalogSwitch(spi, sw_adc_chan, threshold, callback=self._on_button, longpress_callback=self._on_button_longpress)`.

2. v1 `Pistomp.init_encoders()`: The separate `AnalogSwitch` objects for encoder buttons are removed. Instead, top and bottom encoders are created with `sw_adc_chan=TOP_ENC_SWITCH_CHANNEL` / `sw_adc_chan=BOT_ENC_SWITCH_CHANNEL`, `spi=self.spi`, and `type=Token.NAV`.

3. v3 `Pistomptre.init_analog_controls()`: Remove the special-case `AnalogSwitch` for the nav encoder button. Instead, the nav encoder in `init_encoders()` gets `sw_adc_chan=NAV_ADC_CHAN` and `spi=self.spi`.

4. v2 `Pistompcore.init_encoders()`: Already uses `sw_pin=1` for the encoder button. Add `type=Token.NAV`.

5. `EncoderController.poll()` calls `self._button.poll()` for both `GpioSwitch` and `AnalogSwitch` variants. The `AnalogSwitch` variant needs its `refresh()` called — this happens in `poll()` if `self._button` is an `AnalogSwitch`.

**Tests**: Verify encoder button events dispatch `SwitchEvent` with correct `timestamp`. Verify v1/v2/v3 encoder button creation in hardware tests.

### Step 8 — Controller.midiout removal

After `ExternalMidiOut` is deleted, `Controller.midiout` is no longer needed for any controller (all MIDI goes through `_emit_midi()` via the handler).

Remove `self.midiout` from `Controller.__init__()`. `AnalogMidiControl` and `Footswitch` no longer accept `midiout` in their constructors. `Hardware.__init_midi_default()` and `Hardware.__init_midi()` still create the virtual `MidiOut` as `self.midiout` — the handler accesses it via `self.hardware.midiout`.

`Hardware.__route_section()` no longer sets `ctrl.midiout`. It only updates `self.external_routing[ctrl] = routing`.

`Footswitch.__init__()` no longer takes `midiout` parameter. `Hardware.create_footswitches()` no longer passes `self.midiout` to `Footswitch()`.

**Tests**: Update hardware construction in test fixtures. Remove `midiout` from `Footswitch` and `AnalogMidiControl` constructor calls.

### Step 9 — Test sweep

Each step above includes test updates alongside the code. This final step is a comprehensive sweep to verify:

1. All existing tests pass.
2. `tests/input_router/` covers the default cascade, encoder events, analog events, switch events, chord resolution, blend interception, and v1 dispatch.
3. Snapshot tests (LCD rendering) still pass.
4. `tests/test_external_midi.py` no longer references `ExternalMidiOut`.
5. `tests/test_hardware.py` routing assertions use `RoutingInfo` not `ExternalMidiOut`.
6. `tests/v3/test_blend_mode.py` uses `handle_event()` instead of `value_change_callback`.

### Commit order

| # | Commit | Risk | Tests updated |
|---|--------|------|--------------|
| 1 | Extract hardware Encoder, rename EncoderController | Medium (many files) | Import updates, encoder event dispatch |
| 2 | Add Token.NAV, sink on Controller base, timestamp on SwitchEvent | Low | Controller base, SwitchEvent |
| 3 | Remove callback/sink-is-None dual paths, v1 handler gets InputSink | High (core unification) | v1 dispatch, analog event, encoder event |
| 4 | Footswitch SwitchEvent dispatch + FootswitchChords | High (user-facing) | Switch events, chord resolution, footswitch |
| 5 | Delete ExternalMidiOut | Low | Hardware routing, external MIDI |
| 6 | Blend mode migration | Medium | Blend interception, activation/deactivation |
| 7 | Encoder button unification (absorb AnalogSwitch) | Medium | Encoder button events, v1/v3 hardware |
| 8 | Controller.midiout removal | Low | Hardware construction, constructor calls |
| 9 | Test sweep | Low | All of the above |