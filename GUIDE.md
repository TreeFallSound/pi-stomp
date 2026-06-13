# pi-Stomp Development Guide

## Concepts

pi-Stomp is python software that runs on a raspberry pi and acts as a hardware controller for MOD-UI. MOD-UI is a virtual pedalboard webapp that wraps mod-host, which hosts LV2 plugins (effects). It runs all this on top of JACK (audio routing).

In addition to displaying graphics on a 320x240 16-bit LCD, it also reads physical controls (footswitches, encoders, knobs, expression pedals), sends them as MIDI CCs via ALSA's virtual MIDIThrough port, and reflects state back from MOD-UI to the LCD.

The software is structured around a polling loop that reads hardware at a 10ms cadence, drains inbound WebSocket messages at the same rate, and delegates slower work (LCD refresh, MOD sync, WiFi) to progressively-longer intervals.

Three hardware variants (v1/v2/v3) share a common `Hardware` base class (switched via YAML). The "business logic" brain of the app for v1 is the (legacy/unsupported) `mod.py`; for v2/v3, `modhandler.py` is the modern version. Both suclass `Handler`.

MOD-UI is the single writer of plugin bypass and parameter values. pi-Stomp emits changes (MIDI CC for footswitches, WebSocket `param_set` for other toggles) and waits for the echo to update its own state. This avoids dual-source drift.

## OS & Deployment

pi-Stomp runs on a custom Arch Linux ARM image built by the `pistomp-arch` repository. The image includes JACK2, mod-host, MOD-UI, other system dependencies, and all Python dependencies are maintained in a virtual environment.

> __The built-in system python is used for base packages, as they are not packaged on PyPI.__

| Path | Purpose |
|------|---------|
| `/home/pistomp/pi-stomp/` | Application code (git clone) |
| `/home/pistomp/data/` | Runtime data |
| `/home/pistomp/data/config/` | Settings, default config |
| `/home/pistomp/data/.pedalboards/` | Pedalboard bundles |
| `/opt/pistomp/venvs/pi-stomp/` | Python venv (system-site-packages) |
| `/usr/lib/systemd/system/mod-ala-pi-stomp.service` | Service unit |

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
| 200ms | `poll_lcd_updates()` | Render LCD |
| 1000ms | `poll_modui_changes()` | Check `last.json` mtime, banks mtime |
| 2000ms | `poll_wifi()` | WiFi status |
| 60s | `poll_system_info()` | CPU throttling, temperature |

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

All hardware controls send MIDI CCs to a single ALSA virtual port. On the deployed system, rtmidi port 0 resolves to the "Midi Through Port-0" created by `amidithru` (ALSA client 14:0). JACK bridges this via `-X seq`:

```
Hardware Controls (footswitches, encoders, expression pedals)
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
| Encoder buttons | — | Short press calls handler callback (e.g. `universal_encoder_sw`), not MIDI |

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

#### Inbound messages

| Pattern | Typed message | Effect |
|---------|---------------|--------|
| `param_set …/:bypass v` | `PluginBypassMessage` | Set bypass, redraw |
| `param_set …/{sym} v` | `ParamSetMessage` | Cache parameter value (no live redraw) |
| `add {inst} … {bypassed} …` | `AddPluginMessage` | Connect/reconnect dump only; bypass in field 4 |
| `loading_end {snapshot}` | `LoadingEndMessage` | Stash snapshot index for file-watch path |
| `pedal_snapshot {id} {name}` | `PedalSnapshotMessage` | In-board snapshot change |

Snapshot loads from mod-ui broadcast only deltas vs its own cache; pedalboard loads and connect dumps rebroadcast unconditionally. This means reselecting a board is a full resync, but reselecting a snapshot is not.

#### Outbound: emit and echo back

piStomp usually defers to WS messages from MOD-UI to bring state updates, even when we initiated them:

- **Footswitch**: `pressed()` sets local `toggled` state and sends absolute MIDI CC immediately. The bypass display (plugin state, LCD) updates only when mod-ui echoes the change back over WebSocket. For unbound footswitches (`drives_display` == true), the local LED updates immediately.
- **Tap tempo**: Sends `transport-bpm` via WebSocket bridge.

This single-writer discipline keeps rapid presses correct and avoids dual-source drift, at the expense of ~10ms delay (our poll rate). The outlier is footswitches in non-MIDI mode:

1. WS `send_parameter`
2. mod-ui calls `host.bypass()`
3. `msg_callback_broadcast` **skips the origin socket** (us)
4. mod-host does NOT generate `param_set` feedback for `bypass` commands it received from mod-ui

As such, no echo arrives. In this case, pi-Stomp updates local state and LCD immediately, then sends WS to keep mod-ui in sync.

### Pedalboard Data Loading

LILV parses `.ttl` files in the pedalboard bundle into `Pedalboard` → `Plugin` → `Parameter` objects. Binding maps each plugin's MIDI bindings to `controllers["{channel}:{CC}"]`, linking hardware controls to plugin parameters.

Change detection: `FileChangeMonitor` watches `/home/pistomp/data/last.json` mtime. When MOD-UI writes it (pedalboard change), piStomp reloads the pedalboard and syncs hardware. Banks are watched similarly via `banks.json` mtime (v3/Modhandler only).

### Blend Mode

Blend mode interpolates between snapshots based on analog input position. Configured per-pedalboard in `config.yml` under `blend_snapshots`:

```yaml
blend_snapshots:
  - name: "Clean to Fuzz"
    input_id: 0                     # Expression pedal
    interpolation: smooth           # linear, smooth, build, drop, snap, bloom
    stops:
      "0.0": "Clean"
      "0.5": "Crunch"
      "1.0": "Fuzz"
```

On pedalboard load, `SnapshotManager.sync_blend_snapshots()` creates or updates the snapshot entries in MOD, then `BlendMode.prepare()` pre-computes diff maps for every parameter between stops. During the 10ms polling loop, the active `BlendMode` reads its input controller and sends only parameters whose values have actually changed — MIDI-bound parameters are automatically excluded to prevent conflicts with CC control.

```
# Tempo
GET  /get_bpm                            # Get current BPM
POST /set_bpm                            # Sets curent BPM
```

REST covers pedalboard and snapshot operations the current BPM. Plugin bypass/parameters and outgoing tap tempo use WebSocket.

The blend system is in `blend/`: `manager.py` (lifecycle, input wiring), `snapshot.py` (creation/sync), `parameter_setter.py` (WS diff sender), `input_controller.py` (analog input adapter), `easing.py` (interpolation curves), `stop.py` (diff map computation).

## Core Components

### Footswitches (`pistomp/footswitch.py`)

A footswitch can be bound to one of: **MIDI CC** (default), **Relay Bypass** (toggles a hardware relay on longpress), **Preset Change** (calls an increment/decrement callback), or **Tap Tempo** (intercepts presses when enabled). Priority order on press: tap tempo > preset > MIDI CC. Relay bypass fires on longpress regardless.

**Longpress groups** (`Footswitch.all_longpress_groups`): class-level dict of group names → timestamp lists. When two footswitches in the same group are pressed within 400ms, the group callback fires (e.g. `next_snapshot`, `previous_snapshot`, `toggle_bypass`). A single footswitch in a group fires its callback after 400ms hold.

Physical input comes from `GpioSwitch` (GPIO pin, debounced) or `AnalogSwitch` (ADC threshold). `GpioSwitch` calls `callback(state)` on release and `longpress_callback(state)` on long press — both receive a `switchstate.Value` enum (`RELEASED`, `LONGPRESSED`), with no extra args. `AnalogSwitch` uses a single `callback(state)` where `state` can be `PRESSED`, `LONGPRESSED`, or `RELEASED`.

Config overlay per pedalboard can change MIDI CC, relay binding, preset, color, and longpress groups.

### Encoders (`pistomp/encoder.py`, `pistomp/encodermidicontrol.py`)

`Encoder` is GPIO-based quadrature decoding with direction callback. `EncoderMidiControl` extends it to send MIDI CC on rotation (v3 tweak encoders). Encoder buttons are `GpioSwitch` instances with `callback=handler.universal_encoder_sw` and configurable `longpress_callback` (a handler method name from config, e.g. `previous_snapshot`).

The v1/v2 handler (`Mod`) manages encoder state explicitly via `TopEncoderMode`, `BotEncoderMode`, `UniversalEncoderMode` enums. The v3 handler (`Modhandler`) delegates navigation to the LCD (`lcd.enc_step()`, `lcd.enc_sw()`).

### Analog Controls (`pistomp/analogmidicontrol.py`)

Reads 10-bit ADC (0–1023) via MCP3008 SPI, converts to MIDI CC (0–127) using `as_midi_value()`. Threshold-based change detection prevents jitter. `_clamp_endpoints()` forces values near 0 or 1023 to exact endpoints, ensuring full-range input despite ADC noise.

Types: `KNOB` and `EXPRESSION` (config-driven). When `autosync: true`, `initialize()` reads the ADC and sends current position on pedalboard load, preventing stale state after switching.

### LCD System

- **v1**: `pistomp/lcdgfx.py` — monochrome 128×64 display via gfxhat library. Direct PIL/ImageDraw rendering into fixed zones. No handler reference.
- **v2/v3**: `pistomp/lcd320x240.py` — color 320×240 display. Widget-based UI (`uilib/`). Builder pattern constructs panels from pedalboard data. Receives handler reference for UI action callbacks.

### WebSocket Bridge (`modalapi/websocket_bridge.py`, `modalapi/ws_protocol.py`)

`AsyncWebSocketBridge` manages a background daemon thread that owns the WebSocket connection. Queues:
- **Outbound**: `command_queue` (unbounded — never drops blend-mode messages). `send_parameter(instance_id, symbol, value)` and `send_bpm(bpm)` enqueue typed commands. Backpressure monitoring: if the TCP write buffer exceeds 8KB, outbound sends return `False` until it drains.
- **Inbound**: `received_queue`, drained by `get_received_messages()` on every 10ms tick. `output_set` messages (audio meters) are dropped at reception.

`ws_protocol.py` parses raw text into typed dataclasses: `PluginBypassMessage`, `ParamSetMessage`, `AddPluginMessage`, `LoadingEndMessage`, `PedalSnapshotMessage`.

`ping` messages receive a `pong` reply; `data_ready` messages are echoed back.

## Data Flow

### Expression Pedal Movement

```
poll_controls() (10ms)
  → AnalogMidiControl.refresh()
    → ADC read → _clamp_endpoints() → as_midi_value()
      → midiout.send_message([0xB0|ch, CC, value])
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
          → bind_current_pedalboard() — map controllers to parameters
          → lcd.link_data() → lcd.draw_main_panel()
          → Prepare blend modes if configured
```

### Footswitch Press → Plugin Bypass

```
poll_controls()
  → Footswitch.pressed(state)
    → self.toggled = not self.toggled
    → midiout.send_message([ch|CC, CC, 127 if toggled else 0])
    → if unbound: update LED locally (drives_display == true)

mod-ui applies bypass, broadcasts via WebSocket
  → poll_ws_messages() → parse_message()
    → PluginBypassMessage → plugin.set_bypass(v)
    → lcd.refresh_plugins()
```

### Footswitch Press → Non-Footswitch Toggle

For controls that go through WebSocket rather than MIDI (e.g., parameter edits from the LCD):

```
UI interaction → ws_bridge.send_parameter(instance_id, symbol, value)
  → ... no local state change ...
mod-ui echoes back → ParamSetMessage → param.value = value
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

**Controls**:
- `pistomp/footswitch.py` — Footswitch modes, longpress groups
- `pistomp/encoder.py` — Quadrature decoding
- `pistomp/encodermidicontrol.py` — Encoder → MIDI CC
- `pistomp/analogmidicontrol.py` — ADC → MIDI CC with endpoint clamping
- `pistomp/gpioswitch.py` — GPIO button with press/longpress detection
- `pistomp/analogswitch.py` — ADC button with threshold detection

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
- `uilib/` — Widget library (panels, text, icons, menus, dialogs)

## Design Principles

- **Polling over events** — Fixed-frequency loops for predictable timing; 10ms critical path
- **Explicit version routing** — Factory pattern with known version checks, not capability detection
- **Overlay, don't replace** — Per-pedalboard config merges with defaults at field level
- **Single writer** — MOD-UI owns bypass/parameter state; pi-Stomp emits and waits for echo
- **Incremental updates** — `reinit()` updates objects in-place; blend diff maps are pre-computed
- **Trust MOD for audio** — pi-Stomp is a controller; audio processing lives in mod-host
- **Fail gracefully** — Log warnings, continue operation where possible

## On-Device Testing

```bash
curl -X POST http://localhost:80/pedalboard/load_bundle/ \
  -d 'bundlepath=/home/pistomp/data/.pedalboards/AmpBud.pedalboard'

curl -s http://localhost:80/pedalboard/list | python3 -m json.tool
```
