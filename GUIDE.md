# pi-Stomp Development Guide

## Concepts

pi-Stomp is python software that runs on a raspberry pi and acts as a hardware controller for MOD-UI. MOD-UI is a virtual pedalboard webapp that wraps mod-host, which hosts LV2 plugins (effects). It runs all this on top of JACK (audio routing).

In addition to displaying graphics on a 320x240 16-bit LCD, it also reads physical controls (footswitches, encoders, knobs, expression pedals), sends them as MIDI CCs via ALSA's virtual MIDIThrough port, and reflects state back from MOD-UI to the LCD.

The software is structured around a polling loop that reads hardware at a 10ms cadence, drains inbound WebSocket messages at the same rate, and delegates slower work (LCD refresh, MOD sync, WiFi) to progressively-longer intervals.

Three hardware variants (v1/v2/v3) share a common `Hardware` base class (switched via YAML). The "business logic" brain of the app for v1 is the (legacy/unsupported) `mod.py`; for v2/v3, `modhandler.py` is the modern version. Both suclass `Handler`.

MOD-UI is the single writer of plugin bypass and parameter values. pi-Stomp emits changes (MIDI CC for footswitches, WebSocket `param_set` for other toggles) and updates its own indicators optimistically, then reconciles against MOD-UI's echo — which carries the absolute current value, so it overwrites rather than compounds. This keeps the UI responsive while avoiding dual-source drift.

An lv2-ttl-guide exists in docs/ to describe the plugin (LV2) and pedalboard (TTL) formats.

## OS & Deployment

pi-Stomp runs on a custom Raspberry Pi OS Lite image (Debian Trixie, arm64, RT kernel) built by the [pi-gen-pistomp](https://github.com/TreeFallSound/pi-gen-pistomp) repository. The image includes JACK2, mod-host, MOD-UI, and other system dependencies; pi-stomp itself is shipped as an `arm64` Debian package built from this repo at image build time, and updates ship via an apt repo hosted on GitHub Pages (full OTA design in `pi-gen-pistomp/docs/OTA.md`).

> __The system python is used for base packages (e.g. `python3-lilv`), as they are not packaged on PyPI. PyPI dependencies live in a uv-managed venv built at package time.__

| Path | Purpose |
|------|---------|
| `/opt/pistomp/pi-stomp/` | Installed source tree (from the `pi-stomp` `.deb`) |
| `/home/pistomp/pi-stomp/` | Symlink to the above, for `deploy.sh` compatibility |
| `/opt/pistomp/venvs/pi-stomp/` | uv venv with `--system-site-packages` |
| `/home/pistomp/data/` | Runtime data |
| `/home/pistomp/data/config/` | Settings, default config |
| `/home/pistomp/data/.pedalboards/` | Pedalboard bundles |
| `/usr/lib/systemd/system/mod-ala-pi-stomp.service` | Service unit (ships in the `pi-stomp` `.deb`) |

The service runs as the `pistomp` user (not root).

On first boot, `firstboot.sh` reads `/boot/pistomp.conf` for WiFi, hostname, audio settings, and hardware version (Pi 3 → v2.0, Pi 4/5 → v3.0).

```bash
ps-restart                    # sudo systemctl restart mod-ala-pi-stomp
ps-stop                       # sudo systemctl stop mod-ala-pi-stomp
ps-run                        # sudo ... direct run (for debugging)
sudo journalctl -u mod-ala-pi-stomp -f   # live logs
```

For local development, `scp` files to the device, use `deploy.sh`, or mount via sshfs:

```bash
scp modalapi/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/modalapi/
ssh pistomp@pistomp.local "ps-restart"
```

### Shipping a new pi-stomp version

OTA updates flow through the `pi-gen-pistomp` repo's apt repo. Two pushes are required:

1. Land code changes on `pi-stomp#main`.
2. In `pi-gen-pistomp`, bump the pi-stomp package version so `build-deb.yml` builds a fresh `.deb`:
   ```bash
   cd ../pi-gen-pistomp
   ./scripts/bump-version.sh pi-stomp "Description of change."
   ```
   This edits `debpkgs/pi-stomp/debian/changelog` (the version is the gate that triggers a rebuild; no other files need editing).
3. Push `pi-gen-pistomp#main`. The `build-deb.yml` workflow builds the `.deb`, publishes a GitHub Release tagged `debpkg/pi-stomp/<ver>`, and `publish-apt-repo.yml` updates the `gh-pages` apt index.
4. Devices pick it up on their next `apt upgrade` (or via the `pistomp-recovery` Update-packages menu).

## Tests

```bash
uv run pytest                    # all tests
uv run pytest --snapshot-update  # accept changed LCD snapshots
uv run pytest --cov=pistomp --cov=modalapi --cov=common --cov=uilib --cov-report=term-missing
```

The `snapshot` fixture asserts the rendered LCD image matches a baseline PNG:

```python
def test_my_flow(v3_system, snapshot):
    snapshot()           # auto-numbered
    snapshot("label")    # named
    snapshot("label")    # same name → asserts screen returned to prior state
```

Regenerate baselines after intentional UI changes with `--snapshot-update`.

Add a new hardware version by creating `tests/v2/conftest.py` with a fixture analogous to `v3_system`.

## Architecture

### Entry Point & Polling Loop

`modalapistomp.py` initializes the system and enters a polling loop:

```
1. Parse CLI args (log level, host type)
2. Initialize audio card (early for audio pass-through)
3. Open MIDI output via rtmidi (first port = ALSA MIDI Through on device)
4. Load default config → determine hardware version
5. Create handler (Mod or Modhandler) via Handlerfactory
6. Create hardware (Pistomp / Pistompcore / Pistomptre) via Hardwarefactory
7. Load pedalboards (LILV parser)
8. Load current pedalboard → reinit hardware → bind controllers
```

The loop runs every 10ms, with slower tasks at multiples:

| Period | Call | Purpose |
|--------|------|---------|
| 10ms | `poll_controls()` | Read all hardware inputs |
| 10ms | `poll_ws_messages()` | Drain inbound WebSocket |
| 20ms | `poll_indicators()` | Update LEDs, VU meters |
| ~80ms* | `poll_lcd_updates()` | Render LCD |
| 1000ms | `poll_modui_changes()` | Check `last.json` mtime, banks mtime |
| 2000ms | `poll_wifi()`, `poll_ethernet()` | Network status |
| 60s | `poll_system_info()` | CPU throttling, temperature |

\* LCD cadence is `period % handler.lcd_poll_divisor`, where the divisor derives from the SPI clock (≈8 ticks). A mounted fullscreen panel (tuner or plugin editor) drops it to every tick (10ms) for smooth animation.

### Hardware Version Selection

`hardware.version` (a float) in the active YAML config selects implementations via factory classes:

| Version | Handler | Hardware | Traits |
|---------|---------|----------|--------|
| < 2.0 | `Mod` (`modalapi/mod.py`) | `Pistomp` (`pistomp/pistomp.py`) | Dual encoders, 3 switches, mono LCD |
| 2.0–2.9 | `Modhandler` (`modalapi/modhandler.py`) | `Pistompcore` (`pistomp/pistompcore.py`) | Single encoder, color LCD, relay |
| ≥ 3.0 | `Modhandler` (`modalapi/modhandler.py`) | `Pistomptre` (`pistomp/pistomptre.py`) | 4 encoders, LED strip, VU meters |

All hardware subclasses inherit from `Hardware` which provides `reinit(cfg)`, `poll_controls()`, SPI/ADC communication, and the `controllers` dictionary mapping `"{channel}:{CC}"` to controller objects.

The LCD is created by each hardware subclass in `init_lcd()` and injected into the handler via `handler.add_lcd(...)`. The handler owns the LCD (`handler._lcd`). For v2/v3, the LCD receives a handler reference for UI callbacks (pedalboard selection, parameter editing, system menu). The v1 LCD (`lcdgfx`) does not receive a handler reference.

### MIDI Routing

Sending MIDI is not something a control does on its own — it is one possible *outcome* of input dispatch (see [Input Dispatch](#input-dispatch-pistompinput)). A control turns its raw reading into an event; the handler's cascade decides what that event means, and for most rotations/presses that means emitting a MIDI CC via `_emit_midi()`. (Other outcomes: a WebSocket param, audio-card volume, UI navigation, or a panel swallowing the event entirely.) This section is the transport *downstream* of that decision.

Emitted CCs go to a single ALSA virtual port. On the deployed system, rtmidi port 0 resolves to the "Midi Through Port-0" created by `amidithru` (ALSA client 14:0). JACK bridges this via `-X seq`:

```
Handler `_emit_midi()`  ← chosen by input dispatch
    ↓ MIDI CC via rtmidi
ALSA Midi Through (amidithru, typically client 14:0)
    ↓ JACK (-X seq)
    ├→ mod-host:midi_in (MIDI Learn for parameter control)
    └→ Available in MOD-UI for wiring to LV2 MIDI plugins
```

Controls that send MIDI:

| Control | CC Range | Notes |
|---------|----------|-------|
| Footswitches | CC 60–63 | Configurable per pedalboard |
| Encoder rotation (v3) | CC 70, 71 | Tweak encoders send on rotate |
| Expression pedal | CC 75 | When `autosync: true`, sends initial position on pedalboard load |
| Encoder buttons | — | Press dispatches a `SwitchEvent`; handler routes nav/short-press to UI, not MIDI |

By default every control emits to the virtual Through port. A control can instead be routed to an external hardware MIDI port — `hardware.external_routing` is the sole routing authority (configured per-pedalboard), consulted by the handler's `_emit_midi()` at dispatch time (`ExternalMidiManager` resolves the rtmidi port). See `modalapi/external_midi.py`.

### Configuration Overlay

Two config layers merge at pedalboard load time:

```
Default config (setup/config_templates/)
  ↓ loaded at startup, creates hardware
Per-pedalboard config ({bundle}/config.yml)
  ↓ overlaid by hardware.reinit(cfg)
```

`reinit()` starts from a copy of the default config, applies defaults (footswitches, encoders, MIDI), then overlays any pedalboard-specific overrides. Unspecified fields keep their defaults. Analog controls call `initialize()` after the overlay — if `autosync: true`, they read the ADC and emit their current position as a MIDI CC to prevent state mismatch.

Config files:
- `/home/pistomp/data/config/default_config.yml` (written by firstboot from templates)
- `{pedalboard_bundle}/config.yml` (per-pedalboard overlay)

### MOD Integration

**REST** (`localhost:80`) for pedalboard/snapshot operations and BPM reads. **WebSocket** (`ws://localhost:80/websocket`) for live state — bypass values, parameter values, and tap-tempo BPM.

The WebSocket bridge (`AsyncWebSocketBridge`) runs a daemon thread with exponential-backoff reconnection. Outbound messages go into an unbounded queue; inbound messages are drained by `poll_ws_messages()` on every tick. `output_set` meter/scope messages are dropped at reception.

REST covers pedalboard and snapshot operations the current BPM. Plugin bypass/parameters and outgoing tap tempo use WebSocket.


#### Inbound messages

| Pattern | Typed message | Effect |
|---------|---------------|--------|
| `param_set …/:bypass v` | `PluginBypassMessage` | Set bypass, redraw |
| `param_set …/{sym} v` | `ParamSetMessage` | `Plugin.set_param_value`: cache value + mirror onto any bound control (footswitch LED/keycap, knob/encoder position) |
| `add {inst} … {bypassed} …` | `AddPluginMessage` | Connect/reconnect dump only; bypass in field 4 |
| `loading_end {snapshot}` | `LoadingEndMessage` | Stash snapshot index for file-watch path |
| `pedal_snapshot {id} {name}` | `PedalSnapshotMessage` | In-board snapshot change |

Snapshot loads from mod-ui broadcast only deltas vs its own cache; pedalboard loads and connect dumps rebroadcast unconditionally. This means reselecting a board is a full resync, but reselecting a snapshot is not.

#### Outbound: emit, then reconcile

MOD-UI stays authoritative for bypass/parameter state, but pi-Stomp updates its own indicators optimistically so the UI stays responsive; the inbound echo carries the absolute current value and reconciles if it ever differs.

- **Footswitch**: `pressed()` flips local `toggled`, updates its LED immediately, and sends an absolute MIDI CC. mod-host applies it and echoes `param_set` to all clients (including us), where `plugin.set_param_value()` reconciles cached state and redraws the LCD. Optimism matters because mod-host gates its feedback stream on the `data_finish`/`output_data_ready` handshake — a backgrounded mod-ui browser tab can delay that echo by seconds, which would otherwise lag the switch.
- **Tap tempo**: Sends `transport-bpm` via WebSocket bridge.

Because the echo is absolute (not a delta), a wrong optimistic prediction is overwritten rather than compounded, and rapid presses stay correct since the CC alternates from locally-advancing `toggled`.

The outlier is a **non-footswitch UI bypass** (e.g. tapping a plugin on the LCD):

1. WS `send_parameter`
2. mod-ui calls `host.bypass()`
3. `msg_callback_broadcast` **skips the origin socket** (us)
4. mod-host does NOT generate `param_set` feedback for `bypass` commands it received from mod-ui

As such, no echo arrives. In this case, pi-Stomp updates local state and LCD immediately, then sends WS to keep mod-ui in sync.

### Pedalboard Data Loading

LILV parses `.ttl` files in the pedalboard bundle into `Pedalboard` → `Plugin` → `Parameter` objects. Binding maps each plugin's MIDI bindings to `controllers["{channel}:{CC}"]`, linking hardware controls to plugin parameters.

Change detection: `FileChangeMonitor` watches `/home/pistomp/data/last.json` mtime. When MOD-UI writes it (pedalboard change), piStomp reloads the pedalboard and syncs hardware. Banks are watched similarly via `banks.json` mtime (v3/Modhandler only).

### Blend Mode

Blend mode interpolates between snapshots based on analog input position. Configured per-pedalboard in `config.yml`.

On pedalboard load, `SnapshotManager.sync_blend_snapshots()` creates or updates the snapshot entries in MOD, then `BlendMode.prepare()` pre-computes diff maps for every parameter between stops. During the 10ms polling loop, the active `BlendMode` reads its input controller and sends only parameters whose values have actually changed — MIDI-bound parameters are automatically excluded to prevent conflicts with CC control.


The blend system is in `blend/`.

## Core Components

### Input Dispatch (`pistomp/input/`)

Every hardware input — footswitch, encoder, knob, expression pedal — flows through one path on all hardware versions. A `Controller` reads its detector, advances its own state, packages what happened into an immutable event, and hands it to a single sink — the handler — whose `handle` cascades LCD → blend mode → its own logic. That final stage is where an event becomes an effect: **emit a MIDI CC** (`_emit_midi`, see [MIDI Routing](#midi-routing)), send a WebSocket param, set audio-card volume, or drive UI navigation. MIDI is thus an output of dispatch, not a parallel path. There is no router class; the "router" is the sink field plus the code each sink writes. **Design in `pistomp/input/README.md`.**

### Footswitches (`pistomp/footswitch.py`)

A footswitch is a Controller that emits a switch event; the handler decides what the press means — relay bypass, preset change, tap tempo, or the optimistic MIDI-CC toggle described above. Config overlay per pedalboard can change MIDI CC, relay binding, preset, color, and longpress groups.

**Longpress groups** let two footswitches held together fire a shared action (`next_snapshot`, `toggle_tuner_enable`, …) within a 400ms window. The resolver is `FootswitchChords`, owned by the handler.

### Encoders (`pistomp/encoder.py`, `pistomp/encoder_controller.py`)

`Encoder` is the raw quadrature decoder; `EncoderController` is the Controller wrapping it (quantizer, parameter, absorbed push-button). The handler routes each encoder by its type: navigation, audio-card volume, or a plugin parameter.

### Analog Controls (`pistomp/analogmidicontrol.py`)

Reads 10-bit ADC (0–1023) via MCP3008 SPI, converts to MIDI CC (0–127) using `as_midi_value()`. Threshold-based change detection prevents jitter. `_clamp_endpoints()` forces values near 0 or 1023 to exact endpoints, ensuring full-range input despite ADC noise.

Types: `KNOB` and `EXPRESSION` (config-driven). When `autosync: true`, `initialize()` reads the ADC and sends current position on pedalboard load, preventing stale state after switching.

### LCD System

- **v1**: `pistomp/lcdgfx.py` — monochrome 128×64 display via gfxhat library. Direct PIL/ImageDraw rendering into fixed zones. No handler reference.
- **v2/v3**: `pistomp/lcd320x240.py` — color 320×240 display. Widget-based UI (`uilib/`). Builder pattern constructs panels from pedalboard data. Receives handler reference for UI action callbacks.

**Surface formats** — Never create a bare `pygame.Surface((w,h))`: it inherits the display format, which is opaque RGB headless (device/tests) but ARGB under a real window driver (the cocoa emulator). That stray alpha channel silently breaks SRCALPHA compositing (e.g. glyph pastes drop their fill). Always be explicit: `pygame.SRCALPHA` for alpha surfaces, or `depth=32, masks=(0xFF0000, 0xFF00, 0xFF, 0)` for opaque RGB ones (bit-identical to the device's headless 32-bit XRGB; `depth=24` differs in AA rounding).

### WebSocket Bridge (`modalapi/websocket_bridge.py`, `modalapi/ws_protocol.py`)

`AsyncWebSocketBridge` manages a background daemon thread that owns the WebSocket connection. Queues:
- **Outbound**: `command_queue` (unbounded — never drops blend-mode messages). `send_parameter(instance_id, symbol, value)` and `send_bpm(bpm)` enqueue typed commands. Backpressure monitoring: if the TCP write buffer exceeds 8KB, outbound sends return `False` until it drains.
- **Inbound**: `received_queue`, drained by `get_received_messages()` on every 10ms tick. `output_set` messages (audio meters) are dropped at reception.

`ws_protocol.py` parses raw text into typed dataclasses — the ones the handler acts on are `PluginBypassMessage`, `ParamSetMessage`, `AddPluginMessage`, `LoadingEndMessage`, `PedalSnapshotMessage`, `TransportMessage` (BPM) — plus several recognized-but-mostly-ignored kinds (`LoadingStartMessage`, `SizeMessage`, `AddHwPortMessage`, `TrueBypassMessage`, `MidiMapMessage`, …); anything else becomes `UnknownMessage`.

`ping` messages receive a `pong` reply; `data_ready` messages are echoed back.

### Auxiliary Subsystems

Smaller pieces the loop drives, each self-contained — start at the named file:

- **Tuner** (`pistomp/tuner/`) — a fullscreen LCD panel showing pitch; YIN pitch detection over a JACK audio source. Toggled by a footswitch longpress group.
- **Local-monitor mute** (`modalapi/jack_mute.py`) — disconnects mod-monitor from `system:playback` to silence the pi's output while other JACK clients still get signal.
- **Network managers** (`modalapi/wifi/`, `modalapi/ethernet/`) — nmcli-backed status/config polled at 2s. Blocking subprocess work runs off the UI thread.
- **Audio cards** (`pistomp/audiocard*.py`, `hifiberry.py`, `iqaudiocodec.py`) — per-card init/volume behind `audiocardfactory`.

## Data Flow

### Expression Pedal Movement

```
poll_controls() (10ms)
  → AnalogMidiControl.poll_hw()
    → ADC read → _clamp_endpoints() → as_midi_value() → AnalogEvent
      → handler.handle(event) → _emit_midi()
        → rtmidi port 0 → ALSA Midi Through (amidithru)
          → JACK (-X seq)
            ├→ mod-host:midi_in
            └→ MOD-UI → LV2 MIDI plugins → external devices
```

### Pedalboard Change (via MOD-UI)

```
MOD-UI writes /home/pistomp/data/last.json
  → FileChangeMonitor detects mtime change (1000ms poll)
    → reload_pedalboard(bundle)
      → LILV parses TTL → Pedalboard(Plugin, Parameter) objects
        → set_current_pedalboard(pb)
          → Load {bundle}/config.yml
          → hardware.reinit(cfg) — overlay config
          → ControllerManager.bind() — map controllers to parameters
          → lcd.link_data() → lcd.draw_main_panel()
          → Prepare blend modes if configured
```

### Footswitch Press → Plugin Bypass

```
poll_controls()
  → Footswitch emits SwitchEvent → handler._handle_footswitch()
    → flip toggled, set LED                         # optimistic update
    → emit absolute MIDI CC (127 if toggled else 0)

mod-ui applies bypass, broadcasts via WebSocket
  → poll_ws_messages() → parse_message()
    → PluginBypassMessage → plugin.set_bypass(v)   # → set_param_value, reconciles switch
    → lcd.refresh_plugins()
```

### Footswitch Press → Non-Footswitch Toggle

For controls that go through WebSocket rather than MIDI (e.g., parameter edits from the LCD):

```
UI interaction → ws_bridge.send_parameter(instance_id, symbol, value)
  → ... no local state change ...
mod-ui echoes back → ParamSetMessage → plugin.set_param_value()  # caches value, mirrors to any bound control
```

## Key Files

**Entry & Factories**:
- `modalapistomp.py` — Main loop
- `pistomp/handlerfactory.py` — Version → handler
- `pistomp/hardwarefactory.py` — Version → hardware

**Handlers** (Business Logic):
- `pistomp/handler.py` — Abstract base
- `modalapi/mod.py` — v1 handler (also has encoder state-machine enums)
- `modalapi/modhandler.py` — v2/v3 handler

**Hardware** (Physical Interface):
- `pistomp/hardware.py` — Base class, config overlay, controller dict
- `pistomp/pistomp.py`, `pistompcore.py`, `pistomptre.py` — v1/v2/v3 subclasses

**Input & Controls** (see `pistomp/input/README.md`):
- `pistomp/input/` — Event dataclasses + `InputSink` protocol
- `pistomp/controller.py`, `controller_manager.py` — Controller base + pedalboard binding
- `pistomp/footswitch.py`, `footswitch_chords.py` — Footswitch Controller + chord resolver
- `pistomp/encoder.py`, `encoder_controller.py` — Quadrature decoder + Controller wrapper
- `pistomp/analogmidicontrol.py` — ADC → MIDI CC with endpoint clamping
- `pistomp/gpioswitch.py`, `analogswitch.py` — Raw GPIO/ADC button detectors
- `modalapi/external_midi.py` — External MIDI port routing

**Blend**:
- `blend/manager.py` — Lifecycle, input wiring
- `blend/snapshot.py` — Snapshot creation/sync via MOD-UI REST
- `blend/parameter_setter.py` — Sends parameter diffs over WebSocket
- `blend/input_controller.py` — Adapts analog controls as blend inputs
- `blend/easing.py` — Interpolation curves (linear, smooth, build, drop, snap, bloom)
- `blend/stop.py` — Pre-computed diff maps between snapshots

**MOD API**:
- `modalapi/pedalboard.py` — LILV TTL parser
- `modalapi/websocket_bridge.py` — Async WS bridge (daemon thread, backpressure)
- `modalapi/ws_protocol.py` — Message parsing into typed dataclasses
- `modalapi/pedalboard_monitor.py` — FileChangeMonitor for last.json/banks.json
- `common/parameter.py` — Parameter representation, formatting, taper
- `modalapi/plugin.py` — Plugin representation

**Config & State**:
- `pistomp/config.py` — Config loading/validation
- `pistomp/settings.py` — Persistent YAML key-value store (`/home/pistomp/data/config/settings.yml`)

**Display**:
- `pistomp/lcd320x240.py` — Color LCD (v2/v3)
- `pistomp/lcdgfx.py` — Mono LCD (v1)
- `uilib/` — Widget library (see `uilib/README.md` for the paint system)

**Auxiliary**:
- `pistomp/tuner/` — YIN pitch-detection tuner panel
- `modalapi/jack_mute.py` — Local-monitor mute
- `modalapi/wifi/`, `modalapi/ethernet/` — Network managers

## Coding principles

- **Type safety is mandatory**
- **Broad pyright ignores are a code smell**
- **getattr and hasattr are banned**
- **dependencies must form a DAG**

## Design Principles

- **Polling over events** — Fixed-frequency loops for predictable timing; 10ms critical path
- **Explicit version routing** — Factory pattern with known version checks, not capability detection
- **Overlay, don't replace** — Per-pedalboard config merges with defaults at field level
- **Single writer** — MOD-UI owns bypass/parameter state; pi-Stomp emits, paints optimistically, and reconciles against the absolute echo
- **Incremental updates** — `reinit()` updates objects in-place; blend diff maps are pre-computed
- **Trust MOD for audio** — pi-Stomp is a controller; audio processing lives in mod-host
- **Fail gracefully** — Log warnings, continue operation where possible

## Finding LV2 Plugin Port Symbols

When building a custom plugin panel you need the LV2 port symbols (`lv2:symbol`),
ranges (`lv2:minimum`/`lv2:maximum`), and the plugin URI (`lv2:prototype`).

### Preferred: On-Device Inspection

```bash
# List installed plugin bundles (506 on a typical device)
ssh pistomp@pistomp.local "ls ~/.lv2/"

# Read a plugin's manifest to find its TTL file and URI
ssh pistomp@pistomp.local "cat ~/.lv2/<name>.lv2/manifest.ttl"

# Read the plugin TTL for port definitions
ssh pistomp@pistomp.local "cat ~/.lv2/<name>.lv2/<name>.ttl" \
  | grep -E "lv2:symbol|lv2:name|lv2:minimum|lv2:maximum|lv2:default"

# List pedalboards on device (these show which plugins are actually used)
ssh pistomp@pistomp.local "ls ~/data/.pedalboards/"

# Extract plugin URIs from a pedalboard's TTL
ssh pistomp@pistomp.local "grep 'lv2:prototype' ~/data/.pedalboards/<name>.pedalboard/*.ttl"
```

### Fallback: pi-gen-pistomp Cache

The `pi-gen-pistomp` repo caches the full LV2 plugin archive at
`../pi-gen-pistomp/cache/lv2plugins.tar.gz`. **NEVER extract the whole
archive** — it's large and slow. Use `tar` to inspect and extract
specific files:

```bash
# List plugin bundles in the archive
tar -tzf ../pi-gen-pistomp/cache/lv2plugins.tar.gz | grep '\.lv2/$' | head -20

# Read a specific plugin's manifest
tar -xzf ../pi-gen-pistomp/cache/lv2plugins.tar.gz \
  --to-stdout "<name>.lv2/manifest.ttl"

# Read a specific plugin's TTL
tar -xzf ../pi-gen-pistomp/cache/lv2plugins.tar.gz \
  --to-stdout "<name>.lv2/<name>.ttl"

# Extract a single plugin bundle to inspect locally
tar -xzf ../pi-gen-pistomp/cache/lv2plugins.tar.gz \
  "<name>.lv2/" -C /tmp/
```

The device is preferred because it has the actual installed versions and
pedalboard data showing real-world usage. Use the cache only when the
device is unreachable.

## On-Device Testing

```bash
curl -X POST http://localhost:80/pedalboard/load_bundle/ \
  -d 'bundlepath=/home/pistomp/data/.pedalboards/AmpBud.pedalboard'

curl -s http://localhost:80/pedalboard/list | python3 -m json.tool
```
