# Guide for piStomp Development

## Remote Development

**SSH Access**: `ssh pistomp@pistomp.local`

## Service Management

```bash
# Control piStomp service
ps-restart
ps-run
ps-stop

# View logs (live)
sudo journalctl -u mod-ala-pi-stomp -f

# View recent logs
sudo journalctl -u mod-ala-pi-stomp -n 50
```

## Deployment Workflow

### Local development

```bash
# 1. Edit files locally in /Users/cam/dev/pi-stomp/
# 2. Copy Python files to device
scp modalapi/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/modalapi/

# 3. Restart the service
ssh pistomp@pistomp.local "ps-restart"
```

### Mounting the SSH folder

The remote filesystem can also be mounted into a local directory using sshfs, depending on OS support. For example:

```bash
sshfs pistomp@pistomp.local:/home/pistomp <LOCAL_DIR> -o defer_permissions -o volname=Server
```

## Key Data Paths

- **Code**: `/home/pistomp/pi-stomp/`
- **Data**: `/home/pistomp/data/`
- **Config**: `/home/pistomp/data/config/`
- **Pedalboards**: `/home/pistomp/data/.pedalboards/`
- **Service**: `/lib/systemd/system/mod-ala-pi-stomp.service`

## Testing Changes

```bash
# Test pedalboard switch via API
curl -X POST http://localhost:80/pedalboard/load_bundle/ \
  -d 'bundlepath=/home/pistomp/data/.pedalboards/AmpBud.pedalboard'

# List pedalboards
curl -s http://localhost:80/pedalboard/list | python3 -m json.tool
```

## Hardware Versions

- **v1/v2**: Uses `modalapi/mod.py`
- **v3**: Uses `modalapi/modhandler.py` (current device)

## Python Environment

- Service runs as `root` with Python 3.11
- Uses unbuffered mode (`python3 -u`) for proper logging
- Dependencies installed system-wide via `pip3`

## MIDI Routing Architecture

### Single MIDI Source Design

piStomp uses **ALSA MIDI Through port 14** for all MIDI routing:

```
Hardware Controls (Footswitches, Rotary Encoders, Expression Pedals)
    ↓
ALSA MIDI Through (port 14:0)
    ↓
JACK (bridges via `-X seq`)
    ↓
    ├─→ mod-host:midi_in (MIDI Learn for parameter control)
    │   Auto-connected in separated mode via PortRegistration callback
    │
    └─→ Available in MOD-UI for manual wiring
        ↓
        LV2 MIDI plugins (CC Map, Channel Map, Filter, etc.)
        ↓
        External MIDI Devices (C4, HX Stomp, etc.)
```


### Which Controls Send MIDI?

- ✅ Expression Pedal (CC 75) - sends to virtual port
- ✅ Footswitches (CC 60-63) - send to virtual port when pressed
- ✅ Rotary Encoder Rotation (Tweak1=CC70, Tweak2=CC71) - send to virtual port
- ✅ Encoder Button Presses - Can optionally send MIDI via `shortpress` config (see below)

### Encoder Button Configuration (v3 only)

Encoder buttons support configurable `shortpress` callbacks:

```yaml
encoders:
  - id: 1
    midi_CC: 70  # Rotation
    longpress: previous_snapshot
    shortpress: universal_encoder_sw  # Default if omitted

  - id: 2
    midi_CC: 71
    shortpress:
      callback: send_midi_cc
      args: {cc: 72}  # Button sends CC 72 to virtual port
```

Shortpress accepts string (callback name) or object with `callback` and `args` (expanded as kwargs).

#### Implementation Details

| Control | Shortpress | Longpress |
|---------|------------|-----------|
| Encoder | String or `{callback, args}` via `encoderconfig.parse_shortpress_config()` | String only (no args) |
| Footswitch | Hardcoded (toggle/MIDI) - no config | String or list (group names) - no args |
| `GpioSwitch` | `callback_arg` (dict→kwargs, value→arg, None) | `longpress_callback_arg` (dict→kwargs, value→arg, None) |
| `AnalogSwitch` | Single `callback(state)` - no separate longpress | Same callback, state=LONGPRESSED |

### External Device Sync

- Pedalboard load triggers MIDI messages to external devices (e.g., Source Audio C4)
- Configured via `hardware.external_midi` in default config and per-pedalboard config.yml
- See `setup/config_templates/default_config_pistomptre.yml` for example configuration

### Analog Control State Sync

- On pedalboard load, all analog controls send initial position to MIDI Through if `autosync=True` (via config)
- MIDI flows to MIDI Through port 14:0 → available to LV2 MIDI plugins in pedalboard
- Prevents state mismatch - no need to wiggle pedals after switching pedalboards
- Implemented via `AnalogMidiControl.initialize()`
- Works for both v1/v2 (`mod.py`) and v3 (`modhandler.py`) hardware

## Key Development Principles

### Hardware-First Design
- **Polling over events** - Fixed-frequency loops for predictable timing (10ms critical path)
- **Direct hardware access** - No HAL layer, direct SPI/GPIO/MIDI interaction
- **Real-time constraints** - Never block in critical path, separate frequencies by priority
- **Hardware reality drives architecture** - Embrace limitations (ADC polling, SPI timing)
- **ADC endpoint clamping** - Ensure full range of inputs is not prevented by hysteresis

### Version Handling
- **Explicit version routing** - Factory pattern with known version checks, not capability detection
- **Shared base class** - Common functionality in `Hardware`, version-specific in subclasses
- **No breaking changes** - New features extend, don't replace (v1/v2/v3 all supported)

### Configuration Philosophy
- **Overlay, don't replace** - Pedalboard config merges with defaults at field level
- **Minimal config files** - Users specify only what changes from default
- **Config-driven behavior** - Callbacks by name, extensible without code changes
- **Safe defaults always** - Missing config keys use sensible defaults

### State Management
- **Incremental updates** - `reinit()` pattern updates objects in-place, no recreation
- **Shared class state where needed** - Footswitch groups coordinate via class-level dicts
- **Explicit state machines** - Encoder modes (v1/v2) use clear state enums
- **Timestamp-based change detection** - File mtimes for MOD sync, not polling APIs

### MOD Integration
- **Direct REST calls** - No SDK abstraction, just `requests` to `localhost:80`
- **LILV for local parsing** - Parse `.ttl` bundles locally for performance and rich data
- **Trust MOD for audio** - piStomp is controller interface, not audio processor
- **Sync on change** - Reload pedalboard data when MOD writes `last.json`

### Code Organization
- **Factories for versioning** - `Handlerfactory` and `Hardwarefactory` route versions
- **Handlers = business logic** - `mod.py`/`modhandler.py` orchestrate system
- **Hardware = physical** - Hardware classes only talk to GPIO/SPI/ADC
- **Callbacks for extensibility** - Handler methods exposed by name in config

### MIDI Architecture
- **Single MIDI sink** - All hardware controls send to ALSA MIDI Through port 14:0
- **Direct routing** - Hardware controls → MIDI Through → JACK → mod-host
- **Lazy port initialization** - External MIDI ports opened on first use
- **Sync on pedalboard load** - Send analog positions + external MIDI messages

### Development Guidelines
- **Pragmatic over perfect** - Simple solutions over complex abstractions
- **Explicit over implicit** - Clear code paths, minimal magic
- **Configuration over compilation** - Users customize via YAML, not Python
- **Fail gracefully** - Log warnings, continue operation where possible

### When Extending
- **New hardware version?** Add factory branch, inherit from `Hardware`
- **New footswitch action?** Add handler method, reference by name in config
- **New config field?** Add to TypedDict, handle in `reinit()` or `update_config()`
- **New MIDI routing?** Modify `MidiOut` or `ExternalMidiManager`
- **Performance issue?** Check polling loop frequency first

## System Architecture

### Entry Point & Main Loop

**`modalapistomp.py`** - System initialization and polling loop

```python
# Startup sequence
1. Parse CLI args (log level, host type)
2. Initialize audio card (early for audio pass-through)
3. Create MIDI output to ALSA MIDI Through port 14:0
4. Create handler (Mod or Modhandler) via Handlerfactory
5. Create hardware (Pistomp/Core/Tre) via Hardwarefactory with midiout
6. Load pedalboards from MOD API (parsed via LILV)
7. Load current pedalboard and initialize hardware
```

**Polling Loop (Different Frequencies)**:
- `10ms`: `poll_controls()` - Read hardware inputs (critical path)
- `20ms`: `poll_indicators()` - Update LEDs/VU meters
- `200ms`: `poll_lcd_updates()` - Render LCD
- `1000ms`: `poll_modui_changes()` - Sync with MOD UI changes
- `2000ms`: `poll_wifi()` - Update WiFi status
- `60s`: `poll_system_info()` - System health (CPU, throttling)

### Hardware Version Selection

**Factory Pattern** routes version-specific implementations:

```python
# Handlerfactory (business logic)
< 2.0     → Mod (v1)
>= 2.0    → Modhandler (v2/v3)

# Hardwarefactory (physical interface)
< 2.0     → Pistomp (v1: dual encoders, 3 switches, mono LCD)
>= 2.0 < 3.0 → Pistompcore (v2: single encoder, color LCD, relay)
>= 3.0    → Pistomptre (v3: 4 encoders, LED strip, VU meters)
```

**All inherit from `Hardware` base class** - provides common functionality:
- `reinit(cfg)` - Reload config on pedalboard change
- `poll_controls()` - Read all inputs
- SPI/ADC communication
- Controller dictionary: `{channel:CC}` → controller object

### Configuration System

**Two-Layer Config Overlay**:

```
Default Config (global)
  ↓ loaded at startup
Hardware objects created
  ↓ pedalboard load
Pedalboard Config (overlay)
  ↓ hardware.reinit(cfg)
Config merged and applied
```

**Config Files**:
- Global: `/home/pistomp/data/config/default_config.yml` (or built-in templates)
- Per-pedalboard: `{pedalboard}.pedalboard/config.yml`

**Overlay Strategy**: Pedalboard config overrides only specified fields
- Example: Change footswitch MIDI CC for specific pedalboard
- Fields not specified keep default values

### MOD Integration

**HTTP REST API** to `localhost:80`:

```bash
# Pedalboard operations
GET  /pedalboard/list                    # List all pedalboards
POST /pedalboard/load_bundle/            # Load pedalboard
POST /pedalboard/save                    # Save state

# Snapshot/preset operations
GET /snapshot/list                       # Get all snapshots
GET /snapshot/load?id={n}                # Load snapshot n

# Parameter control
POST /effect/parameter/pi_stomp_set//graph{id}/{symbol}  # Set parameter
GET  /effect/parameter/pi_stomp_get//graph{id}/:bypass   # Get bypass state

# Tempo
POST /set_bpm                            # Set tap tempo
GET  /get_bpm                            # Get current BPM
```

**Pedalboard Data Loading** via LILV (LV2 bundle parser):
1. Parse `.ttl` files in pedalboard bundle
2. Extract plugin chain (tail-chase audio connections)
3. For each plugin: instance ID, parameters (min/max/value), MIDI bindings
4. Create `Pedalboard` object with `Plugin` and `Parameter` objects

**Change Detection**:
- Watches `/home/pistomp/data/last.json` timestamp
- MOD UI writes this when pedalboard changes
- piStomp detects → reloads pedalboard → syncs hardware

**Banks** (v3 only):
- Pedalboard grouping/ordering managed by MOD-UI
- File: `/home/pistomp/data/banks.json` (read-only to piStomp)
- Polled via mtime check (1000ms) in `poll_modui_changes()`
- Structure: `{bank_name: [pedalboard_titles]}`
- Current selection persisted in `settings.yml`
- Filters pedalboard menu if bank selected, shows all if None

### Core Components

**Footswitches** (`pistomp/footswitch.py`):
- **Modes**: MIDI CC, Relay Bypass, Preset Change, Tap Tempo
- **Longpress Groups**: Shared class-level state for multi-switch actions
  - Two switches in group pressed within 400ms → group callback
  - Examples: `next_snapshot`, `previous_snapshot`, `toggle_bypass`
- **Config Overlay**: Per-pedalboard override of MIDI CC, bypass, preset, color
- **Physical**: GPIO-based (`gpioswitch.py`) or ADC-based (`analogswitch.py`)

**Encoders** (`pistomp/encoder.py`, `pistomp/encodermidicontrol.py`):
- **Base**: Quadrature decoding, GPIO interrupts, debounce
- **MIDI Control**: Sends CC on rotation (v3 tweak encoders)
- **Buttons**: Configurable shortpress (callback + args) and longpress
- **State Machines** (v1/v2 only): `TopEncoderMode`, `BotEncoderMode`, `UniversalEncoderMode`

**Analog Controls** (`pistomp/analogmidicontrol.py`):
- Read 10-bit ADC via MCP3008 SPI chip
- Convert to MIDI CC (0-127) with threshold-based change detection
- Types: `KNOB`, `EXPRESSION`
- `send_current_value()` forces sync on pedalboard load

**LCD System**:
- **v1**: `lcdgfx.py` - Monochrome text display
- **v2/v3**: `lcd320x240.py` - Color GUI with widget-based UI library (`uilib/`)
  - Builder pattern constructs UI from pedalboard data
  - Event-driven updates via `link_data()`

### Data Flow Examples

**Expression Pedal Movement**:

```
poll_controls() (10ms)
  → AnalogMidiControl.refresh()
    → ADC read (0-1023) → MIDI CC (0-127)
      → midiout.send_message([0xB0|ch, 75, value])
        → ALSA MIDI Through (port 14:0)
          → JACK (bridged via -X seq)
            ├→ mod-host:midi_in (MIDI Learn / parameter control)
            └→ Available in MOD-UI for wiring to LV2 MIDI plugins
                → External MIDI devices (if wired through plugins)
```

**Pedalboard Change (via MOD UI)**:

```
MOD-UI writes /home/pistomp/data/last.json
  → poll_modui_changes() detects timestamp change (1000ms)
    → reload_pedalboard(bundle)
      → LILV parses TTL → creates Pedalboard object
        → set_current_pedalboard(pb)
          → Load {bundle}/config.yml
          → hardware.reinit(cfg) - overlay config
          → bind_current_pedalboard() - map controllers to parameters
          → external_midi.send_messages_for_pedalboard()
          → update_lcd()
```

**Footswitch Press → Plugin Bypass**:

```
poll_controls()
  → Footswitch.poll() → detect press
    → footswitch.pressed()
      → Toggle self.enabled
      → Update LED
      → Send MIDI CC (if configured)
      → Update bound parameter.value (e.g., :bypass)
      → refresh_callback(footswitch=self)
        → Handler.update_lcd_fs()
          → LCD.update_footswitch() - redraw indicator
```

### Key Files

**Entry & Factories**:
- `modalapistomp.py` - Main entry point and polling loop
- `pistomp/handlerfactory.py` - Handler version selection
- `pistomp/hardwarefactory.py` - Hardware version selection

**Handlers** (Business Logic):
- `pistomp/handler.py` - Abstract base
- `modalapi/mod.py` - v1/v2 handler
- `modalapi/modhandler.py` - v3 handler

**Hardware** (Physical Interface):
- `pistomp/hardware.py` - Base abstraction
- `pistomp/pistomp.py` - v1 implementation
- `pistomp/pistompcore.py` - v2 implementation
- `pistomp/pistomptre.py` - v3 implementation

**Controls**:
- `pistomp/footswitch.py` - Footswitch logic, longpress groups
- `pistomp/encoder.py` - Rotary encoder decoding
- `pistomp/encodermidicontrol.py` - Encoder with MIDI output
- `pistomp/analogmidicontrol.py` - ADC-based MIDI controller

**MIDI**:
- `pistomp/midiout.py` - MIDI output to ALSA MIDI Through
- `modalapi/external_midi.py` - External device sync

**MOD API**:
- `modalapi/pedalboard.py` - LILV parser
- `common/parameter.py` - Parameter representation & formatting
- `modalapi/plugin.py` - Plugin representation

**Config & State**:
- `pistomp/config.py` - Config loading/validation
- `pistomp/settings.py` - Persistent settings (JSON)

**Display**:
- `pistomp/lcd320x240.py` - Color LCD (v2/v3)
- `pistomp/lcdgfx.py` - Mono LCD (v1)
- `uilib/*` - Widget library (v3)
