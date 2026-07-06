# Plan: Generic plugin-owned footswitch behavior (LED + press semantics), loopjefe first consumer

## Context

pi-Stomp is gaining an RC-505-style multitrack looper (`loopjefe-lv2`) controlled
from footswitches. The plugin was redesigned and the earlier plan
(`docs/multitrack-looper-plan.md`) is now materially stale in two ways that break
pi-Stomp's assumptions:

- **`state` is now a read-only OUTPUT control port with 9 states** (Empty=0,
  Record Arm=1, Recording=2, Record Close=3, Playback=4, Stopped=5, Overdub
  Arm=6, Overdub=7, Overdub Close=8). Output ports reach pi-Stomp as `output_set`,
  **not** `param_set` — and pi-Stomp currently drops *all* `output_set` at the WS
  bridge (`websocket_bridge.py:207`, an audio-meter flood). So the old
  "`param_set` echo → footswitch LED" path no longer fires for `state`.
- **Control is via edge-triggered, self-clearing input trigger ports**: `advance`
  (short-press), `reset` (long-press), plus `undo`/`redo`. pi-Stomp's short-press
  today alternates `127/0` (`handler.py:168-170`), so every other press sends `0`
  — a dead no-op for a rising-edge trigger. The self-clearing behavior is
  documented in `loopjefe-lv2/docs/state-machine-redesign.md`, `CLAUDE.md`,
  `src/state_machine.h` (implementation), and tested in
  `tests/test_state_ports_contract.cpp`. `undo`/`redo` are NOT self-clearing
  (the host must clear them).

Rather than hardcode looper knowledge into the handler, the goal is a **generic
plugin-customization mechanism**: when a footswitch is MIDI-bound (via mod-ui
MIDI-learn, reflected in the pedalboard TTL) to a plugin's parameter, pi-Stomp
looks up that plugin's registered `PluginCustomization` and lets it own the
footswitch's behavior — press semantics (momentary vs toggle), which of the
plugin's OUTPUT ports to subscribe to, and per-tick LED rendering (color as a
function of cached state, beat-synced pulsing). Any future plugin with a
non-trivial control surface registers a customization with **zero new handler
code**.

The FS4 `beat_sync`→`BeatGrid` metronome already works and is unaffected; this
plan generalizes the *per-track* footswitch behavior and adds the `output_set`
plumbing it needs. Confirmed product decisions: LED color is a pure function of
the 9-state value (matching loopjefe's MODGUI, **not** per-track colors); all
active states beat-pulse (bright on beat, brightest on the bar downbeat, dim
between), including the blue shoulder states; Stopped is steady grey; Empty is
off.

## Key facts established during exploration

- **Footswitch → Parameter back-ref exists** (`Controller.bind_to_parameter` sets
  `self.parameter`, `controller.py:89`), giving `fs.parameter.instance_id` +
  `fs.parameter.symbol`. **Footswitch → Plugin does NOT exist** — only the reverse
  `plugin.controllers.append(controller)` (`controller_manager.py:90`). We do NOT
  add a forward ref; the behavior factory `footswitch_behavior_fn(plugin)` receives
  the plugin and captures whatever it needs (instance_id, customization fields) on
  the behavior object itself.
- **Every footswitch always has a behavior.** `ControllerManager.bind()` attaches
  either a plugin-provided behavior or a `DefaultFootswitchBehavior` (toggle
  semantics, category color, no WS subscriptions). This eliminates all `None`
  guards on `fs.behavior` in the driver and dispatch code.
- **`set_led()` and `set_category()` no longer drive the pixel.** The old baked-in
  behavior (`set_led` called `pixel.set_enable`, `set_category` called
  `pixel.set_color_by_category`) was removed. Pixel rendering is now entirely
  owned by `_drive_footswitch_leds` in `poll_indicators`. `set_led` only handles
  the GPIO LED (for immediate press feedback); `set_category` only stores the
  category for the default behavior to read.
- **Binding happens in `ControllerManager.bind()`** (`controller_manager.py:67-101`),
  called on every pedalboard/state change; loopjefe's `advance` port (MIDI-learned)
  gets a TTL `midi:binding`, so the short-press footswitch binds to
  `parameter.symbol == "advance"` on the loopjefe instance.
- **`PluginCustomization`** (`modalapi/plugin_customization.py:30`) is a frozen
  dataclass looked up by URI (`plugins/customization.py` `register`/`lookup`) and
  stored on `Plugin` at load (`pedalboard.py:228-237`). Existing consumers under
  `plugins/*/__init__.py` (~30 packages).
- **LED surfaces**: `fs.pixel` (RGB `Pixel`, `ledstrip.py:51` — `set_color` stores,
  `set_enable(True)` renders) and `fs.led` (GPIO on/off/blink). `set_led`
  (`footswitch.py:115`) only toggles enable; color comes from `set_category` →
  `Category.get_category_color`.
- **Per-tick LED driver today is only `_drive_metronome`** (`modhandler.py:343`),
  hard-targeting the taptempo FS with hardcoded colors, called from
  `poll_indicators` (~20ms). `BeatGrid.tick(now)` → `TickState(is_anchored,
  is_flashing, is_bar_start, bpm, bpb)` (`beatsync.py`). This is the insertion
  point for a generic per-footswitch driver.
- **WS receive**: `output_set ` frames dropped cheaply by prefix at
  `websocket_bridge.py:207` (on the `WebSocketWorker` thread) *before* parsing.
  `param_set /graph/<inst> <sym> <val>` and `output_set /graph/<inst> <sym> <val>`
  share shape. No `OutputSetMessage` type exists; no subscription concept exists.
  `_handle_ws_message` (`modhandler.py:531`) is an isinstance ladder; ParamSet is
  matched to a plugin by O(n) scan on `instance_id`.

## Design overview

Introduce a **`FootswitchBehavior`** — a per-binding object a plugin's
customization creates at bind time and attaches to the bound footswitch. It owns:

1. **Press semantics** — `momentary: bool` (short-press sends a one-shot `127`
   instead of toggling). Checked by `_handle_footswitch`; no separate
   `momentary_symbols` field needed on `PluginCustomization`.
2. **Output subscriptions** — `output_subscriptions() -> Iterable[str]`: symbols
   on *this instance* whose `output_set` the behavior wants (e.g. `["state"]`).
3. **Value intake** — `on_output(symbol, value)` caches incoming state.
4. **Per-tick color** — `led_color(beat: TickState) -> tuple[int,int,int] | None`:
   returns the color for this tick (None = off). The behavior never computes
   brightness — that's the driver's job.
5. **Per-tick style** — `led_style(beat: TickState) -> LedDisplayStyle`: returns
   `SOLID` or `METRONOME` for this tick. Defaults to `SOLID`.

`PluginCustomization` grows one optional field:
- `footswitch_behavior_fn: Callable[[Plugin], FootswitchBehavior] | None = None`
  (stored with `compare=False, hash=False` like the other `*_fn` fields). When set,
  the factory is called at bind time; when unset, a `DefaultFootswitchBehavior` is
  used instead. Every footswitch always has a behavior — no `None` guards needed.

The WS bridge gains an **atomically-swappable interesting-set** of
`"instance/symbol"` keys; subscribed `output_set` frames survive the prefix drop,
flow through a new `OutputSetMessage`, and are dispatched to the owning behavior.
De-registration is automatic — the interesting-set is fully recomputed on every
`ControllerManager.bind()` call (pedalboard load/rebind), and the old set is
atomically swapped out.

A new **`_drive_footswitch_leds(beat)`** in `poll_indicators` computes the beat
tick once and asks every behavior-bearing footswitch to render.

## Changes by area

### 1. Momentary short-press (standalone, required)

- `pistomp/handler.py` `_handle_footswitch` short-press arm (`~167-170`): if
  `fs.behavior.momentary`, emit `_emit_midi(fs, 127)` every press (no `toggled`
  flip). Otherwise keep the existing toggle behavior. No plugin back-ref needed
  — the behavior carries `momentary`.
- Longpress already sends momentary `127` (`handler.py:152`) — unchanged; covers
  `reset`.

### 2. Behavior attachment (every footswitch always has a behavior)

- `pistomp/footswitch.py`: add `self.behavior: "FootswitchBehavior | None = None`
  in `__init__`; clear it in `clear_pedalboard_info` (`footswitch.py:187`).
  `set_led()` no longer drives `fs.pixel`; `set_category()` no longer calls
  `pixel.set_color_by_category`. Pixel rendering is entirely owned by the
  per-tick driver.
- `pistomp/controller_manager.py` `bind()` (`~85-90`, the `isinstance(controller,
  Footswitch)` block): if `plugin.customization.footswitch_behavior_fn` is set,
  call it; if it returns a behavior, attach it; otherwise fall back to
  `DefaultFootswitchBehavior(controller)`.
- Type-only import of `FootswitchBehavior` (use `TYPE_CHECKING` / string
  annotations).

### 3. `FootswitchBehavior` protocol + `DefaultFootswitchBehavior` + `LedDisplayStyle`

- New `modalapi/footswitch_behavior.py`:
  ```python
  class LedDisplayStyle(Enum):
      SOLID = auto()       # steady color (default)
      METRONOME = auto()   # driver pulses brightness on the beat grid

  class FootswitchBehavior(Protocol):
      @property
      def momentary(self) -> bool: ...
      def output_subscriptions(self) -> Iterable[str]: ...
      def on_output(self, symbol: str, value: float) -> None: ...
      def led_color(self, beat: TickState) -> tuple[int, int, int] | None: ...
      def led_style(self, beat: TickState) -> LedDisplayStyle: ...

  class DefaultFootswitchBehavior:
      """Built-in: toggle semantics, category color, no WS subscriptions."""
      def __init__(self, fs: Footswitch) -> None: ...
  ```
  **Key separation:** the behavior returns *what color + which style*, never the
  per-tick brightness. The generic driver (§5) owns the metronome gradient. A
  behavior varies only its returned *color* over time (e.g. loopjefe returns a
  distinct color when `measure_number == 0`). No `LedRender` dataclass — two
  methods are cleaner.
- Add `footswitch_behavior_fn` to `PluginCustomization`
  (`modalapi/plugin_customization.py:30`).

### 4. `output_set` subscription filter + typed message + dispatch

- `modalapi/websocket_bridge.py`:
  - Add `self._interesting: frozenset[str] = frozenset()` and
    `set_interesting_outputs(keys: frozenset[str])` (atomic reference swap — no
    lock needed for replace + membership read under the GIL).
  - In `_receive_messages` (`~207`), replace the unconditional `output_set ` drop
    with: cheap `split(" ", 3)`, build key `inst_no_prefix + "/" + symbol`, keep
    only if in `self._interesting`, else `continue` (drop as today).
- `modalapi/ws_protocol.py`: add `OutputSetMessage(instance, symbol, value)`
  dataclass + a `case ["output_set", path, rest]` in `parse_message` (mirror the
  `param_set` arm at `:290`), add to the `WebSocketMessage` union.
- `modalapi/modhandler.py`:
  - After `ControllerManager.bind()` (pedalboard load/rebind), assemble the
    interesting-set by scanning footswitches with behaviors:
    `{f"{fs.parameter.instance_id}/{sym}" for fs in ... for sym in
    fs.behavior.output_subscriptions()}` and push via
    `ws_bridge.set_interesting_outputs(...)`.
  - Add an `isinstance(msg, OutputSetMessage)` arm to `_handle_ws_message`
    (`~531`): find footswitch(es) whose behavior stores a matching `instance_id`
    (captured at construction from the plugin), call
    `behavior.on_output(msg.symbol, msg.value)`.

### 5. Generic per-tick LED driver

- `modalapi/modhandler.py` `poll_indicators` (`338`): compute
  `beat = self.beat_grid.tick(_now_us())` **once**; pass it to the existing
  `_drive_metronome(beat)` (FS4) and to a new `_drive_footswitch_leds(beat)`.
- `_drive_footswitch_leds(beat)`: for each `fs` in `hardware.footswitches`, call
  `color = fs.behavior.led_color(beat)` and `style = fs.behavior.led_style(beat)`.
  Every footswitch always has a behavior — no `None` guard needed.
  - `SOLID` → show `color` steadily (or off when `color is None`).
  - `METRONOME` → the driver scales `color` brightness by the beat envelope
    (below), so the pulse is uniform across all metronome LEDs regardless of
    plugin. When the grid is unanchored (`not beat.is_anchored`) → show `color`
    steadily (no pulse).
  Apply to `fs.pixel` (`set_color(scaled); set_enable(True)` / `set_enable(False)`
  when `None`) and `fs.led` (`on()`/`off()`), mirroring `_drive_metronome`.
- **Beat envelope / gradient.** To make `METRONOME` a real gradient (not a square
  80ms flash), extend `BeatGrid.tick`/`TickState` (`pistomp/beatsync.py`) to expose
  a normalized within-beat phase (e.g. `beat_phase: float` in `[0,1)` = elapsed
  fraction of the current beat) plus the existing `is_bar_start`. The driver maps
  phase→brightness with a decay envelope (bright at phase 0, decaying toward the
  next beat), brightest on the bar downbeat. This is a small additive change; the
  existing `is_flashing`/`_drive_metronome` path stays working.
- Keep `_drive_metronome` (FS4, not plugin-bound) separate for now; both share the
  one `beat` tick computed in `poll_indicators`. Note possible future unification.

### 6. loopjefe plugin package (`plugins/loopjefe/__init__.py`)

- `register(*LOOPJEFE_URIS, customization=PluginCustomization(
    display_name="LoopJefe",
    footswitch_behavior_fn=make_loopjefe_behavior))`.
  URIs: `http://treefallsound.com/plugins/loopjefe` and `.../loopjefe-2x2`.
- `LoopjefeBehavior`: `momentary = True`;
  `output_subscriptions() -> ("state", "measure_number")`; caches `state:int` and
  `measure_number:int` from `on_output`. `led_color(beat)` and `led_style(beat)`
  — **no brightness math** (the driver owns the gradient):
  - **Style by state**: Empty(0) → `(None, SOLID)` (off); Stopped(5) →
    `((80,80,80), SOLID)` (steady grey); all other states → `(color, METRONOME)`.
  - **Base color by state** (sensible defaults, tune later): Record Arm(1)/Record
    Close(3) → blue `(0,80,255)`; Recording(2) → red `(255,0,0)`; Playback(4) →
    green `(0,255,0)`; Overdub Arm(6)/Overdub Close(8) → blue `(0,80,255)`;
    Overdub(7) → orange `(255,140,0)`.
  - **Loop-downbeat color swap**: when `measure_number == 0` (the loop's own
    first measure), return a **distinct variant** of the state color (e.g. a
    whiter/brighter tint) so the loop downbeat reads differently from the rest of
    the loop. This is the *only* thing `measure_number` changes — pure color
    selection; the pulse envelope still comes from the driver/BeatGrid.

### 7. Cross-repo: loopjefe LV2 — new `measure_number` output + monitored outputs

In `loopjefe-lv2` (**both** `loopjefe/` and `loopjefe-2x2/` bundles — independent
copies):
- **New `measure_number` OUTPUT control port**: `lv2:ControlPort, lv2:OutputPort`,
  `lv2:integer`, min 0, default 0 — the current measure index *within the loop*
  (0 = the loop's own downbeat/first measure). Add to the port enum, `connect_port`
  case, and write it each `run()` from the loop's phase math (the plugin already
  computes loop bar/phase via `phaseMapAbsBeats`/`phaseMapPhase01` in
  `transport.h`). Bump the port count and `lv2:index`es; update the `.ttl` in both
  bundles.
- **Monitor both outputs**: add `state` **and** `measure_number` to the modgui's
  `modgui:monitoredOutputs` so mod-host monitors them and emits `output_set`
  (mod-ui auto-sends `monitor_output` for `extinfo['monitoredOutputs']` on plugin
  add). Without this, pi-Stomp never receives either. Confirm the modgui.ttl block.
- Rebuild/install both bundles; verify with lilv/`make validate`.
- Update `README.md`'s port table (already stale — still lists the old 5-state
  enum) to the current 9-state `state` + `measure_number`.

## Tests

- `tests/test_ws_protocol.py`: `output_set` parses to `OutputSetMessage` (happy +
  edge).
- `tests/test_websocket_bridge.py` (or extend): interesting-set membership — a
  subscribed `output_set` survives, a non-subscribed one is dropped; empty set
  drops all (regression: today's behavior).
- New `tests/test_loopjefe_behavior.py`: state→color/style map for all 9 states —
  Empty→`(None, SOLID)`, Stopped→`(grey, SOLID)`, active states→`(color,
  METRONOME)`; `measure_number == 0` returns the distinct downbeat-variant color,
  non-zero returns the base color. (Brightness/pulse is the driver's job — tested
  separately.)
- `tests/test_beatsync.py` (extend): `TickState.beat_phase` advances 0→1 across a
  beat and resets on crossing; `is_bar_start` on the downbeat.
- Driver test (extend `test_modhandler` or new): `METRONOME` render scales
  brightness by `beat_phase` (bright at phase 0, dim near 1), brightest on
  `is_bar_start`; `SOLID` render is steady; unanchored METRONOME → steady color.
- `tests/test_handle_footswitch_longpress.py` / `test_footswitch.py`: momentary
  short-press emits `127` every press (no toggle) when
  `fs.behavior.momentary`; unaffected footswitches still toggle.
- Full suite: `uv run pytest`; `pyright` zero + `ruff` clean (per CLAUDE.md).

## Verification (end-to-end)

1. Unit + type/lint gates green (`uv run pytest`, pyright, ruff).
2. **Emulator / device**: load a pedalboard with a loopjefe instance, MIDI-learn a
   footswitch's short-press CC → `advance`, long-press CC → `reset`; set transport
   rolling with a known BPM.
   - Press short repeatedly → `state` advances (0→1→2→…); the footswitch LED shows
     the mapped color and **pulses on the beat** (brightest on downbeat); Stopped =
     steady grey; Empty = off.
   - Long-press → `reset` clears the track → LED off.
   - Confirm only the subscribed `output_set /graph/<inst> state` flows (others
     still dropped) — check WS debug logs for volume.
3. Confirm FS4 global metronome still flashes unchanged (single beat tick shared).

## Open questions / future

- **Tap-tempo footgun (document, not code):** the plugin aborts an in-progress take
  if `transport_bpm` diverges from the sampled `capture_bpm` mid-record. Hitting
  FS4 tap-tempo *while recording* kills that loop. Set tempo before recording.
- **Possible unification** of `_drive_metronome` into `_drive_footswitch_leds`
  later (FS4 as an implicit taptempo behavior).
