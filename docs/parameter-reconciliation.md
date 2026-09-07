# Parameter reconciliation — research notes

This document records the research on the input, binding, and parameter stack.
It gives the facts, the defects, and the options. It uses ASD-STE100 Simplified
Technical English.

## Terms

- **MOD-UI** — the web application that owns the parameter state.
- **mod-host** — the audio host below MOD-UI. It applies the values.
- **echo** — a `param_set` message from MOD-UI or mod-host. It gives the current
  absolute value of one port.
- **preview** — an optimistic local write. The screen moves. The device sends
  nothing and marks nothing as confirmed.
- **commit** — a finished local edit. The device sends the value, then marks it.
- **reconcile** — the device adopts the echo value. This is the truth.
- **the flicker** — a short backward move of a value on the screen. It happens
  when an echo of an older value arrives after a newer local preview.
- **a fast scrub** — a fast turn of a tweak encoder.

## The domain rule

MOD-UI is the single writer of the parameter and bypass state. The device emits,
paints the screen optimistically, and reconciles against the echo. The device
must never treat the local value as the truth.

## The reactive Parameter

`common/parameter.py` holds the only value cell. It owns these fields:

- `_value` — the live value. A preview or a reconcile writes it.
- `_confirmed` — the last value MOD-UI echoed. A failed commit rolls back to it.
- `_observers` — callbacks for every change. The screen repaints from these.
- `_committed_observers` — callbacks for a confirmed value only. A footswitch
  keycap tracks these. (The code calls this list `_settled_observers` today.
  See "Rename" below.)

## The three write operations

- `reconcile(value)` sets `_confirmed`, writes `_value`, and notifies the
  committed observers. It always notifies, even if the value did not change.
- `preview(value)` writes `_value` only. It does not notify the committed
  observers.
- `commit(value, sink)` writes `_value`, sends through the sink, then notifies
  the committed observers. If the send fails, it rolls back to `_confirmed`.

`reconcile` and a successful `commit` are the same event: the confirmed value
changed. The name "settled" is the union of these two. This union exists only
because the two are one event.

## Rename: "settled" to "committed"

The team does not want the term "settled". Change these names:

- `subscribe_settled` to `on_commit`.
- `_settled_observers` to `_committed_observers`.
- `_notify_settled` to `_notify_committed`.
- `test_settled_fires_...` to `test_committed_fires_...`.

The `commit` method and the "committed" event become one concept. This is
correct. Both reference systems below use one name for both.

## Known defects

Each defect is a place where a write does not go through the correct operation.

1. **`commit` does not advance `_confirmed`.** After a good local commit,
   `_confirmed` keeps the last echoed value. On the paths with no echo (the
   bypass of a footswitch-less plugin), `_confirmed` stays stale. A later failed
   commit then rolls back to the wrong value. `common/parameter.py`.
2. **A range change skips the committed observers.** `set_binding_range` and
   `clear_binding_range` write `_value` and notify only `_observers`. A
   footswitch keycap does not refresh. `_confirmed` can fall outside the new
   range. `common/parameter.py`.
3. **The volume encoder never commits.** The volume arm only previews and writes
   the audio card. It never notifies the committed observers. `_confirmed` never
   moves. `modalapi/modhandler.py`.
4. **The analog turn never writes the bound parameter.** The analog arm only
   emits the MIDI CC. The parameter value moves only from the echo. The LCD bar
   and the parameter become two stores. `modalapi/modhandler.py`.
5. **The footswitch CC is not gated during a board load.** `_emit_midi` sends a
   CC even in the load window. The parallel `param_set` path refuses the send.
   A stomp during a load can diverge. **Decision: gate `_emit_midi` too.**

## How other systems do this

### Zynthian (zynthian-ui, `zyngine/zynthian_controller.py`)

Zynthian is the closest hardware twin. It runs on a Raspberry Pi with encoders
and switches.

- It keeps one value: `self.value`. It has no confirmed or preview split.
- It has one write path: `set_value(val, send=True)`. The flag `send` gives the
  provenance. `send=True` sends the value out. `send=False` adopts a value with
  no send.
- The inbound MIDI path (`midi_control_change`) calls the same `set_value`.
- The UI is a pull model. The flag `is_dirty` tells the UI to repaint.
- Zynthian stops the echo clobber with a time window. `set_ignore_engine_fb`
  makes the controller ignore the engine feedback for a period.

### Mixxx (`src/controllers/softtakeover.cpp`)

Mixxx is the reference for the reconciliation of a physical control against the
software value.

- It keeps one value in the `ControlObject`.
- It tracks the provenance as an "in sync with MIDI" flag.
- Soft takeover ignores an incoming physical value until it crosses the software
  value. This stops a jump. The logic is a truth table in `willIgnore`.

### The common pattern

Both systems use the same shape:

- one value cell,
- one write path,
- the provenance as a flag,
- one policy for the case when the values diverge.

Neither system keeps two observer lists or three write verbs. The pi-Stomp
defects all sit where a write leaves the single write path.

## How mod-host sends values back

`mod-host/src/effects.c` sends the echoes from a feedback thread, not from the
audio thread. The audio thread appends a `POSTPONED_PARAM_SET` event to a
lock-free list and posts a semaphore.

The feedback thread drains the list in batches:

- `RunPostPonedEvents` moves the whole list to a local queue (`effects.c:1186`).
- It reads the queue backward, newest first (`list_for_each_prev`, `:1246`).
- `ShouldIgnorePostPonedSymbolEvent` drops an older duplicate of the same
  `(effect_id, symbol)` (`:1133`). The newest value of each port wins.

Results:

- **mod-host keeps only the newest value of each port per batch.** It already
  skips the older values. Intermediate values that pile up between two drains do
  not go out.
- **You cannot count the echoes.** A fast burst becomes one echo. The
  message `param_set %i %s %f` (`mod-host.h:62`) has no sequence number and no
  origin. There is no link from a send to an echo.
- **The echo is absolute and in order.** One TCP socket carries it. The last
  echo in order is always the current truth.

## The flicker

The flicker happens when a local preview runs ahead of the echo. An echo of an
older value arrives and repaints the value backward for one frame. The next echo
corrects it.

The flicker is bounded and self-correcting:

- mod-host keeps the newest value per batch, so the echo is never very old.
- mod-host and MOD-UI are single, serial writers, so the echo order matches the
  processing order.
- The flicker is a short backward move, not a jump, and never a wrong final
  value.

## Version 3.3.0 compared to HEAD

There is no `v3.3.0` git tag. The commit `8893ba19 "Cut v3.3.0"` marks it.

In v3.3.0, a fast scrub wrote through `reconcile`. `set_param` called
`plugin.set_param_value`, and that method calls `reconcile`
(`modalapi/plugin.py` at `8893ba19`). This gave three problems on a fast scrub:

1. The device could not tell a local edit from an echo. A lagging echo repainted
   the value backward with no guard.
2. `_confirmed` moved to every local value and every lagging echo. It thrashed.
3. `reconcile` notified the committed observers on every detent. A bound keycap
   thrashed.

HEAD switched the scrub to `preview` (`92051aa7 "Simplified path for
everything"`). `_confirmed` no longer thrashes. The keycap no longer thrashes.
The flicker from a lagging echo remains, but smaller.

**Is v3.3.0 strictly worse than HEAD? No.**

- On the scrub axis, HEAD is better and regresses nothing.
- The backpressure removal is a trade, not a pure win. v3.3.0 refused a send when
  the write buffer was above 8 KB. HEAD keeps an unbounded queue and drops the
  gate (`modalapi/websocket_bridge.py:266`). Under a stalled socket, the failure
  mode moves from "refuse the edit" to "the queue grows".
- HEAD is a work-in-progress branch with an audit that is not complete.

## The clobber question

The question was: which policy stops a local edit from a clobber by a late echo?

The answer from the protocol: no extra policy is needed. The echo is absolute,
in order, and from one serial writer. The last echo in order is the truth. A
timer (Zynthian) or a crossover (Mixxx) is a workaround for a system without this
guarantee. pi-Stomp has the guarantee.

The rule to keep: every local edit must reach mod-host, or self-commit when
MOD-UI skips the origin. Then the last echo always brings the device back.

## Ideas we examined

### A throttle from the ping/pong latency

The bridge already samples the round trip. `_monitor_latency` reads `ws.latency`
every 5 s into `peak_latency` (`modalapi/websocket_bridge.py:234`, `:41`).

Do not build a throttle from this signal. The reasons:

- The round trip measures how far MOD-UI is behind, not the write buffer. It
  spikes during a board load, where the device already refuses sends.
- The outbound queue already combines the sends. `_param_queue` is a
  `dict[Symbol, float]`. It sends one value per port per tick.
- A throttle does not stop the flicker. The preview moves on every detent, at any
  send rate.

If a real saturation shows in the logs, keep the write-buffer gate as a
combine-only flow control. It must not roll back the value. This is safe now,
because the scrub uses `preview`.

### A fix in MOD-UI

You cannot fix the flicker from the MOD-UI side without a cost.

- The worst flicker case is the tweak encoder. It sends a MIDI CC through
  `_publish_cc` (`modalapi/modhandler.py:1232`). mod-host has no client origin for
  a MIDI change. MOD-UI cannot skip an origin that does not exist.
- MOD-UI can skip the origin only on the `param_set` path (`_publish_plugin_param`,
  `:1237`). But a skip removes the reconcile. The device would lose the confirmed
  and clamped value. This is the reason the footswitch-less bypass path already
  self-commits.
- A sequence number would let the device find its own echo. But this changes the
  shared `param_set` format that the web UI reads. It is invasive.

### The coalesce rule (your rule)

The rule: if two echoes exist for one port, skip the older one. This is correct.
It is audio-safe, because `param_set` writes an LV2 control-input port. mod-host
samples that port once per block. An intermediate value that a new value
overwrites before the next block is never heard. (Triggers and notes use atom
ports, not `param_set`, so this rule cannot drop them.)

Where the rule applies:

- **mod-host already applies it on the echo path** (see above). This is done.
- **The device does not apply it on the inbound path.** `modhandler.py:956`
  drains `get_received_messages()` and reconciles every echo, one by one. Combine
  the batch to the last value per port, then reconcile once.

The inbound combine is the cheap, safe win:

- It needs no protocol change and no MOD-UI change.
- It limits the flicker to one repaint per port per tick.
- It has no swallow cost. The queue is in order, so the newest value is the
  truth. The device keeps the newest and drops the older. A web edit is the
  newest, so it survives.

## Recommendation (ranked)

1. **Advance `_confirmed` on a good commit.** This fixes defect 1.
2. **Route the range, volume, and analog writes through the operations.** This
   fixes defects 2, 3, and 4.
3. **Gate `_emit_midi` during a load.** This fixes defect 5.
4. **Rename "settled" to "committed".**
5. **Combine the inbound echoes per port per tick.** This is your rule. It is the
   safe fix for the flicker.
6. **Measure the MOD-UI drain latency first.** Log `ws.latency` during a real
   fast scrub. Read it from `journalctl`. If the latency is a few milliseconds,
   the flicker window is below one frame. Then step 5 is optional.
7. **Value-match confirmation (option B).** Hold the reconcile of a port while a
   preview is open, until an echo matches the last send. Use this only if a
   flicker remains after step 5. It has a cost: it can swallow a web edit during
   a scrub.

Do not build the ping-latency throttle. Do not fix the flicker from the MOD-UI
side.
