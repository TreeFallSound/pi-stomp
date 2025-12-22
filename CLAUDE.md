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

**Expression Pedal → MOD Integration:**
- Hardware expression pedal (ADC) read by `pistomp/analogmidicontrol.py`
- MIDI messages sent to virtual ALSA port via `modalapi/external_midi.py`
- Virtual port created using `amidithru` subprocess (appears in MOD as "piStomp Expression MIDI 1")
- All routing handled in MOD pedalboard using LV2 MIDI plugins (CC Map, Channel Map, etc.)

**External Device Sync:**
- Pedalboard load triggers MIDI messages to external devices (e.g., Source Audio C4)
- Configured via `/home/pistomp/data/config/external_midi.yml`
- See `setup/config_templates/external_midi.yml.example` for documentation
