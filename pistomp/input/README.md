# Input dispatch

Every hardware input — footswitch, encoder, knob, expression pedal — flows through one path, identical across hardware versions. A control reads its own pins, advances its own state, packages what happened into an immutable event, and hands that event to a single sink. There is no `InputRouter` class and no global stack: the "router" is just the `sink` field every controller inherits, plus whatever code each sink writes inside `handle`.

## Controllers are sources, sinks are actors

A `Controller` (`controller.py`) owns one raw detector — an `Encoder`, `GpioSwitch`, `AnalogSwitch`, or ADC channel — and a `sink: InputSink`. On each 10ms tick `poll_hw()` reads the detector, advances the controller's own state (encoder quantizer, `parameter.value`, `midi_value`), builds the matching event, and calls `self.sink.handle(event)`. By the time the event is dispatched, the controller has already updated itself: **the event carries facts, not requests.**

An `InputSink` (`sink.py`) is one abstract method, `handle(event) -> bool`. `True` means "fully handled; the controller does nothing further." `False` is informational — there is no automatic forwarding, no framework. Sinks compose by writing the forwarding they want, in plain code.

The detectors underneath a controller (`Encoder.read_rotary()`, the GPIO/ADC switch callbacks) only sense raw edges and rotation. They never call `sink.handle` themselves — the owning controller builds the event.

## Events

Three immutable dataclasses (`event.py`), all carrying their source `controller`; sinks discriminate by `isinstance` / `match`:

* `EncoderEvent` — `rotations` this tick, plus the already-quantized `new_value` and `new_midi_value`.
* `AnalogEvent` — `raw_value` (ADC) and the already-converted `midi_value`.
* `SwitchEvent` — `kind` (`PRESS` | `LONGPRESS`) and a `timestamp`.

There is no `consumed` field; that's the return of `handle`. There is no `RELEASE` kind: GPIO footswitches fire only on short-press-release or long-press, so a completed short press *is* `PRESS` — the user-meaningful event. `SwitchEvent.timestamp` is the `time.monotonic()` captured at the moment of detection (the GPIO interrupt, the ADC press), threaded all the way through to tap-tempo stamping so timing reflects the press, not when the handler got around to it.

## The handler is the sink

For every controller on every version the sink is the handler — `Modhandler` (v2/v3) or `Mod` (v1) — wired once by `Hardware.register_sink(self)`. Its `handle` is a fixed cascade: ask the **LCD** first (so an open panel can intercept inputs for the encoder it cares about), then the active **blend mode**, then run the handler's own logic by event type — display the parameter dialog, commit to mod-host unless the control is externally routed, emit MIDI.

Push/pop semantics live on the LCD, next to the only thing that needs them: a panel pushes itself when it opens and pops when it closes, and the LCD's `handle` walks that stack top-down. Blend mode likewise intercepts at the handler instead of hijacking a controller callback — `intercept(event)` reads the source controller's normalized position and sends its diff map.

Encoders are split to keep this clean: `Encoder` is the pure quadrature decoder, `EncoderController` is the `Controller` that owns it plus the quantizer and the absorbed push-button. The nav encoder's button is not a standalone switch — it lives inside its controller and dispatches a `SwitchEvent` like any other. Footswitch chords (longpress groups) are the one piece of genuinely cross-controller, timing-deferred state, so they live in `footswitch_chords.py` as a handler-owned helper rather than a sink: `observe()` records a press, `tick()` resolves the 400ms window once per poll and names the callbacks that fired.

## LCD push: the adaptive size gate

The push to the LCD is **synchronous and blocking** (`lcd_ili9341.update` → `disp.image`), and its cost scales with the dirty-rect area: a selection highlight (~78×29px) is ~2ms — well inside the 10ms tick — while the EQ curve (up to 320×178px) is tens of ms at 24MHz, which on its own overruns the tick. Because the write blocks, *deferring* a too-large transfer to a later slot can't make it cheaper; it only moves when you pay it.

So `PanelStack.propagate_dirty` always composes the change to its in-memory surface (cheap), then asks the LCD how long the push would take — `lcd.transfer_ms(clip)` — and gates on `PanelStack.INLINE_BUDGET_MS` (8ms, headroom under the tick):

- **`transfer_ms ≤ budget`** → push inline, right now. Each change is its own frame. Nav selection clips are small, so a fast spin scans visibly; param dialogs render their progress immediately.
- **`transfer_ms > budget`** → coalesce into `_pending_lcd_clip` (union) and let the next `poll_updates` flush slot push it once. Intermediate states are skipped to the latest — the EQ curve "jumps to the end" instead of grinding through every interstitial.

Each LCD driver answers `transfer_ms` from its own SPI clock (`LcdIli9341` from `baudrate`, the emulator's `LcdPygame` from `spi_hz`); the `LcdBase` default is 0 (stub LCDs are free → always inline). **A faster SPI clock means cheaper transfers, so more interstitial frames clear the budget and get drawn** — exactly the "draw more when we can afford it" goal.

The nav encoder is capped at one detent per tick (`max_drain=1` in `pistomptre.init_encoders`); tweak encoders keep the default 8. So `enc_step` applies one selector step per detent and the small-clip gate paces the scan naturally — no separate queue or divisor override. Fullscreen plugin panels still drop `lcd_poll_divisor` to 1 so their coalesced redraws flush promptly.
