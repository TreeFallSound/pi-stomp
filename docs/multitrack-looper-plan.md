# Multitrack Looper Plan (LoopJefe LV2 + pi-Stomp)

Implementation fork lives at `~/dev/loopjefe-lv2` (renamed from a clone
of `mod-audio/sooperlooper-lv2-plugin`). The original working title
"multitrack looper" survives in the doc name; the canonical scope
is **three freely-recorded loop tracks of different lengths, locked
to a shared beat grid, controlled from footswitches alone**.

## Goal

Give pi-Stomp genuine RC-505-style live looping: several independently
recorded loop tracks of *different*, freely-played lengths (a 4-bar
chord loop, a 16-bar bassline recorded right after it, in either order)
that always land on a shared beat grid — using footswitches alone, and
optionally a richer external MIDI controller — without pi-Stomp becoming
an audio router or instrument coordinator. The reference point
throughout is Marc Rebillet's live workflow (Boss RC-505 + keyboard):
build a song from nothing, live, by layering loops of different lengths
that never drift apart, with nothing pre-declared about how long any
given loop "should" be.

## Why LV2/mod-host, not the standalone SooperLooper engine

We evaluated and rejected running the full `essej/sooperlooper` JACK
app (OSC-controlled, natively multitrack within one process), because:

- It sits **outside** mod-host's pedalboard, so it can't be freely
  positioned in the signal chain — no per-track pre/post-loop effects,
  which is a hard requirement (users need to choose what processes a
  track's input before it's recorded, and what processes its output
  after).
- It would require pi-Stomp to own audio routing (JACK port patching)
  and, if we want a MIDI-bindable control surface for digital
  instruments, instrument/MIDI coordination too — both explicitly out
  of scope. pi-Stomp is a control/monitoring layer over mod-host, not
  the thing coordinating real audio (the one deliberate exception is
  **blend mode**).

Instead: **three separate instances of the SooperLooper LV2 plugin**,
one per track, placed anywhere in a mod-host pedalboard like any other
plugin, each independently addressable via mod-ui's existing MIDI-learn
system.

## Researching the reference device: RC-505 (mkI) mode matrix

Before designing our own behavior we read the actual RC-505 mkI
owner's manual end to end. Four largely independent per-track settings
govern length/sync behavior:

| Axis | Options | What it controls |
|---|---|---|
| `Loop Sync` | ON / OFF | ON: playback start phase-aligns to the group's shared downbeat. OFF: loops independently, retriggers from its own bar 1. |
| `Measure` (only meaningful if `Loop Sync=ON`) | fixed number (1, 2, 4, 8...) / `AUTO` / `FREE` | Fixed: you type in an exact bar count ahead of time, recording is forced to fit it. `AUTO`: copies whatever the *first-recorded* AUTO track ended up being. `FREE`: *"set automatically, corresponding to the length of the recording"* — whatever you actually played, measured after the fact, nothing pre-declared. |
| `Quantize` (only active if something's already playing/synced to quantize against — rhythm on, an existing synced track, or MIDI sync) | `REC END` / `MEASURE` / `BEAT` | Governs *timing precision at the edges* — snaps record-start (always) and, depending on mode, overdub/playback boundaries to either a measure or a beat. |
| `Tempo Sync` | ON / OFF | ON: track plays at the shared phrase-memory tempo (may stretch). OFF: always plays at its own "original tempo," never stretched. |

Watching Marc's livestreams (a 4-bar loop, then a 16-bar loop recorded
immediately after, in that order, nothing hesitant or dialed-in
beforehand) is consistent with `Loop Sync=ON` + `Measure=FREE` +
`Quantize=BEAT` + `Tempo Sync=ON` — **not** a fixed/typed-in bar count
on either track. Nothing was pre-declared; both lengths were simply
measured from what he played, snapped to the beat grid, and it worked
because a shared tempo already existed underneath both recordings.

**Decision: hardcode exactly this combination.** Every track
permanently behaves as `Loop Sync=ON, Measure=FREE, Quantize=BEAT,
Tempo Sync=ON`. This is a deliberately narrow, opinionated first version
matching the one workflow we're targeting, not a general-purpose
emulator.

## Architecture: how freely-recorded loops of different lengths stay locked (Design A)

mod-host already implements the LV2 `time:` extension in full
(`mod-host/src/effects.c`). Two facts, confirmed by reading the source,
make this simpler than first assumed:

- **mod-host is the JACK timebase master** (`jack_set_timebase_callback`,
  `JackTimebase` — search the file). It always emits valid BBT
  (`pos->valid = JackPositionBBT`), so `bar`, `barBeat` (fractional
  0-indexed beat-within-bar), `beatsPerBar`, `beatUnit`, and
  `ticksPerBeat` are authoritative — not just `beatsPerMinute`.
- **While the transport is *rolling*, `pos.frame` advances every audio
  cycle, so the change-guard at `effects.c` (the forge site) fires
  every `run()`** — mod-host re-forges and pushes a fresh
  `time:Position` (`speed`, `frame`, `bar`, `barBeat`, `beatsPerBar`,
  `beatsPerMinute`, `ticksPerBeat`) into every subscribed instance
  **every block**. It only falls silent when the transport is *stopped*
  (frame frozen).

It reaches any plugin that declares an atom input port supporting it
(`lilv_port_supports_event(..., timePosition)` sets `HINT_TRANSPORT` on
that port). Critically, **this is a broadcast, not a wire**: pushed
automatically into every subscribed instance with zero manual patching
in mod-ui. Real and working today; nothing about it needs to change.

Given that shared clock (tempo + absolute phase) is established once,
*before* anyone hits record, each of the three LoopJefe instances
implements `FREE`-mode behavior **entirely locally**, with no
instance ever needing to know what another instance did.

**Quantization is to the measure (bar), not the beat.** This is the
load-bearing behavioral decision. For loops of *different* lengths to
stay musically locked, each loop's length must be an integer number of
*bars* and each must start on a downbeat — then a 16-bar loop is exactly
4× a 4-bar loop's cycle and their downbeats always coincide. Beat-only
quantize would permit a "4 bars + 1 beat" (17-beat) loop that never
lines up with a 16-beat loop's bars, defeating the whole multitrack-lock
goal. Measure alignment also matches the RC-505 faithfully: its record
quantize is `REC END` = "quantize to the measure start location" (mkI
manual p.15) and its count-in is a full **1-measure** count (p.19).
`beatsPerBar` is in the atom and persisted per-pedalboard, so this costs
nothing to read.

1. Each `run()` while rolling, read the latest `time:Position` from the
   `time_info` atom port: cache `frame`, `bar`, `barBeat`, `beatsPerBar`,
   `beatsPerMinute`, `speed`. Because mod-host hands us absolute phase
   every block, **we never integrate our own frame counter** — no drift.
   Derive `beat_length_samples = sample_rate * 60 / bpm` and
   `bar_length_samples = beat_length_samples * beatsPerBar` for boundary
   math.
2. On `record` press, snap the actual start to the **next bar boundary**,
   sample-accurate *within the block* by computing the sample offset to
   the next downbeat from the atom's `frame`/`bar`/`barBeat`. The window
   between press and that boundary is the count-in (up to a full bar).
3. Record for however long the footswitch is held — genuinely free,
   nothing pre-declared, nothing capped.
4. On `record` release, snap the stop so the total recorded length is the
   **nearest whole number of bars** (round to closest, not always up or
   down), computed from `bar_length_samples`. The resulting loop length
   is therefore always an exact whole number of bars, without ever having
   been told in advance how many.

Edge cases the implementer must handle: a release *before* the first
bar boundary has even been reached (recording never really started —
abort cleanly, leave the track empty); and rounding a sub-one-bar take
to a minimum of one bar rather than zero.

**Precondition — the transport must be rolling.** Beat-sync only works
while mod-host's transport is rolling (frame advancing); when stopped,
`frame`/`barBeat` are frozen and no boundaries can be found. Transport
rolling *and* BPM are **persisted per-pedalboard** (`timeInfo.rolling`,
`timeInfo.bpm`, applied at load), so the "shared clock exists before
anyone records" premise is satisfied by shipping the looper pedalboard
with `rolling: true` and a sensible default BPM. **The plugin must
fall back gracefully** when the transport is stopped or `speed == 0`:
behave as a free-running (unquantized) record rather than never
triggering.

**pi-Stomp does NOT own the transport.** Deliberate design choice: an
external MIDI controller (or a keyboardist's device) typically owns
play/stop, and we don't want to fight it. pi-Stomp is a pure transport
*slave* — it reads the beat grid (see "Beat-grid sync" below) and never
calls start/stop. Starting the transport is left to: the pedalboard's
persisted `rolling: true`, an external controller's transport button, or
a footswitch the *user* chooses to MIDI-learn onto the `:rolling`
global port. That last option is available but not required and not
something pi-Stomp drives on its own.

**This is why no recording-order constraint exists.** Any of the three
tracks can be recorded first, second, or third — each one independently
locks to the same absolute beat grid the moment it's recorded, because
the grid was established by the shared broadcast tempo, not derived
from whichever track happened to go first. This directly matches what
we saw Marc do: 4 bars then 16 bars, either could have gone first, both
land cleanly on the grid.

## Forking to `loopjefe-lv2`: identity changes

Because this changes real-time *behavior* under an existing LV2 URI
(LV2 URIs are meant to be permanent, stable contracts), we're not
patching `mod-audio/sooperlooper-lv2-plugin` in place. The repo has
been cloned and renamed to `loopjefe-lv2` at `~/dev/loopjefe-lv2`, git
remote `github.com:sastraxi/loopjefe-lv2` (the canonical build source
for now; to be moved to a TreeFallSound org repo later — the debpkg's
`config.sh` ref will need updating at that point). Renaming the repo
alone isn't enough — every place the old plugin's identity is baked in
needs to change too, or the built `.lv2` bundle will still silently
collide with (or shadow) the original `sooperlooper.lv2` on-device.

| Location | Current value | What needs to happen |
|---|---|---|
| `loopjefe/src/loopjefe.cpp:43` | `#define PLUGIN_URI "http://treefallsound.com/plugins/loopjefe"` | **Decided:** new URI namespace is `treefallsound.com/plugins`. Mono → `http://treefallsound.com/plugins/loopjefe`, stereo → `http://treefallsound.com/plugins/loopjefe-2x2`. This is the one change that actually matters for LV2 identity/compatibility; everything else below is bookkeeping around it. |
| `loopjefe/src/manifest.ttl` | Subject, `lv2:binary`, `rdfs:seeAlso` | Subject/binary/seeAlso filenames updated to match the renamed `.so`/`.ttl` (see directory renames below). |
| `loopjefe/src/loopjefe.ttl` | Plugin URI subject, `doap:name "LoopJefe"`, `mod:brand "MOD"` | `mod:brand "MOD"` dropped or changed to `"TreeFallSound"` — this isn't a MOD Devices-maintained plugin, keeping their brand label on it is misleading. |
| Directory names `loopjefe/`, `loopjefe-2x2/` | — | (Renamed from `sooperlooper/`, `sooperlooper-2x2/`.) The `Makefile` derives the plugin/bundle/binary name from `basename $(pwd)`, so the bundle name (`loopjefe.lv2`/`loopjefe-2x2.lv2`) cascades automatically. |
| Filenames `loopjefe.cpp`, `loopjefe.ttl` | — | (Renamed from `sooperlooper.cpp`, `sooperlooper.ttl`.) Not load-bearing (Makefile globs `src/*.cpp`), but renamed for clarity/consistency. |
| GPL copyright header (`loopjefe.cpp:1-27`) | `Copyright (C) 2002 Jesse Chappell` | **Preserved, not stripped** — this is GPL-licensed code and we're distributing a modified version. Fork/modification notice added alongside the original copyright; not replaced. `COPYING` (the GPL license file) stays as-is. |
| `modgui.ttl` (shipped separately, on-device only, not in this repo) | Points at the old `sooperlooper` URI | Needs its own new file pointing at the new URI, or the pretty pedal skin won't attach to the new plugin at all (it'll just fall back to mod-ui's generic control list — functionally fine, not blocking for v1). |
| `README.md` | — | States plainly: fork of `mod-audio/sooperlooper-lv2-plugin`, itself derived from Jesse Chappell's original SooperLooper (GPL), modified by TreeFallSound/pi-Stomp to add beat-synced multitrack recording. **Shipped.** |
| `lv2:minorVersion`/`lv2:microVersion` (`loopjefe.ttl`) | `0` / `1` | Reset from upstream's `0`/`9` — a version lineage that's ours, not a continuation of upstream's numbering. |

The `-2x2` (stereo) variant gets the identical treatment,
independently (it's a fully separate `PLUGIN_URI`/directory/bundle, not
derived from the mono one) — same namespace, `-2x2` suffix as shown
above.

## Plugin ports and the cycle/reset design

The plugin is the LADSPA→LV2 SooperLooper shim with three new things
added in `loopjefe-lv2`:

| Port | Type | Purpose |
|---|---|---|
| `time_info` | `atom:AtomPort`, `atom:Sequence`, `atom:supports time:Position` | Receives mod-host's per-block transport broadcast (frame, bar, barBeat, bpm, speed) — no pi-Stomp involvement, no mod-ui wiring. |
| `state` | `lv2:ControlPort`, `lv2:integer`, `lv2:enumeration` (5 scalePoints: Empty, Recording, Overdub, Playback, Stopped) | **Replaces** the old `play_pause`+`record` pair. Writes from any source (footswitch CC, plugin-internal, mod-ui REST) cycle the state machine; the plugin echoes its current state back via `param_set`, which pi-Stomp mirrors to the bound footswitch's LED. See "State machine" below. |
| `reset` | `lv2:ControlPort`, `lv2:integer` | Momentary trigger: when set non-zero, the plugin returns to `Empty` (state 0) and writes 0 back. Bound to the footswitch's longpress CC. |

`time_info` is the plugin's first atom/URID code. The shim's
`instantiate()` previously ignored its `features` argument; adding
`time_info` also means: request and store `LV2_URID_Map` from `features`
in `instantiate`; map the `time:Position`, `time:frame`, `time:barBeat`,
`time:beatsPerMinute`, `time:speed` URIDs; add the `connect_port` case
for the new port; and walk the atom sequence each `run()` (manual
`LV2_ATOM_SEQUENCE_FOREACH` / object-property iteration — no forge
needed on the read side). Reference implementations to mirror: the
LV2 book's `eg-metro` example (canonical minimal `time:Position`
consumer) and any DPF/MOD tempo-synced plugin on-device.

### State machine (plugin-owned, 5 states)

The plugin's internal `SooperLooper::state` is a per-sample state
machine inherited from the LADSPA original. With the `state` port
exposed, the cycle a single footswitch drives is:

| From state | Press | To state | Notes |
|---|---|---|---|
| Empty | press | Recording | Start quantizes to next downbeat (see Architecture) |
| Recording | press | Overdub | Length snaps to nearest whole bar |
| Overdub | press | Playback | |
| Playback | press | Stopped | Content retained, not playing |
| Stopped | press | Overdub | Re-enter overdub from the same content |

The key design decision: **the plugin, not pi-Stomp, owns this state
machine.** The footswitch is dumb — it sends a single CC on every
press. The plugin reads `state` from the port, sees that the value
changed externally (CC wrote a non-zero value, or just *any* value
different from what the plugin itself last wrote), advances the state,
and writes the new value back. mod-host echoes the write as
`param_set /graph/loopjefe_1 state N`, mod-ui relays it over WS, and
pi-Stomp's existing `plugin.set_param_value("state", N)` calls
`set_value(N)` on the bound footswitch — which the footswitch uses
to color its LED (Empty=unlit, Recording=red, Overdub=yellow,
Playback=green, Stopped=dim green).

This is the load-bearing simplification: pi-Stomp has zero per-track
state-machine code. The state lives in one place (the plugin), the
echo carries it to the LED, and the footswitch's existing
`param_set → set_value` chain does the work without any new
plumbing. Same path works for any external MIDI source (keyboard pads,
external foot controllers) bound to the `state` port in mod-ui.

**The `state` port's value-echoing contract** (the reason this design
works): mod-host emits `param_set /graph/<instance> <symbol> <value>`
over its feedback socket for *any* control port value change, whether
the change came from a MIDI-learned CC, a mod-ui REST/WS command, or
the plugin writing to it in `run()`. mod-ui relays verbatim. pi-Stomp's
existing `ParamSetMessage` handler in `modalapi/plugin.py:127` calls
`set_value(value)` on any bound controller. Confirmed: this chain
is fully generic, not `:bypass`-specific.

### Trigger vs. echo on the same port

The `state` port serves as both the cycle trigger (the footswitch CC
writes 127 to it) and the state publisher (the plugin writes the
new state back). The plugin distinguishes external from internal
writes by tracking the value it last wrote: a value read in `run()`
that differs from the last self-written value is an external trigger;
the plugin cycles and rewrites. A matching value means no trigger
happened this block.

This is the same pattern as a tap-tempo button: the port goes 0 →
momentary value → 0, and the plugin reacts to the momentary value.

### `reset` (longpress → clear)

`reset` is a separate, simple integer port. The footswitch's longpress
fires a *second* CC (different from the short-press CC). Both are
MIDI-learned in mod-ui: short-press CC → `state`, longpress CC →
`reset`. Pressing long: CC=127 sent, mod-host writes 127 to `reset`,
plugin resets to `Empty` (state 0) and writes 0 back. The `state`
echo lights the footswitch to off. The `reset` echo is ignored (its
value has no meaning beyond the trigger).

This requires a small pi-Stomp extension: the existing `longpress`
config in `pistomp/config.py` is a closed enum of pi-Stomp-internal
behaviors (`next_snapshot`, `previous_snapshot`, `toggle_bypass`,
`set_mod_tap_tempo`, `toggle_tap_tempo_enable`). It needs to grow
arbitrary "send this CC" actions, the same way short-press bindings
already target arbitrary CCs/parameters. **Deferred to a follow-up
PR** — the plugin can land first and be exercised with two separate
footswitches (one bound to `state`, one to `reset`) for testing.

### What stays out of v1

- `cycle_beats`, `quantize`, `measure_count`, `sync_target` ports —
  FREE+BEAT-quantize-to-the-bar is hardcoded, not configurable.
- Reverse, one-shot, multiply, insert, replace,
  configurable-Loop-Sync/Measure/Quantize/Tempo-Sync modes.
- `modgui` skin update for the new state-machine UX (the old skin
  still works against the new plugin; the new URI just needs the
  modgui file repointed at it, which is on-device-only and not
  blocking).

## What gets MIDI-learned through MOD-UI

Every control port on an LV2 plugin instance is automatically
learnable in mod-ui — bind any incoming MIDI CC or note to any port,
per instance, per pedalboard, entirely inside mod-ui's existing UI.
This was true before our changes and doesn't need new pi-Stomp code
to work. The live-performance bindings per track are:

- `state` — single CC drives the entire cycle. Bound to a pi-Stomp
  footswitch's short-press CC, or to a keyboard pad, or to anything
  else speaking MIDI into mod-host.
- `reset` — separate CC clears the track. Bound to a pi-Stomp
  footswitch's longpress CC, or to a dedicated pad.
- `dryLevel` — a natural target for an expression pedal or a
  controller knob (blend-mode-adjacent).

Two independent sources can feed these learned bindings, and they can
coexist:

1. **pi-Stomp footswitches**, which already emit raw MIDI CC
   (alternating 0/127 for toggle-style presses). No plugin awareness
   needed on pi-Stomp's side; it just sends CC, and mod-ui's learned
   binding routes it to the right port.
2. **Any external MIDI device** — a keyboard's own pads/buttons, a
   dedicated MIDI foot controller, anything speaking MIDI into
   mod-host — bound the exact same way, entirely inside mod-ui, with
   zero pi-Stomp involvement. A digital instrument's own loop-control
   pads can be bound directly to the same `state` port pi-Stomp's
   footswitches use, and multiple sources can be bound to the same
   port simultaneously (e.g. both a footswitch and a keyboard pad
   trigger `state` on track 2).

## Live UX with pi-Stomp's 4 footswitches (3 tracks + metronome)

Three tracks, one footswitch per track. The 4th switch is the
global metronome, reusing pi-Stomp's existing tap-tempo switch. This
discards the earlier "3 tracks + 1 modifier switch" design (with
chorded FSmod + FSn for clear and global-stop): the plugin's
5-state cycle makes a modifier switch unnecessary, and a single
footswitch per track is a much simpler learn.

| Switch | Gesture | Bound to | Action |
|---|---|---|---|
| FS1/2/3 | short press | `state` (per track) | Cycle Empty → Recording → Overdub → Playback → Stopped → Overdub → … |
| FS1/2/3 | long press | `reset` (per track) | Clear the track back to Empty |
| FS4 | (n/a; metronome is a global visual) | — | Per-beat flash driven by the beat-grid sync (see below) |

Two of the three real gesture tiers pi-Stomp's footswitches already
support are used:

1. **Single (short) press** — release before 500ms. Fires immediately,
   zero added latency. This is the tier every latency-sensitive,
   frequently-hit action lives on.
2. **Long press** — held ≥500ms. Fires a `longpress_callback`. Today
   the *set* of valid long-press actions is a fixed enum
   (`pistomp/config.py`); to support the looper's longpress-as-clear,
   this needs to grow arbitrary CC/parameter targets. **Deferred to a
   follow-up PR.**
3. **Chord** — long-press-based simultaneity. Not used by the looper
   (the modifier-switch design was removed). The chord machinery
   stays for non-looper features (`next_snapshot`, `previous_snapshot`,
   `toggle_bypass`, `toggle_tap_tempo_enable`).

## Beat-grid sync: crossing the RT barrier (transport slave)

pi-Stomp drives a synced metronome LED from the same beat grid the
plugin uses for its bar-quantize — with no audible click available
(the v3 codec has one shared stereo DAC; the "headphone" and "line"
jacks carry the *same* signal, so we cannot route a click to
phones-only like an RC-505; `mod-ui`/`mod-host` have no built-in
metronome). **The LED is the only feedback, so timing accuracy
matters and drift is the enemy.**

### The clock-domain problem (and JACK's answer)

The Pi's CPU clock and the codec's audio-sample clock are **different
crystals** and drift against each other. JACK's frame counter runs on
the *audio* clock; pi-Stomp schedules on the *system* clock. The bridge
is a real JACK primitive: **`jack_frames_to_time(client, frame)` →
`jack_time_t` (µs)**, backed by JACK's delay-locked loop that
continuously maps audio-frames ↔ system-microseconds. mod-host, as
timebase master, knows *which frame* is a downbeat (from its BBT:
`pos.bar`/`pos.beat`/`pos.frame`/`frame_rate`); JACK knows *what
system-time* that frame maps to. Neither pi-Stomp nor mod-ui has to
track consumption timing.

### Design: mod-host emits absolute-timestamped downbeats over WS

A pi-Stomp-side JACK client was rejected: it would drag the main
loop toward RT scheduling and the Python `jack` binding's
`transport_query()` **crashes** on-device — `unique_1 != unique_2`
ABI mismatch then a `munmap` abort, verified 20/20; the binding's
cdef also lacks `jack_frames_to_time`/`get_time`/`get_latency_range`,
so the frame→time conversion *must* happen in C anyway. Touches three
vendored repos, each additively:

1. **mod-host (C, RT-safe):** each process cycle, from the `pos` it
   already computes, detect a **downbeat** (bar-1) boundary crossing.
   Convert that boundary frame to an absolute system-time and push
   `{bar, t_us, bpm, beatsPerBar}` through the **existing
   `rtsafe_memory_pool` postponed-event queue** (the same RT→non-RT
   pipe used for `param_set` feedback — no new RT machinery). Emit
   **on the downbeat only** (not every beat): one anchor + BPM lets the
   consumer extrapolate the whole grid, so worst-case re-anchor
   interval is one bar. The timestamp is in **`CLOCK_MONOTONIC`** in
   microseconds, back-dated to the actual downbeat frame (not "now")
   so consumer phase is immune to feedback/relay/WS-drain latency.
2. **mod-ui (Python):** relay as a new WS line `beat_sync <bar>
   <t_us> <bpm> <bpb>` on the socket pi-Stomp already drains.
3. **pi-Stomp (Python):** parse (small `ws_protocol.py` add). On
   receipt, `t_us` is the exact monotonic time the downbeat occurred.
   Anchor the grid; drive the LED against
   `time.clock_gettime(CLOCK_MONOTONIC)`. **No JACK client, no
   subprocess, no RT** on pi-Stomp.

**Why the absolute timestamp is the whole trick:** a "downbeat happened
NOW" message would be smeared by WS + relay + the 10ms drain. An
absolute `t_us` is immune — however late pi-Stomp reads it,
`phase = now − t_us` recovers the true elapsed time. Transport jitter
only delays when pi-Stomp *first learns* the grid, never the phase it
computes.

### Audio-interface latency (answering "does frames_to_time handle it?")

**No.** `jack_frames_to_time` maps a frame to system-time at JACK's
engine/driver boundary (anchored to the ALSA hardware IRQ). It does
**not** add the playback-port buffering + codec latency between that
boundary and the physical output jack. Here that residual is
period×nperiods = 64×2 = 128 frames ≈ **2.67 ms**, plus a few frames
of DA7212 codec latency ≈ **~4–5 ms total**. That is far below the
~20–40 ms audio-visual sync threshold the eye can detect, so the
correction is **optional, not critical** — the loops themselves are
the only audible reference and 5 ms against them is imperceptible. If
we want exactness anyway it's cheap: add
`jack_port_get_latency_range(out, JackPlayback)` (µs) to `t_us` in
mod-host. **Drift, not this constant offset, is the thing that
actually matters** — and the per-downbeat re-anchor bounds drift to at
most one bar.

## LED feedback

### Metronome (FS4, delivered)

FS4 (the tap-tempo switch) is the global visual metronome. It's
driven by the beat-grid anchor: a short **~80 ms flash per beat**
(≈8 main-loop ticks at 100 Hz), with the downbeat flashed brighter.
Concretely, the LED strip pixel and the GPIO LED on FS4 are both
flashed for 80ms after each beat boundary crossing, with the strip
color at full white (255, 255, 255) on a downbeat and a slightly
dimmer white (180, 180, 180) on regular beats — the two different
RGB values render as visually distinct whites against the strip's
global `LED_BRIGHTNESS = 0.19`. The GPIO LED has no per-channel
brightness, so it just goes on for both.

When the transport stops, mod-ui sends `transport 0 …`, which pi-Stomp
uses to clear the grid immediately. The 5-second stale timeout in
`BeatGrid` is a safety net for a crashed mod-host that produces no
events at all. With no anchor, the metronome driver leaves the
pixels off; the taptempo's own set_led path (or the next category
update) restores FS4's normal state.

### Per-track state color (FS1/2/3, deferred to plugin-side PR)

Each track's LED should mirror the plugin's `state` value, per the
RC-505 track-button convention:

| LED | State |
|---|---|
| Unlit | Empty (no phrase) |
| Red | Recording |
| Yellow | Overdubbing |
| Green | Playing |
| Dim green | Stopped-but-has-content |

The LED color is **derived from the enumeration's scalePoint labels**,
not from a hardcoded value→color table. The plugin's TTL declares the
`state` port with `lv2:enumeration` and 5 scalePoints whose `rdfs:label`
is one of the conventional names:

```
:state a lv2:InputPort, lv2:ControlPort ;
    lv2:integer ;
    lv2:enumeration ;
    lv2:scalePoint [ rdfs:label "Empty"     ; ] ;
    lv2:scalePoint [ rdfs:label "Recording" ; ] ;
    lv2:scalePoint [ rdfs:label "Overdub"   ; ] ;
    lv2:scalePoint [ rdfs:label "Playback"  ; ] ;
    lv2:scalePoint [ rdfs:label "Stopped"   ; ] .
```

The label→color mapping lives in the **plugin customization** system
(`modalapi/plugin_customization.py` + `plugins/customization.py`),
which is the right home for "this plugin's bound parameters have a
non-trivial value→LED-color mapping." A new optional field on
`PluginCustomization`:

```python
# modalapi/plugin_customization.py
LedColorFn = Callable[[Footswitch, float], tuple[int, int, int] | None]

@dataclass(frozen=True)
class PluginCustomization:
    panel_cls: type[PluginPanel] | None = None
    display_name: str | None = None
    display_name_fn: Callable[[Plugin], str | None] | None = ...
    subtitle_fn: Callable[[Plugin], str | None] | None = ...
    intercept_shortpress: bool = False
    tile_active_color: tuple[int, int, int] | None = None
    tile_border: RectBorder | None = None
    extra_data: PluginExtraData | None = None
    footswitch_led_color_fn: LedColorFn | None = None  # NEW
```

The function is called from `Footswitch.set_led` whenever a
`footswitch_led_color_fn` is set on the bound plugin's customization;
it returns an `(r, g, b)` triple for "lit in this color" or `None`
for "unlit." If the customization isn't set, `set_led` falls through
to the existing category-color logic (`Pixel.set_color_by_category`
+ on/off), so all existing plugins (and `:bypass`-bound footswitches)
behave exactly as today.

The loopjefe customization is then a small package under
`pi-stomp/plugins/loopjefe/`:

```python
# pi-stomp/plugins/loopjefe/__init__.py
from modalapi.plugin import Plugin
from modalapi.plugin_customization import PluginCustomization
from plugins.customization import register
from pistomp.footswitch import Footswitch

LOOPJEFE_URIS = (
    "http://treefallsound.com/plugins/loopjefe",
    "http://treefallsound.com/plugins/loopjefe-2x2",
)

_LABEL_TO_COLOR = {
    "Empty":     None,           # unlit
    "Recording": (255,   0,   0),
    "Overdub":   (255, 255,   0),
    "Playback":  (  0, 255,   0),
    "Stopped":   (  0,  80,   0),  # dim green
}

def _state_to_color(footswitch: Footswitch, value: float) -> tuple[int, int, int] | None:
    param = footswitch.parameter
    if param is None or not param.enum_values:
        return None
    for scale_point in param.enum_values:
        if float(scale_point.get("value", 0)) == value:
            return _LABEL_TO_COLOR.get(scale_point.get("label", ""))
    return None

register(
    *LOOPJEFE_URIS,
    customization=PluginCustomization(footswitch_led_color_fn=_state_to_color),
)
```

The value arriving via `param_set` is converted to a color in three
steps: `value → scalePoint (via enum_values lookup) → label
(scalePoint.rdfs:label) → color (_LABEL_TO_COLOR[label])`. A
scalePoint whose label isn't in the map returns `None` (unlit) and
the footswitch falls back to its existing category color. **The
plugin author controls what the LED shows by choosing scalePoint
labels** — not by being known to pi-Stomp via a URI prefix or a
hardcoded value table. Any plugin that declares a `state`-like port
with the conventional labels will get the right colors without
further pi-Stomp changes (just register a customization).

**Generalizes beyond `:bypass`.** The function takes
`(footswitch, value)` — it doesn't care which port. Today's
`param_set → Footswitch.set_value → Footswitch.set_led` chain runs
for any MIDI-mapped parameter; the customization just gets to
override the LED color logic. For `:bypass` (binary; the category
color is fine) the customization simply isn't set, and the existing
logic applies unchanged. For multi-state ports like loopjefe's
`state`, the customization takes over. A plugin that wanted a
gradient-color display for a continuous parameter could register a
customization that maps `(lo, value, hi)` to a color — same hook,
no new infrastructure.

The wiring on the param_set side already exists: when a
`param_set /graph/loopjefe_1 state 2.0` arrives, `plugin.set_param_value`
in `modalapi/plugin.py:127` calls `set_value(2.0)` on the bound
footswitch controller, which calls `set_led(...)`, which consults
the customization. The deferred work is therefore small: add the
new customization field, plumb a back-reference from `Footswitch`
to the bound `Plugin` (set in `_bind_controller_to_param`), and
update `set_led` to call `footswitch_led_color_fn` before the
default path. A `param_set … state` echo with the right scalePoint
labels will already work correctly today (the existing `set_value`
ignores the value if the parameter's type is `Type.ENUMERATION`,
but the enumeration's scalePoint labels are already parsed and
available via `Parameter.get_enum_value_list()`). What is *not*
done is the customization hook in `set_led` and the loopjefe
customization itself — both small. Until the loopjefe plugin
exposes `state` (deferred), this is moot.

### Count-in pulse (was speculative, removed)

The earlier plan called for "pulsing red during a record-pending
window" — visual substitute for RC-505's audible 1-measure count-in
that we can't reproduce (single shared DAC, no phones-only bus, no
mod metronome). With the plugin owning the state machine and the
press-to-record gap being at most one bar (~1-2s at typical tempos),
the visual transition is now: green (Stopped) → brief black → red
(Recording). The plugin goes from Stopped to Recording on the next
downbeat, and the LED is driven by the `state` echo. The
"pulsing red during the gap" was tied to pi-Stomp's pre-state-machine
design; it's removed.

## What changes when more MIDI is available

Everything above still applies — footswitches are just one MIDI source
among possibly several bound to the same ports. More MIDI availability
buys:

- **More tracks addressable without a modifier switch.** A keyboard
  with enough pads can bind directly to N tracks' worth of `state`
  ports, no chord addressing needed at all.
- **Real secondary actions without the 500ms+ long-press cost.** Undo,
  redo, per-track dry level — each gets its own dedicated pad or
  knob instead of being squeezed into chords.
- **Expression control** — a pedal or mod wheel bound to `dryLevel`
  live, which is the one place pi-Stomp's "blend mode" is explicitly in
  scope to help coordinate.
- Bass/keys/pads on the same device don't have to be sacrificed for
  loop control — with enough MIDI surface, looping and playing can be
  simultaneous and physically separate, which footswitches alone can't
  offer since your feet are busy but so is everything else.

## Plugin state-machine touchpoints (`loopjefe/src/loopjefe.cpp`)

The engine is a per-sample state machine (`pLS->state`) inherited from
the LADSPA original. The five `STATE_*` values reachable from the new
`state` port (the rest are dead code with no path that sets
`state` or `nextState` to them):

| State | # | Meaning |
|---|---|---|
| `STATE_OFF` | 0 | Empty (no phrase) |
| `STATE_TRIG_START` | 1 | armed, waiting to begin recording — **bar-start quantize injection point** |
| `STATE_RECORD` | 2 | actively recording |
| `STATE_PLAY` | 4 | playing the loop |
| `STATE_OVERDUB` | 5 | overdubbing |

(`STATE_TRIG_STOP` (3) and `MULTIPLY`/`INSERT`/`REPLACE`/`DELAY`/
`MUTE`/`SCRATCH`/`ONESHOT` (6-12) are dead code — no control path ever
sets `state` or `nextState` to any of them.)

`STATE_OFF` here is "empty," not "stopped." The 5-state UX described
in the table above is implemented as a thin wrapper that maps the
`state` port's value to the internal `pLS->state` transitions: Empty
↔ Recording ↔ Overdub ↔ Playback ↔ Stopped ↔ Overdub. "Stopped with
content" and "Empty" are externally distinct but internally the
plugin returns to `STATE_PLAY`/loops; the "stopped" surface state is
maintained by the wrapper so the LED reflects it.

Touchpoints:
- **`state` port write → cycle**: setting `state` to a value different
  from the last plugin-written value advances the state machine and
  writes the new value back. The 5-state cycle is implemented in the
  wrapper; the underlying `STATE_*` transitions are unchanged from the
  earlier free-form `play_pause`/`record` design.
- **Start quantize** (`STATE_TRIG_START` handler): same as before —
  computes the sample offset to the next bar boundary from the cached
  transport (`barBeat`, `beatsPerBar`, `beatsPerMinute`), reuses the
  existing block-local state-transition idiom (advance `lSampleIndex`
  to the trigger sample, push the new loop chunk, set `state =
  STATE_RECORD`, then `break` so the outer `while` loop immediately
  re-dispatches into the `STATE_RECORD` case for the remainder of
  the block — sample-accurate, no dead time). Falls back to
  triggering immediately when the transport isn't rolling.
- **Length finalize on stop**: the real "stop recording" event is the
  `*(plugin->record) <= 0.0 && plugin->recording` branch in `run()`'s
  control-reading section (not `STATE_TRIG_STOP`, which is
  unreachable). Round-to-nearest-bar is applied there, gated on
  `pLS->state == STATE_RECORD` so overdub stops (which inherit their
  source loop's length verbatim) are left alone. The `state`-port
  transition from Recording → Overdub happens here.
- **`reset` port write → Empty**: any non-zero value on `reset`
  triggers a hard reset of the loop's audio content and
  `state`-wrapper variable back to `STATE_OFF` / `Empty`.

Both `loopjefe/` and `loopjefe-2x2/` carry a full copy of this file —
every change is applied twice (the dirs are independent bundles, not
shared code). The stereo variant's `STATE_TRIG_START` steps its outer
sample loop by `NUM_CHANNELS` while indexing input frames directly by
that same stepped index, inconsistent with `STATE_RECORD`'s
per-sample loop just below it — pre-existing, left as-is; the
bar-boundary trigger reuses the same loop shape the amplitude trigger
it replaced had.

### How to verify (before touching pi-Stomp)

The plugin is fully testable via mod-ui MIDI-learn, no pi-Stomp code:

1. Build locally: `make` at repo root produces `loopjefe.lv2`/
   `loopjefe-2x2.lv2`. Install to a MOD host (MOD Desktop, or scp to
   the device's `~/.lv2/`).
2. Load a pedalboard with the plugin. Set transport **rolling** with
   a known BPM/`beatsPerBar` (persist `timeInfo.rolling: true` or hit
   play).
3. MIDI-learn a CC (any source) to `state`.
4. **State echo:** press the footswitch. The plugin's `state` value
   should advance (0 → 1 → 2 → 3 → 4 → 2 → 3 → 4 → …) and be
   reflected in the mod-ui plugin UI.
5. **Start quantize:** trigger `state` at a random moment mid-bar;
   confirm the Empty → Recording transition lands on the next
   downbeat, not instantly. Watch the loop-length readout — first
   pass may need `fprintf` debugging of the computed boundary frame.
6. **Length quantize:** record for ~3.5 bars then trigger the
   Recording → Overdub transition; confirm the resulting loop length
   is an integer number of bars (4), not 3.5.
7. **Multitrack lock (the real test):** on two instances, record a
   4-bar loop and a 16-bar loop in *either order*; confirm their
   downbeats stay coincident over many repeats (this is the whole
   point).
8. **Fallback:** stop the transport, trigger a transition; confirm
   it free-runs (transitions immediately, unquantized) instead of
   hanging.
9. **Reset:** trigger `reset`; confirm the track clears and the
   `state` value goes back to 0.
10. Confirm the modgui still loads with the added `state` and `reset`
    ports (or falls back to the generic control list without
    erroring).

## Packaging: `loopjefe-lv2` debian package (`pi-gen-pistomp`)

Ships to devices via the existing apt-repo OTA flow, mirroring the
LV2 package pattern already used by `cabsim-lv2` / `veja-*-cab-lv2`:

1. **`config.sh`** — add `LOOPJEFE_LV2_REPO` / `LOOPJEFE_LV2_REF`
   alongside the existing `CABSIM_LV2_REPO/REF`. Repo =
   `https://github.com/sastraxi/loopjefe-lv2`, ref = `main` (or a
   pinned tag once cut).
2. **`debpkgs/loopjefe-lv2/`** — new package dir cloned from the
   cabsim template:
   - `build.sh` — clone the ref, `record_upstream_sha`, copy
     `debian/` over, `dpkg-buildpackage -b -us -uc`, `move_to_cache`.
   - `debian/control` — `Source: loopjefe-lv2`, `Build-Depends:
     debhelper-compat (= 13), lv2-dev` (no fftw/sndfile — this
     plugin has no such deps), `Architecture: arm64`.
   - `debian/rules` — `override_dh_auto_build`/`install` calling the
     repo's top-level `Makefile` (which recurses into both
     `loopjefe/` and `loopjefe-2x2/`), installing both `.lv2` bundles
     under `usr/lib/lv2/`. No modgui to copy for v1.
   - `debian/changelog` — initial `loopjefe-lv2 (0.1-1) trixie`
     entry.
3. **Ship it** — bump the package version via `bump-version.sh`,
   push `pi-gen-pistomp#main`; `build-deb.yml` builds the `.deb` and
   `publish-apt-repo.yml` updates the apt index (per CLAUDE.md's
   "Shipping a new pi-stomp version" flow, same mechanism).

Blocked only on the plugin building cleanly and the renamed/patched
tree being pushed to the build-source remote — this step comes last.

## Open questions

- Mid-song tempo *change* under measure-quantize: the plugin's bar
  math and pi-Stomp's grid extrapolation both assume constant tempo
  since the last anchor. Fine for the target workflow; revisit if
  tempo automation is ever needed (JACK `bar_start_tick` handles it
  authoritatively).
- Design B (explicit master→follower `AUTO`-style length mirroring)
  is deferred, not rejected — worth revisiting if a workflow ever
  needs one track's length forced to exactly match/multiply another's
  rather than everything independently landing on the shared beat
  grid.
- Plugin-side `state` port: should the value be 0-indexed (0..4) or
  1-indexed (1..5)? LV2 enumeration values are arbitrary; the
  pi-Stomp LED mapping and the wrapper's internal transitions need to
  agree. **Resolved for v1: 0-indexed** (Empty=0, Recording=1,
  Overdub=2, Playback=3, Stopped=4) — easier to compute `bar *
  bpb + beat_in_bar` style arithmetic.

---

## Appendix: Delivered and remaining work

A snapshot of the in-progress state across the three repos. Everything
listed as "delivered" is implemented in the working tree but
**uncommitted**; "deferred" is on the roadmap but not yet started.

### `~/dev/loopjefe-lv2` (the plugin)

| Item | Status | Notes |
|---|---|---|
| Identity rename (`sooperlooper*` → `loopjefe*`, new URI namespace) | **Delivered** | Uncommitted; staged in working tree |
| GPL copyright preservation + fork notice | **Delivered** | Header in `loopjefe.cpp` |
| `time_info` atom port + LV2_URID_Map wiring + `readTimeInfo()` | **Delivered** | Mono and `-2x2` variants |
| Bar-boundary quantize in `STATE_TRIG_START` | **Delivered** | Computes sample offset to next downbeat each block |
| Length snap to nearest whole bar on stop | **Delivered** | Gated on `pLS->state == STATE_RECORD` |
| Free-run fallback when transport stopped | **Delivered** | |
| `state` port (5-value enumerated integer) replacing `play_pause`+`record` | **Deferred** | Separate PR |
| 5-state cycle wrapper (`Empty`/`Recording`/`Overdub`/`Playback`/`Stopped`) | **Deferred** | Separate PR; the 4-state `STATE_*` internals are unchanged |
| `reset` port (longpress → clear) | **Deferred** | Separate PR |
| modgui skin update for the new URI | **Deferred** | On-device-only, not blocking for v1 |
| `debpkgs/loopjefe-lv2/` in `pi-gen-pistomp` | **Not started** | Blocked on plugin tree landing |

### `~/dev/mod-host`

| Item | Status | Notes |
|---|---|---|
| `POSTPONED_BEAT_SYNC` event type in `src/effects.c` | **Delivered** | Uncommitted; adds struct, event-type, and switch case |
| Downbeat crossing detection in `UpdateGlobalJackPosition` | **Delivered** | Back-dates `t_us` to actual downbeat frame via `bar_beat`/`beat_length_frames` math; reuses existing `rtsafe_memory_pool` |
| `g_last_beat_sync_bar` reset on stopped/no-BBT | **Delivered** | Lets a fresh roll re-anchor immediately |
| `clock_gettime(CLOCK_MONOTONIC)` for the anchor `t_us` | **Delivered** | Unconditionally correct; sidesteps any `jack_time_t`-vs-monotonic question |
| `jack_port_get_latency_range` correction (optional ~5ms offset) | **Not started** | Optional, not critical per the latency analysis |

### `~/dev/mod-ui`

| Item | Status | Notes |
|---|---|---|
| `beat_sync` relay in `process_read_message_body` | **Delivered** | Uncommitted; `mod/host.py` 7-line addition |
| Browser-side `ws.onmessage` handling | **N/A — no change needed** | `html/js/host.js` silently ignores unrecognized commands; `beat_sync` falls through the if/else chain without matching any branch, no crash, no error. `triggerDelayedReadyResponse(false)` clears the data-ready handshake timer (harmless, next `data_finish` re-arms it). |
| HMI-side handling | **N/A — no change needed** | The HMI WebSocket is inbound-only (HMI sends commands *to* mod-ui, doesn't receive broadcasts). |

### `~/dev/pi-stomp`

| Item | Status | Notes |
|---|---|---|
| `BeatSyncMessage` typed message in `ws_protocol.py` | **Delivered** | Uncommitted; one-line docstring: "`t_us` is back-dated to the actual downbeat frame." |
| `parse_message` case for `beat_sync` | **Delivered** | Uncommitted; matches the format `beat_sync <bar> <t_us> <bpm> <bpb>` |
| `pistomp/beatsync.py` (`BeatGrid` + `TickState`) | **Delivered** | Uncommitted; new file. `on_anchor` / `clear` / `tick`. Re-anchors on each `beat_sync`; ticks return `(is_anchored, is_flashing, is_bar_start, bpm, bpb)`. No docstrings — the field names carry the meaning. |
| `tests/test_beatsync.py` (19 tests) | **Delivered** | Uncommitted; covers anchor/tick/flash/clear/stale/re-anchor/frozen-dataclass behaviors |
| `tests/test_ws_protocol.py` (6 parser tests) | **Delivered** | Uncommitted; happy path, edge cases |
| Dispatch `BeatSyncMessage` / `TransportMessage(rolling=False)` in `_handle_ws_message` | **Delivered** | Uncommitted; `modhandler.py` |
| `_drive_metronome` in `poll_indicators` (FS4 strip + GPIO LED flash) | **Delivered** | Uncommitted; `modhandler.py`. Always-on (no pedalboard gate). Strip pixel: `(255,255,255)` on downbeat, `(180,180,180)` on regular beat. GPIO LED: `on()` for any flash. |
| `pyright` + `ruff` clean, 1019 tests pass | **Verified** | Zero regressions |
| Per-track state-cycle tracking (was plan item 1) | **Removed — moved to plugin** | Plugin owns the state machine. The 5-state `state` port echo drives the footswitch LED through the existing `param_set → set_value` chain. No pi-Stomp code needed. |
| Per-track LED state coloring (was plan item 2) | **Deferred to plugin-side PR** | Add a `footswitch_led_color_fn` field to `PluginCustomization` (in `modalapi/plugin_customization.py`), plumb a back-reference from `Footswitch` to the bound `Plugin`, and have `Footswitch.set_led` consult the customization before falling through to the existing category-color path. Then register the loopjefe customization at `pi-stomp/plugins/loopjefe/__init__.py` with a `LABEL → COLOR` map keyed off the `state` port's scalePoint labels (`Empty`/`Recording`/`Overdub`/`Playback`/`Stopped`). The customization hook is general — any plugin with a non-trivial value→LED-color mapping can register a function. See the "Per-track state color" section. |
| Longpress → secondary CC (was plan item 3) | **Delivered** | `longpress` now accepts `{midi_CC: N}` alongside the existing named-group form (string/list); `Footswitch.set_longpress` dispatches between them, and `Handler._handle_footswitch` sends a momentary CC=127 via a consolidated `_emit_midi(controller, value, cc=...)` on the shared `Handler` base (previously duplicated per-subclass). The looper's longpress-as-clear binding (short-press CC → `state`, longpress CC → `reset`) can now be configured directly in `config.yml`, no mod-ui workaround needed. |
| v1 mod.py (mono LCD, no ledstrip) support | **Explicitly out of scope** | v1 has no LED strip; the metronome LED has no v1 surface. The `BeatSyncMessage` parser still recognizes the message; v1's `_handle_ws_message` simply has no `isinstance(msg, BeatSyncMessage)` branch and ignores it. No code change needed in v1. |
