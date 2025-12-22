# Claude Code Guide for piStomp Development

## Remote Development

**SSH Access**: `ssh pistomp@pistomp.local`

## Service Management

```bash
# Restart piStomp service
sudo systemctl restart mod-ala-pi-stomp

# View logs (live)
sudo journalctl -u mod-ala-pi-stomp -f

# View recent logs
sudo journalctl -u mod-ala-pi-stomp -n 50
```

## Deployment Workflow

```bash
# 1. Edit files locally in /Users/cam/dev/pi-stomp/
# 2. Copy Python files to device
scp modalapi/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/modalapi/

# 3. Clear Python cache and restart
ssh pistomp@pistomp.local "rm -rf /home/pistomp/pi-stomp/modalapi/__pycache__/* && sudo systemctl restart mod-ala-pi-stomp"
```

## Key Paths

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

### Hardware Controls → Virtual MIDI Port

```
Hardware Controls (Footswitches, Rotary Encoders, Expression Pedals)
    ↓
MidiOutHandler (wrapper intercepts all MIDI CCs)
    ↓
├─→ MOD-UI (internal MIDI routing)
└─→ send_passthrough_cc()
        ↓
    Virtual Port "piStomp-MIDI" (created by amidithru)
        ↓
    MOD Pedalboard (LV2 MIDI plugins: CC Map, Channel Map, Filter, etc.)
        ↓
    External MIDI Devices (C4, HX Stomp, etc.)
```

### Which Controls Send MIDI?

- ✅ Expression Pedal (CC 75) - rotates and sends to virtual port
- ✅ Footswitches (CC 60-63) - send to virtual port when pressed
- ✅ Rotary Encoder Rotation (Tweak1=CC70, Tweak2=CC71) - send to virtual port
- ❌ Encoder Button Presses - handled by `gpioswitch.py`, no MIDI sent (used for snapshots/navigation)

### External Device Sync

- Pedalboard load triggers MIDI messages to external devices (e.g., Source Audio C4)
- Configured via `/home/pistomp/data/config/external_midi.yml`
- See `setup/config_templates/external_midi.yml.example` for documentation
