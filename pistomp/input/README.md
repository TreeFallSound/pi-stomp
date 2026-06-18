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
