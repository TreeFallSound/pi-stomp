# R3 — Binding truth and reconciliation

## 1. Summary

Binding truth in pi-Stomp today is **dispersed across four stores** that never
merge into a single authoritative table: (1) the pedalboard TTL's
`lv2:port … midi:binding` parsed by LILV into `Parameter.binding`
(`modalapi/pedalboard.py:175-184`); (2) the hardware `controllers` dict keyed
`"{channel}:{CC}"`, populated from the default + per-pedalboard config overlay
(`pistomp/hardware.py:303,348,488`); (3) `ControllerManager.bind()`, which is
the one place the two meet — a plugin parameter's `binding` string is used as a
lookup key into `controllers` (`pistomp/controller_manager.py:74-90`); and (4)
`Hardware.external_routing`, an identity-keyed side table that decides whether a
given controller's CC actually goes out the virtual ALSA port or a named
external port (`pistomp/hardware.py:63-67,391-414`). There is **no merged
"effective binding table"**; the handler never sees a single view. The LCD does
**not** independently recompute bindings — it renders purely from
`current.analog_controllers` (built by `ControllerManager`) and the
`Footswitch.parameter`/`Footswitch.category` fields set during bind
(`pistomp/lcd320x240.py:233-248,747-782,1014-1140`). LCD drift risk is low
*today* but the architecture has no fence keeping it that way. The handler is
the *de facto* route authority (its `_emit_midi` consults `external_routing`),
but it is not the *binding* authority — that role is split between the TTL
parser and `ControllerManager` with no single owner.

## 2. Where binding truth lives today

End-to-end data flow (file:line cited at each hop):

```
┌─ TTL parse ────────────────────────────────────────────────────────┐
│ modalapi/pedalboard.py:175-184  LILV reads lv2:port midi:binding    │
│   → binding = "%d:%d" % (channel, controllerNumber)                 │
│   stored on Parameter(binding=...) at pedalboard.py:203,216         │
│   plugin.parameters[symbol] = Parameter(...)  (one per port)        │
└────────────────────────────────────────────────────────────────────┘
                              │
┌─ Pedalboard load ─────────────────────────────────────────────────┐
│ modalapi/modhandler.py:745  reload_pedalboard → LILV parse          │
│ modhandler.py:set_current_pedalboard (≈785)                         │
│   cfg = {bundle}/config.yml  (per-pedalboard overlay)               │
│   hardware.reinit(cfg)  →  hardware.py:133-161                      │
└────────────────────────────────────────────────────────────────────┘
                              │
┌─ Config overlay (hardware side) ──────────────────────────────────┐
│ pistomp/hardware.py:133-161  Hardware.reinit                        │
│   __init_footswitches(self.cfg)   default CCs → controllers[ch:cc]   │
│   __init_encoders(self.cfg)       default tweak CCs → controllers    │
│   __apply_midi_routing(self.cfg)  external_routing rebuilt          │
│   then if cfg: repeat for the per-pedalboard overlay                │
│   hardware.py:451-519  __init_footswitches can rewrite CC, clear CC, │
│     set preset, set color, set longpress — per pedalboard           │
│   hardware.py:416-422  __apply_midi_routing sets external_routing  │
└────────────────────────────────────────────────────────────────────┘
                              │
┌─ Bind (the one merge point) ─────────────────────────────────────┐
│ modhandler.py:878  bind_current_pedalboard                          │
│   → ControllerManager.bind(current)  controller_manager.py:47-65    │
│     _bind_plugin_parameters (67-101):                                │
│       for each plugin param with .binding:                          │
│         controller = hw.controllers.get(param.binding)              │
│         if hw.is_external(controller): warn + SKIP   ← collision     │
│         controller.bind_to_parameter(param)                          │
│         plugin.controllers.append(controller)                        │
│         if Footswitch: set_category(plugin.category)                │
│         else: current.analog_controllers["inst:param"] = display    │
│     _bind_volume_encoders: surface VOLUME encoders                   │
│     _bind_external_controllers (115-152):                            │
│       for each controller in hw.controllers that is_external:        │
│         bind a SYNTHETIC Parameter (External instance_id)            │
│         current.analog_controllers["ch:cc"] = External entry         │
└────────────────────────────────────────────────────────────────────┘
                              │
┌─ Live MIDI-learn (post-load) ─────────────────────────────────────┐
│ modalapi/ws_protocol.py:143-156  MidiMapMessage(instance,symbol,ch,cc)│
│ modhandler.py:616-618  _apply_midi_binding(...)                     │
│   handler.py:224-241  updates param.binding in place, re-binds the   │
│   controller, redraws LCD                                          │
└────────────────────────────────────────────────────────────────────┘
                              │
┌─ LCD render (pure consumer) ──────────────────────────────────────┐
│ lcd320x240.py:233-248  draw_main_panel                                │
│   draw_analog_assignments(current.analog_controllers)  line 246      │
│   draw_footswitches()  line 248  reads self.footswitches (passed in   │
│     via link_data) and each fs.parameter / fs.category                │
│ lcd320x240.py:1014-1140  draw_analog_assignments: pure read of the    │
│   display dict built by ControllerManager                            │
│ lcd320x240.py:747-782  draw_footswitches: pure read of fs.parameter,  │
│   fs.preset_callback_arg, fs.toggled, fs.category                    │
└────────────────────────────────────────────────────────────────────┘
```

**Key observations:**

- The TTL parser produces *one string per parameter* (`"channel:CC"`) and
  attaches it as `Parameter.binding`. It does not know whether a matching
  hardware controller exists — that's `ControllerManager.bind`'s job.
- `ControllerManager.bind` is **the only place that joins the two worlds**.
  It is the *de facto* merge authority but it is not owned by the handler; it
  lives in `pistomp/controller_manager.py` and is invoked by the handler
  (`modhandler.py:878`).
- `Hardware.reinit` rebuilds `controllers` **and** `external_routing` *before*
  `bind` runs, so by the time `bind` executes, the CC space is already
  partitioned into "internal" vs "external" without `bind` ever voting.
- The handler's `_emit_midi` (`modhandler.py:305-314`) is a *pure consumer* of
  `external_routing`: it asks `hardware.external_port_name(controller)` and
  routes accordingly. The handler does not own the routing decision; it
  enforces it.

## 3. The `controllers` dictionary

**Declaration:** `pistomp/hardware.py:57`
```python
self.controllers: dict[str, Controller] = {}
```

**Keying scheme:** `"{midi_channel}:{midi_CC}"` — a decimal-formatted string.
- Analog controls: `hardware.py:303` (`create_analog_controls`)
- Encoders: `hardware.py:348` (`create_encoders`)
- Footswitches: `hardware.py:488` (`__init_footswitches`, on CC set)

The key is the **same string format** produced by the TTL parser
(`pedalboard.py:180-184`), which is what makes the `controllers.get(binding)`
lookup in `ControllerManager._bind_plugin_parameters` work
(`controller_manager.py:77`).

**Value:** a `Controller` instance — `AnalogMidiControl`, `EncoderController`,
or `Footswitch`. Each carries `.midi_channel`, `.midi_CC`, `.parameter` (the
currently-bound `Parameter` or `None`), and (for footswitches) `.category`,
`.lcd_color`, `.preset_callback_arg`, `.toggled`.

**Important subtlety:** the dict is **identity-keyed on channel+CC, not on the
controller object**. Two different physical controllers cannot share a key —
the second `__init_footswitches` call for the same CC will **overwrite** the
first (see the `TODO problem if this creates a new element?` comment at
`hardware.py:489`). There is no protection against CC collision within config;
the last writer wins.

**What it does NOT contain:**

- Any notion of *which plugin parameter* a CC is bound to. That mapping lives
  in `Controller.parameter` (one-way; the plugin side keeps the reverse mapping
  in `plugin.controllers: list[Controller]`, `plugin.py:60`).
- Any notion of external routing. That is `external_routing`, a separate dict
  (see §5).
- Any notion of "shadowed" or "context-active" bindings. A controller in the
  dict is always live; panels shadow by consuming events upstream in the
  cascade, not by mutating the dict.

## 4. Config overlay mechanics

`Hardware.reinit(cfg)` (`hardware.py:133-161`) runs **twice** for each pedalboard
load — once with `self.cfg` (the default), then once with `cfg` (the
per-pedalboard overlay). The structure:

```
1. self.cfg = default_cfg.copy()
2. external_routing.clear()           ← rebuilt from scratch
3. __init_midi_default()               ← set channel from default
4. chord_helper.rebuild(callbacks)
5. __init_footswitches(self.cfg)      ← default CCs land in controllers
6. __init_encoders(self.cfg)          ← default tweak CCs land in controllers
7. __init_external_midi(self.cfg)
8. __apply_midi_routing(self.cfg)    ← external_routing populated for default
9. if cfg is not None:                ← the per-pedalboard overlay
   9a. __init_midi(cfg)               ← may change midi_channel
   9b. __init_footswitches(cfg)       ← may rewrite/clear CCs, set preset, color, longpress
   9c. __init_external_midi(cfg)
   9d. __init_encoders(cfg)
   9e. __apply_midi_routing(cfg)     ← external_routing re-populated for overlay
10. register longpress groups with chord resolver
```

### Binding-related config keys

Sourced from `setup/config_templates/default_config_pistomptre.yml` and
`default_config_pistompcore.yml`:

| Key | Path | Effect on bindings |
|-----|------|--------------------|
| `hardware.midi.channel` | `hardware.py:351-359` | Determines the `channel` half of every `"{ch}:{CC}"` key. v1 had a "LAME bug" offset. |
| `hardware.footswitches[].midi_CC` | `hardware.py:481-489` | Overwrites the footswitch's CC; rewrites the `controllers` key. `NONE` clears it (removes from dict, `hardware.py:444-449`). |
| `hardware.footswitches[].preset` | `hardware.py:492-503` | Replaces MIDI binding with a preset callback; **clears the CC** (`hardware.py:493`). |
| `hardware.footswitches[].longpress` | `hardware.py:516-517` | Adds longpress chord membership; not a binding per se but a parallel action path. |
| `hardware.footswitches[].color` | `hardware.py:512-513` | Sets `fs.lcd_color` — a display attribute, not a binding, but the LCD reads it. |
| `hardware.footswitches[].disable` | `hardware.py:506-509` | Suppresses the footswitch without removing it. |
| `hardware.encoders[].midi_CC` | `hardware.py:345-348`, `hardware.py:404-406` | Overwrites the encoder's CC; rewrites the `controllers` key (via `__route_section`). |
| `hardware.encoders[].midi_channel` | `hardware.py:407-409` | Per-encoder channel override; rewrites the `controllers` key. |
| `hardware.encoders[].longpress` | `hardware.py:521-536`, `hardware.py:534-536` | Adds longpress callback; parallel action path. |
| `hardware.encoders[].midi_port` | `hardware.py:383-389, 410-414` | Routes the encoder's CC to an external ALSA port instead of the virtual Through. |
| `hardware.analog_controllers[].midi_CC` | `hardware.py:284, 300-304` | Sets the analog control's CC and `controllers` key. |
| `hardware.analog_controllers[].midi_port` | `hardware.py:383-389, 410-414` | Routes the analog CC to an external port. |
| `hardware.analog_controllers[].autosync` | `hardware.py:297-298` | Sends current value on pedalboard load; not a binding but affects state sync. |
| `hardware.footswitches[].midi_port` | `hardware.py:410-414` (set_cc=False for FS) | Routes the footswitch's CC to an external port. **Note:** footswitch CCs are owned by `__init_footswitches`, not `__route_section` (see `hardware.py:402` comment). |
| `hardware.external_midi.*` | `hardware.py:434-442` | One-shot messages sent on pedalboard load; not a binding, but a side-channel MIDI output. |
| `blend_snapshots[]` | `modhandler.py:830-855` | Per-pedalboard blend-mode config; claims an analog input. See §7 collision matrix. |

### Overlay semantics

The overlay is **not a deep merge** — it's **re-execution** of the same
initializer functions on the overlay cfg. `__init_footswitches(cfg)` re-runs
over the **existing** `self.footswitches` list (created once during
construction, `hardware.py:195-268`) and rewrites fields in place
(`hardware.py:457` loop). This means:

- A footswitch that was given a CC by the default config keeps that CC if the
  overlay is silent about it. (`fs.set_midi_CC(cc)` only fires if `Token.MIDI_CC
  in f`, `hardware.py:481`.)
- A footswitch given `preset: UP` in the overlay has its CC cleared
  (`hardware.py:493`) — preset mode and MIDI-CC mode are mutually exclusive.
- The `controllers` dict entry is mutated to match: `__clear_footswitch_midi_cc`
  removes the old key (`hardware.py:444-449`), `set_midi_CC` adds the new one
  (`hardware.py:488`).

The overlay runs **before** `ControllerManager.bind`. So the sequence is:
config overlay finalizes the CC space → LILV's `param.binding` strings try to
find matching controllers → bind wires them up. **The TTL parser never sees
the overlay.** A pedalboard TTL that MIDI-learns CC 62 (footswitch 2's default)
will bind to footswitch 2; a pedalboard overlay that reassigns footswitch 2 to
`preset: UP` will clear CC 62, and the TTL binding will dangle (CC 62 not in
`controllers` → `bind` silently skips it, `controller_manager.py:77-79`).

## 5. External MIDI — what `external_midi` knows and doesn't

`modalapi/external_midi.py` defines `ExternalMidiManager` and the
`EXTERNAL_INSTANCE_ID = "External"` sentinel. Two distinct concerns:

### 5a. `ExternalMidiManager` (the message sender)

`external_midi.py:42-225`. Holds:
- `midi_ports: dict[str, rtmidi.MidiOut]` — cache of opened external ports
- `messages: dict[str, list[MidiMessage]]` — per-port message lists sent on
  pedalboard load (`send_messages_for_pedalboard`, line 199)
- `send_raw(port_name, message)` — one-shot CC send (line 182)

What it knows: **ALSA client names**. `_find_port_index` matches a device name
case-insensitively against the client-name prefix of each rtmidi port string
(`external_midi.py:88-96`). It does **not** know what CCs a device owns, what
parameters it controls, or whether a CC collides with another device's. It is a
dumb pipe: "send these bytes to this named port."

### 5b. `Hardware.external_routing` (the routing authority)

`hardware.py:63-67`:
```python
self.external_routing: dict[Controller, RoutingInfo] = {}
```
Keyed by **controller identity** (not by CC). Populated by
`__apply_midi_routing` (`hardware.py:416-422`) via `__route_section`
(`hardware.py:391-414`) which reads the `midi_port` field of each config
section. Value is a `RoutingInfo(destination, port_name)` dataclass
(`controller.py:33-44`).

The handler's `_emit_midi` consults this:
```python
port_name = self.hardware.external_port_name(controller)  # modhandler.py:310
if port_name is not None and self.external_midi is not None:
    if self.external_midi.send_raw(port_name, cc): return
self.hardware.midiout.send_message(cc)  # fallback to virtual
```

### What external_midi does NOT know

1. **Whether an external device's CC space overlaps another external device's.**
   Two external ports can both listen on CC 70; `external_midi` will happily
   send CC 70 to whichever controller is routed. There's no global CC registry.
2. **Whether an external device's CC space overlaps the virtual Through port.**
   The virtual port carries the hardware's own CCs (60-63, 70-71, 75...). An
   external device on the same CC is invisible to pi-Stomp; the controller is
   routed one way or the other, never both.
3. **Whether the external device actually has a parameter on that CC.** Pi-Stomp
   emits and hopes. There is no echo, no reconciliation, no
   `ParamSetMessage`-style feedback from external devices. The
   `EXTERNAL_INSTANCE_ID` synthetic parameter exists only so the LCD has
   something to show (`controller_manager.py:115-152`); it is a fiction.
4. **That the external device exists at all, until the first send.**
   `__resolve_midiout` calls `external_midi.open_port(port_name)` *eagerly*
   during reinit (`hardware.py:388`), but `open_port` only checks that an ALSA
   port with that client name is enumerable *now* — it doesn't poll for later
   arrival beyond the 5-second `_open_failures` backoff
   (`external_midi.py:106-108`).

### The "unknown controller on the same CC" question

This is the crux of A5's "what we badge when we don't know what's on the other
end" rule. Today:

- A controller in `controllers` is either internal (routed to the virtual
  Through) or external (routed to a named ALSA port). The decision is binary
  and complete at reinit time.
- An **external controller** gets the synthetic `External` parameter and an
  "External" category in `analog_controllers` (`controller_manager.py:115-152`).
  The LCD shows it with a light-blue tint and a `"{port_name}:{cc} (external
  MIDI)"` subtitle (`lcd320x240.py:1060-1064`).
- A controller that is **internal but shares a CC with an external device** is
  invisible to pi-Stomp — there is no record of external devices' CC maps.
- A controller that is **configured external but the named port is not
  connected** falls back to the virtual port at send time
  (`modhandler.py:311-314`), but the LCD still shows it as external. This is a
  *display lie*: the badge says external, the CC goes to mod-host.

So the existing "unknown controller" rule is: **we badge what we routed, not
what we know is on the other end.** A5's "generic MIDI badge, not a guess"
directly addresses this — today we guess (we show the configured port name as
if it's authoritative) and the guess can be wrong (port gone, device silent).

## 6. LCD drift analysis

**Finding: the LCD is currently clean — it does not independently compute
bindings.** It is a pure consumer of two data sources:

### 6a. `current.analog_controllers` (built by ControllerManager)

`lcd320x240.py:246` calls `draw_analog_assignments(self.current.analog_controllers)`.
`draw_analog_assignments` (`lcd320x240.py:1014-1140`) iterates the dict by
`id` field, looks up the actual `AnalogMidiControl`/`EncoderController` instance
by id from `hardware.analog_controls + hardware.encoders` (line 1029-1034) only
for **progress-bar tracking**, not for binding derivation. The name, category,
and "external"/"volume"/"unassigned" status all come from the dict value
(`AnalogDisplayInfo`) that `ControllerManager._bind_plugin_parameters` and
`_bind_external_controllers` populated.

There is **one local computation** worth flagging: line 1051 produces
`control_type = Token.EXPRESSION if i == 0 else Token.KNOB` with the comment
`# HACK cuz we don't know type of unmapped`. This is a **display heuristic for
unmapped slots**, not a binding derivation — it guesses the *icon shape* for an
empty slot based on convention (slot 0 = expression pedal). This is a drift
risk if the hardware has a non-standard slot-0 control, but it does not invent
bindings; it just draws an icon.

### 6b. Footswitch list (passed by reference via `link_data`)

`lcd320x240.py:233-236` stores `self.footswitches` (a reference to
`hardware.footswitches`). `draw_footswitches` (`lcd320x240.py:747-782`) iterates
the **hardware's** footswitch list and reads:
- `fs.preset_callback_arg` → preset mode label
- `fs.parameter` → plugin-bound label (via `footswitch_label`, line 728-745)
- `fs.category` → color (set by `ControllerManager._bind_plugin_parameters:95`
  → `controller.set_category(plugin.category)`)
- `fs.toggled` → active state
- `fs.taptempo` → tap-tempo label

Every one of these fields is set by `ControllerManager.bind` or
`__init_footswitches`. **The LCD never consults `controllers` or
`param.binding` directly.** It reads the live `Footswitch` object's state.

### 6c. `update_footswitch` (live MIDI-learn path)

`lcd320x240.py:784-800` — called from `handler._redraw_after_binding`
(`handler.py:264-266`) when a `MidiMapMessage` arrives. It reads
`footswitch.parameter` and `footswitch.category` to update the label and
color. Again, pure consumer; no independent binding derivation.

### 6d. Where drift *could* creep in

The LCD is clean today, but the **fence is convention, not architecture**:

1. **The LCD reads `hardware.footswitches` and `hardware.analog_controls`
   directly** (e.g. `lcd320x240.py:757, 1029`) rather than reading through a
   handler-owned view. A future panel that walks `hardware.controllers` to draw
   badges would be computing a binding view independently of
   `ControllerManager`'s `analog_controllers` — a drift source.
2. **The `Icon.object` field** (`lcd320x240.py:1031, 1070, 1128`) stores a
   reference to the live `AnalogMidiControl` / `EncoderController` /
   `BlendMode` for progress-bar polling (`lcd320x240.py:307-334`). This is a
   *live object reference* the LCD holds across frames. If the controller is
   re-bound (reinit), the LCD's `w_controls` list is rebuilt by
   `draw_analog_assignments` on the next `draw_main_panel` call, so stale
   references are cleared — but only on a full panel rebuild, not on a partial
   re-bind. The `_redraw_after_binding` path calls `draw_analog_assignments`
   again (`handler.py:265-266`), so it's covered.
3. **The BlendMode substitution** (`lcd320x240.py:1056-1073`): the LCD
   substitutes a `BlendMode` object for the analog control in the `Icon.object`
   slot when `analog_control.id == active_blend_mode.config["input_id"]`. This
   is a **local decision** — but it reads from `self.handler.active_blend_mode`
   (line 1056), so it's still handler-authoritative. The risk is that this
   substitution is *display-only*: the underlying `analog_control` still emits
   MIDI CCs on movement (the blend `handle_event` intercepts first
   `blend/manager.py`, so the CC is shadowed). The badge currently shows the
   blend snapshot name, not the parameter — which is correct for blend mode but
   is a *different binding* than `analog_controllers` records. **This is the
   one place the LCD renders a binding that `ControllerManager` did not
   record.**

### 6e. v1 LCD (`lcdgfx.py`) — not analyzed in depth

The v1 LCD (`pistomp/lcdgfx.py`) uses a different rendering model (fixed zones,
no widgets). It has its own `draw_analog_assignments` (`lcdgfx.py:348`) and
`draw_plugins` (`lcdgfx.py:490`). Spot checks show it reads
`plugin.has_footswitch` and `plugin.controllers` for layout. This is the
**reverse** direction of v2/v3 — it walks plugins, not hardware. This is a
potential drift point on v1 but v1 is legacy/unsupported per CLAUDE.md, so it's
out of scope for the A5 badge work (which targets v2/v3).

## 7. Collision matrix

Enumerating each collision scenario with current behavior and the charter's
desired behavior (A5 — handler owns a merged effective binding table; badges
render only from it; never render a binding that won't fire; unknown controllers
get a generic MIDI badge).

### 7a. config vs TTL (same CC targeted by config overlay and MIDI-learn binding)

**Scenario:** default config assigns footswitch 2 → CC 62. Pedalboard TTL
MIDI-learns `pluginX/:bypass` to CC 62. No per-pedalboard overlay changes fs 2.

**Current behavior:** No collision. `reinit` runs first — fs 2 ends up in
`controllers["13:62"]` (channel 13 on tre). Then `bind` runs, finds
`param.binding == "13:62"`, looks it up, binds `fs.parameter = param`, sets
`fs.category = pluginX.category`. LCD shows fs 2 labeled with pluginX bypass.
**This is the happy path; it works.**

**Failure mode:** Per-pedalboard overlay reassigns fs 2 to `preset: UP`.
`reinit` clears CC 62 from `controllers` (`hardware.py:493`). TTL binding for
`pluginX/:bypass` still says `"13:62"`. `bind` does `controllers.get("13:62")`
→ `None` → **silent skip** (`controller_manager.py:77-79`). The TTL binding is
**orphaned with no warning**. mod-host still has the MIDI-learn mapping, so a
CC 62 from *any source* (e.g. an external controller, or the virtual port if
another controller were re-routed to CC 62) would still toggle pluginX's
bypass — but pi-Stomp has no controller emitting CC 62, so the binding is
effectively dead. **The LCD shows nothing** (no badge for pluginX bypass on a
footswitch), which is honest-by-accident.

**Desired (A5):** The handler's effective binding table would record the TTL
binding as "shadowed by config overlay (preset mode)" and either render it in a
shadowed state or omit it. The orphan should be detectable — today it isn't.

### 7b. config vs context (future context declaration claims same CC)

**Scenario:** (Future, post-R2.) A panel context declares "tweak encoder 2 →
graphic-EQ band-3 gain" while the pedalboard TTL has encoder 2 MIDI-learned to
`reverb/:mix`.

**Current behavior:** N/A — context declarations don't exist. Today the panel's
`on_event` consumes encoder 2 events upstream of `_handle_encoder`
(`modhandler.py:292-300`), so the TTL binding is shadowed while the panel is
open. `controller.parameter` is still the reverb mix param; the LCD's
`analog_controllers` still shows the reverb binding. **The panel binding is
invisible to `analog_controllers`** — it lives in `on_event` code, not in any
table. This is the core drift the charter targets.

**Desired (A5):** The handler's effective binding table would have two entries
for encoder 2 — the pedalboard-scoped TTL binding (shadowed, inactive while
panel open) and the panel-scoped context binding (active). The badge renderer
shows the active one. The table is the single source; `on_event` is either
generated from it or listed as a known escape hatch (R1's classification).

### 7c. config vs blend (blend claims an analog input that also has a config binding)

**Scenario:** `analog_controllers[0]` (expression pedal, CC 75). Per-pedalboard
`blend_snapshots` config names `input_id: 0` as the blend input.

**Current behavior:** `BlendMode.prepare()` builds diff maps and **excludes
MIDI-bound parameters** from interpolation (`blend/manager.py:199-210`,
`_extract_midi_bound_parameters` reads `param.binding is not None`). However,
the expression pedal's **own CC 75** is not a *plugin parameter* binding — the
pedal sends CC 75, which mod-host routes to whatever it's learned to. Blend
excludes params with `param.binding`, not params controlled by the pedal's CC.
So if the pedal's CC 75 is MIDI-learned to `reverb/:mix`, blend's diff map for
`reverb/:mix` would *not* be excluded (because `reverb/:mix`'s
`param.binding` is `"13:75"` — wait, it *is* non-None). Let me re-check.

`blend/manager.py:205`:
```python
if param.binding is not None:
    midi_params.add((plugin.instance_id, symbol))
```
So any parameter with a non-None `param.binding` — including one bound to the
blend input's own CC — is excluded from interpolation. **This is a
silent collision resolution**: if CC 75 is both the blend input *and* a
MIDI-learned parameter control, the parameter is dropped from blend diff maps
and only the CC controls it. The blend interpolates the *other* params. The
LCD substitutes the `BlendMode` object into the pedal's icon slot
(`lcd320x240.py:1056-1073`), showing the blend snapshot name instead of the
parameter. **So the display is consistent with the behavior**, but the behavior
is "blend silently loses that one parameter," which a user might not expect.

**Desired (A5):** The effective binding table would record CC 75 as claimed by
blend, and any plugin parameter MIDI-learned to CC 75 would be flagged as
conflicting. Either blend wins (param excluded — current behavior, made
visible) or the param wins (blend can't use CC 75 — needs a different input).
The merge rule must be explicit and visible to the user.

### 7d. TTL vs blend

**Scenario:** Two parameters on the pedalboard are MIDI-learned: `drive/:gain`
to CC 70 (tweak encoder 1) and `reverb/:mix` to CC 71 (tweak encoder 2). Blend
config names `input_id: 1` (encoder 1) as the blend input.

**Current behavior:** `_extract_midi_bound_parameters` adds
`("drive", "gain")` and `("reverb", "mix")` to the excluded set. Both are
dropped from blend diff maps. Encoder 1's movement sends CC 70 (toggle
`drive/:gain`) *and* triggers blend interpolation of the *other* params. But
blend's `handle_event` (`blend/input_controller.py:95-112`) **returns True
(consumed)** when the event is from its controlled input, which happens in the
handler cascade **before** `_handle_encoder` (`modhandler.py` cascade order:
blend first, then handler logic — see R1 §3a H12). So the CC 70 emission from
`_handle_encoder` **never runs** while blend is active. Result: `drive/:gain`
is excluded from blend *and* never receives its CC. **It goes silent.** This is
a real bug-worthy collision: enabling blend on encoder 1 silently kills any
plugin parameter MIDI-learned to encoder 1's CC.

**Desired (A5):** The effective binding table would detect that encoder 1 is
claimed by blend and flag/reject TTL bindings to CC 70. At minimum, the badge
for `drive/:gain` would show "shadowed by blend" rather than just disappearing.

### 7e. Two plugins on the same pedalboard MIDI-learned to the same CC

**Scenario:** `pluginA/:bypass` and `pluginB/:bypass` both MIDI-learned to CC 60
(footswitch 0).

**Current behavior:** `ControllerManager._bind_plugin_parameters`
(`controller_manager.py:74-101`) iterates plugins in pedalboard order
(`plugin.parameters.values()`). For `pluginA/:bypass`, it does
`controller.bind_to_parameter(paramA)` → `controller.parameter = paramA`. Then
for `pluginB/:bypass`, it does `controller.bind_to_parameter(paramB)` →
**`controller.parameter = paramB`** — overwriting paramA. Both
`pluginA.controllers` and `pluginB.controllers` get the footswitch appended
(lines 90, 250). But `controller.parameter` points only to paramB.

Effect:
- A footswitch press sends CC 60, mod-host toggles **both** pluginA and
  pluginB bypass (both have MIDI-learn mappings).
- `plugin.set_param_value(":bypass", v)` (`plugin.py:127-137`) reconciles via
  `self.controllers` — **both** plugins have the footswitch in their
  `controllers` list, so both call `controller.set_value(v)`, which updates
  `fs.toggled`. Last writer wins for `fs.toggled`, but both plugins' bypass
  states update correctly via their own `param.value`.
- The LCD shows the **last-bound** plugin's label (paramB) because
  `footswitch_label` reads `fs.parameter` which is paramB.

So the footswitch controls both plugins (correct from mod-host's view), but
the badge only names one. **This is a display lie of omission** — the badge
says "pluginB" but the switch also toggles pluginA.

**Desired (A5):** The effective binding table would record CC 60 as bound to
**two** parameters. The badge renderer would either show both names, show a
"multi" badge, or signal the conflict. The current one-controller-one-parameter
model in `Controller.parameter` cannot represent this.

### 7f. External controller sharing the CC space

**Scenario:** Footswitch 0 configured `midi_port: "External FX Loop"` with CC 60.
Another external device (a MIDI footcontroller the user has) also listens on
CC 60 on a *different* ALSA port.

**Current behavior:** `external_routing[fs0] = RoutingInfo(EXTERNAL, "External
FX Loop")` (`hardware.py:411-412`). `_emit_midi` sends CC 60 to that port only
(`modhandler.py:310-313`). The other external device is **invisible** to
pi-Stomp — it has no config entry, no `controllers` key, no badge. Pi-Stomp
cannot know it exists. Its CC 60 activity is unseen and unrendered.

**Desired (A5):** "What we badge when we don't know what's on the other end" —
for the configured external port, a generic MIDI badge (no parameter name,
just CC + port). For unknown external controllers sharing the CC space, **no
badge** (we don't know they're there). The charter's "generic MIDI badge, not
a guess" applies to *configured-but-unverified* external controllers, not to
unconfigured ones.

### Collision matrix table

| Collision type | Current behavior | Desired (A5) |
|---------------|------------------|--------------|
| **config vs TTL** (same CC) | If config keeps the CC: bind succeeds, LCD shows TTL binding. If config reassigns/clears the CC: TTL binding silently orphaned, no LCD entry, no warning. mod-host still has the mapping. | Handler's effective table records both; orphaned TTL binding shown in shadowed state or flagged. Merge rule explicit. |
| **config vs context** (future) | N/A (no contexts). Panel `on_event` shadows TTL binding upstream; `analog_controllers` still shows TTL binding (stale) while panel is open. | Table has both entries; active one (context) rendered; shadowed one (TTL) hidden or shown as shadowed. |
| **config vs blend** (blend claims analog input that has config binding) | Blend excludes MIDI-learned params from diff maps. If the analog input's own CC is MIDI-learned to a param, that param is excluded. LCD shows blend snapshot name. Behavior is consistent but silent. | Table records the conflict; user-visible choice between blend and CC-controlled param. |
| **TTL vs blend** (blend input's CC equals a TTL MIDI-learned CC) | **Bug**: blend's `handle_event` consumes the event before `_handle_encoder` runs, so the CC is never emitted. The MIDI-learned param goes silent. Excluded from blend diff maps too. Double loss. | Table detects the CC claim conflict; either reject the blend input config or reject the TTL binding. At minimum, badge the dead TTL binding as "shadowed by blend." |
| **Two plugins, same CC** (TTL MIDI-learn) | Last plugin wins for `controller.parameter` and LCD label. Both plugins appended to `controller`'s... no: both plugins have the controller in their `controllers` list, so **both** reconcile on WS echo. Both toggle on the CC. Badge names only the last. | Table records multi-binding; badge shows both or a "multi" indicator. One-controller-one-parameter model must become one-to-many. |
| **External controller sharing CC space** (two external ports, same CC) | Invisible to pi-Stomp. Configured external controller gets a synthetic "External" badge. Unknown external controllers get nothing. | Configured-but-unverified external: generic MIDI badge (CC + port, no param name). Unknown: no badge. No guess. |

## 8. The "unknown controller" problem

The charter (A5) states: "Bindings we cannot name (external controllers on the
same CC space) get a generic MIDI badge, not a guess."

Today the system has **three categories of controller on a given CC**:

1. **Known & internal:** in `controllers`, routed to virtual Through, bound to
   a named plugin parameter. Full badge (parameter name + category color).
2. **Known & external:** in `controllers`, routed to a named ALSA port, bound
   to a synthetic `External` parameter. Badge today shows
   `"{port_name}:{cc} (external MIDI)"` (`lcd320x240.py:1060-1064`). This is
   **already** the "generic MIDI badge" A5 asks for — but it's only honest if
   the port is actually connected. If the port is gone, `_emit_midi` falls back
   to the virtual port (`modhandler.py:311-314`), but the badge still says
   external. **The fix is to verify port presence at badge-render time, not
   just at send time.**
3. **Unknown:** not in `controllers` at all. An external device listening on
   the same CC as a known internal controller is in this category. Pi-Stomp
   cannot see it. **No badge is correct here** — we don't know it's there.
   A5's rule is about not *inventing* a badge for these.

The "generic MIDI badge, not a guess" rule therefore has two concrete
requirements:

1. **For configured external controllers:** show `CC{n} → {port_name}` with a
   generic MIDI icon, never a parameter name. If the port is not enumerable at
   render time, show `CC{n} → {port_name} (offline)` or omit the parameter
   entirely. Today the LCD does the first part right and the offline part not
   at all.
2. **For collisions between a known controller and an unknown external on the
   same CC:** there is nothing to badge — the unknown is invisible. The rule
   is defensive: don't, in a future effective-binding table, synthesize a
   fake entry for "external devices that might share this CC." The table
   records what pi-Stomp emits, not what the CC space might contain.

## 9. Recommendation

### Should the handler be the single authority? **Yes.**

The charter (A5) names the handler as the single authority that owns the merged
view. Today, the *merge* happens in `ControllerManager.bind`, which is
invoked by the handler (`modhandler.py:878`) but is not *part of* the handler.
The routing authority is `Hardware.external_routing`, consulted by the
handler's `_emit_midi` but owned by `Hardware`. The binding *source* is the
TTL parser, producing `Parameter.binding` strings that `ControllerManager`
consumes.

Three owners, no merged view. The handler is the *consumer* of all three but
not the *owner* of any.

### What needs to change

1. **A single "effective binding table" owned by the handler.** It should
   merge: (a) TTL `Parameter.binding` → CC, (b) config overlay's CC
   assignments and external routing, (c) future context declarations, (d)
   blend-mode input claims. Each entry records: control, CC, channel, routing
   (virtual/external port), bound parameter(s), scope (pedalboard/panel), and
   shadow state (active/shadowed/orphaned).

2. **`ControllerManager.bind` becomes a builder of this table**, not a silent
   mutator of `controller.parameter`. The silent-skip behavior at
   `controller_manager.py:77-79` (CC not in `controllers`) should produce a
   table entry marked "orphaned" rather than disappearing.

3. **Multi-binding support.** `Controller.parameter` (single) must become
   `Controller.parameters` (list) or the table must record the one-to-many
   relationship separately. The `plugin.controllers` list already supports the
   reverse direction; the controller side is the bottleneck. (See §7e.)

4. **External controller badge honesty.** The LCD's external-controller
   rendering (`lcd320x240.py:1060-1064`) should verify port presence via
   `ExternalMidiManager` before showing the port name as live. An offline port
   should show a diminished badge, not a confident one.

5. **Blend/TTL conflict detection.** Today the blend-input CC and
   MIDI-learned CC collision (§7d) is a silent bug. The effective table would
   flag it at `BlendMode.prepare()` time — "input_id 1's CC 70 is
   MIDI-learned to drive/:gain; chose one." Today `_extract_midi_bound_parameters`
   excludes by `param.binding`, but it doesn't detect that the *input
   controller's own CC* is bound.

### What is already correct

- **The LCD is a pure consumer.** No code in `lcd320x240.py` reads
  `controllers`, `param.binding`, or `external_routing` directly. It reads
  `current.analog_controllers` (built by `ControllerManager`) and the live
  `Footswitch` object's fields. The A5 requirement "the LCD renders *from* the
  table and never computes its own idea of what's bound" is **already
  satisfied** for the main panel and footswitch strip, *if* the table is the
  handler's effective binding view. The LCD just needs to keep reading from
  that one source — which today is `current.analog_controllers` + `footswitches`.
- **`_emit_midi` is already handler-authoritative for routing.** The handler
  owns the routing decision via `hardware.external_port_name(controller)`. No
  controller emits MIDI on its own; all go through `_emit_midi`. This matches
  the charter's "MIDI is an output of dispatch, not a parallel path."
- **Optimistic-update-then-reconcile** (CLAUDE.md "MOD Integration") is
  independent of the binding table. It concerns *values*, not *bindings*. No
  change needed.
- **The `controllers` dict keying scheme** (`"{ch}:{CC}"`) is correct and
  matches the TTL parser's output format. The lookup works. The problem is
  not the key; it's that the dict is a flat CC→controller map with no
  binding metadata, no multi-binding, no shadow state.
- **`ControllerManager._bind_external_controllers` synthetic parameter**
  pattern (creating a fake `Parameter` with `EXTERNAL_INSTANCE_ID`) is a
  reasonable scaffolding for the "generic MIDI badge." It just needs to be
  promoted from a controller-level hack into the effective table, with the
  "offline port" honesty fix.

## 10. Open questions for R2 (declaration schema and precedence)

R2 must produce a schema that can represent everything R3 found. The merge
semantics R2 must be able to express:

1. **Multi-binding (one CC → many params).** §7e shows two plugins' bypass on
   one footswitch CC. The schema must allow a context declaration to bind a
   control to multiple effects, or must explicitly declare this an error and
   force a unique-CC constraint. Which? Today mod-host allows it; pi-Stomp's
   `Controller.parameter` cannot represent it.

2. **Shadowed vs orphaned vs active state.** §7a (config reassigns CC → TTL
   binding orphaned) and §7b (panel context shadows TTL binding) require the
   table to distinguish three states: active (binding fires), shadowed (a
   higher-precedence binding covers it, but it's still in the table), and
   orphaned (the control is gone/reassigned, binding can never fire). Does the
   schema record state per-binding-entry, or is state derived from precedence
   at render time?

3. **External routing as a binding attribute or a separate dimension?** Today
   `external_routing` is a per-controller fact, independent of which parameter
   is bound. A5's effective table could model routing as a column on the
   binding row (control, CC, routing, param) or as a separate
   control-attribute table. R2 must decide. The current separation
   (`controllers` vs `external_routing`) works because routing is a
   transport concern, not a binding concern — but the "offline port" honesty
   fix couples them at render time.

4. **Blend-mode input claim as a binding.** §7c/7d show blend claiming an
   analog input. Is this a context declaration (analog input → blend
   interpolation effect) that must coexist with TTL plugin bindings on the
   same CC, or does it pre-empt them? The answer determines whether blend is a
   row in the table or a shadowing layer above it. The current behavior
   (blend consumes events upstream, TTL params go silent) suggests it's a
   shadowing layer, but that makes the TTL bindings invisible — which is the
   bug in §7d.

5. **Selection-dependent bindings (R1 §3b E3, E6, E7, E10-12, E15, E16).**
   These are panel-scoped bindings where the *target* depends on the current
   selection (e.g. enc1 → "selected arc widget's parameter"). The schema must
   represent "enc1 edits the selection" as a binding type, and the badge
   renderer reads the selection to name the badge. Does the effective table
   hold a placeholder row that resolves at render time, or does the panel
   publish a resolved binding on focus change? R2 must decide; R3 only notes
   that today this lives entirely in `on_event` code with no table
   representation.

6. **Footswitchpiercing (A3).** The charter requires footswitch `SwitchEvent`s
   pierce panel contexts by default. Today this is enforced by no panel
   consuming footswitch events in `on_event` (R1 §5, finding 4). When context
   declarations exist, the schema must mark footswitch bindings as
   "piercing-by-default" and the cascade enforces it. Where in the cascade?
   The handler's `_handle_switch` (`handler.py:128-162`) runs *after*
   `lcd.handle` (`modhandler.py` cascade), so piercing is currently
   structural (panels don't filter footswitches). With declared contexts, the
   cascade needs an explicit bypass rule for footswitch-class events. R2 must
   specify whether this is a per-control-class precedence rule or a cascade
   wiring rule.

7. **Does `controller.parameter` survive or get replaced?** If the effective
   table becomes the authority, `controller.parameter` is a denormalized
   cache of one row of the table. R2 must decide whether controllers keep
   their `.parameter` field (for the reconcile path in `plugin.set_param_value`
   → `c.set_value`, `plugin.py:135-137`) or whether reconciliation reads the
   table directly. Today `plugin.controllers: list[Controller]` is the reverse
   index; changing this has broad impact.