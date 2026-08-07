# Bluetooth menu

## Context

The OS side of Bluetooth already works and is deliberately tiny. `pi-gen-pistomp`
`feat/bluetooth` adds `bluez` + `Experimental = true` in `/etc/bluetooth/main.conf`
(which activates bluez's built-in MIDI GATT plugin), an rfkill-unblock drop-in on
`bluetooth.service`, and a `BLUETOOTH_ENABLED="false"` flag in `pistomp.conf`. Once a
BLE-MIDI device is *connected*, bluez publishes an ALSA seq port and `jackd -X seq`
bridges it into JACK automatically — mod-ui needs no help and pi-Stomp needs no MIDI
code.

Three things do not exist and are ours:

- **No pairing agent is registered anywhere on the image.** With no `org.bluez.Agent1`
  owner and `AlwaysPairable` unset, pairing cannot complete headlessly at all. This is
  the load-bearing gap; everything else is UI.
- **No trust or reconnect policy.** `[Policy] ReconnectUUIDs` doesn't cover the MIDI
  UUID, so a device must be paired *and* trusted for bluez to auto-accept its
  reconnection.
- **No on/off control after first boot.** `BLUETOOTH_ENABLED` is consumed once by
  `firstboot.sh`, which then renames itself to `firstboot.done`.

Bluetooth hardware exists on **Pi 5 only** — `config.txt` gives the BT UART to DIN MIDI
on Pi 3/4 via `dtoverlay=pi3-disable-bt`.

Outcome: a phone-style pair/connect/forget menu for BLE-MIDI devices, plus HID input
devices (presenters, page-turners, keyboards, mice) usable as wireless footswitches.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **D-Bus via `dbus-fast`**, added to `pyproject.toml` → uv venv | No pi-gen change for the Python side. Gives a persistent `org.bluez.Agent1` (required for headless pairing), `PropertiesChanged` signals for RSSI/Connected/Paired instead of polling, and clean `Pair`/`Connect` calls. We already run as root (`ps-run` uses sudo), so stock D-Bus policy suffices. |
| 2 | **Reuse `CommandQueue`**; `dbus-fast` replaces only its worker *thread's* job | The queue's real work — serialize, dedupe by `key()`, drain results on the main thread — is still exactly what we want. Each `Command.run()` blocks on `asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)`. `poll()`, `pending_op_count()`, exception-as-result and the whole test-fixture shape stay untouched. |
| 3 | **Entry point: a row in the Network (WiFi) menu** | Same conditional-row idiom as "Wired Connection" → `EthernetMenu`. Toolbar stays at 4 tiles (it is full: 210/240/270/296 at 20px on a 320px screen). |
| 4 | **No BT hardware → no row, no mention of Bluetooth anywhere** | Pi 3/4 users must not see a feature their board cannot have. |
| 5 | **Menu owns enable/disable**; no `pistomp.conf` write-back | `systemctl enable --now bluetooth` persists on its own (it writes a symlink), so the firstboot flag never needs rewriting. Avoids touching the boot partition at runtime. |
| 6 | **Nearby list shows only MIDI and HID devices** | Everything else (phones, laptops, beacons, fitness trackers) is noise we can do nothing with. Predicate in §"Device filter". |
| 7 | **Pair + trust + connect is one action** | The three-way distinction is bluez's model, not the user's. Trust-on-pair is also what makes reconnection work at all (see Context). |
| 8 | **HID devices emit MIDI CC, and arrows/wheel synthesize NAV** | CC emission means mod-ui's existing MIDI-learn maps them like any footswitch — no new config surface, and it is what the MIDI-learn axiom in `pistomp/input/README.md` prescribes. NAV synthesis lets a cheap presenter drive the entire menu system. |
| 9 | **HID mappings live in `default_config*.yml`** | Same declarative shape as `footswitches:` / `encoders:`, including the `longpress: <callback_name>` idiom. |

## Cognitive-load design

The information architecture is the WiFi menu with the nouns swapped — which is also
what Android and iOS do, so it is the shape users already carry.

```
Bluetooth · EV-1-WL                     ← the title answers "is it working?"
  EV-1-WL  ✔                     ▮▮▮    ← paired; ✔ = connected right now
  R400 Presenter                        ← paired, out of range or disconnected
  Nearby devices...                     ← drill-in; scans only while open
  Turn Bluetooth off
  ⬅
```

- Tap a paired row → connect. Long-press → `Disconnect / Forget` submenu.
- Tap a nearby row → pair + trust + connect as one action, with in-row
  `Pairing…` / `Connecting…` text (there is no BT toolbar tile to spin).
- **An empty nearby list must read `No devices found. Put your device in pairing
  mode.`** BLE-MIDI peripherals only advertise while discoverable; this one string
  prevents more confusion than everything else in the feature combined.
- Paired rows carry a type badge (`M` = MIDI, `I` = input) so "why isn't this doing
  anything" has an on-screen answer.

## Device filter

A discovered device is shown iff it is already paired, **or** it has a real `Name`
**and** any of:

- `UUIDs` contains the BLE-MIDI service `03B80E5A-EDE8-4B33-A751-6CE34EC4C700`
- `UUIDs` contains HID-over-GATT `0x1812` or BR/EDR HID `0x1124`
- `Class` major device class is `0x05` (Peripheral)
- `Appearance` is in the HID category (`0x03C0`–`0x03C4`)

**Test `Name`, never `Alias`.** BlueZ populates `Alias` with a MAC-derived string
(`D4-06-0F-EE-16-83`) when the device has no name, so `Alias` is *always* truthy and
would let every beacon through. `Name` is absent on nameless devices — that is the
discriminator.

`Appearance` is the weakest arm: not one device in a live scan reported it. UUIDs are
the reliable signal; keep the `Appearance` and `Class` arms as belt-and-braces for
classic HID, but do not depend on them.

## Verified on hardware

Run against a Pi 5 (`Raspberry Pi 5 Model B Rev 1.0`, bluez 5.82-1.1+rpt1) with a BOSS
EV-1-WL. Findings that shaped the design above:

- **The MIDI plugin is compiled into Debian's bluez** (`profiles/midi/midi.c` and the
  `snd_midi_event_*` ALSA symbols are present in the `bluetoothd` binary), and it is
  gated on `Experimental = true` — with the stock config no MIDI profile registers.
- **The filter predicate holds.** Unpaired and pre-pair, the EV-1-WL advertises
  `03b80e5a-ede8-4b33-a751-6ce34ec4c700`, readable straight off `Device1.UUIDs`. A
  scan of the surrounding area returned five other devices, of which zero were useful
  (four nameless beacons, one Fitbit) — the unfiltered list would be pure noise.
- **The Pi 5 BT radio comes up rfkill soft-blocked** (`/sys/class/rfkill/rfkill0/soft`
  = 1), confirming the `feat/bluetooth` rfkill-unblock drop-in is load-bearing, not
  defensive. Note `rfkill` the CLI is not installed on the current image.
- **End-to-end chain confirmed.** After pair + trust + connect, `bluetoothd` published
  ALSA seq client `133: 'EV-1-WL'` port `EV-1-WL Bluetooth`, which JACK's `-X seq`
  bridged to `system:midi_capture_6` with alias `EV-1-WL:midi/capture_1`. Nothing in
  pi-Stomp had to touch MIDI.

### Discovery lifecycle (affects `ops.py`)

**BlueZ purges every unpaired LE device object the instant discovery stops** — the
`org.bluez.Device1` interface is removed and any subsequent `Pair()` fails with "not
available". Two requirements follow:

- The nearby list must hold `StartDiscovery()` open for as long as it is on screen, and
  `Pair()` must be issued against a live object **while discovery is still running**.
  Scan and pair cannot be independent serialized commands.
- Unpaired rows can vanish between refreshes as a matter of course. The `_rows_sig`
  rebuild path must treat disappearance as normal, never as an error.

Paired devices persist in `/var/lib/bluetooth` and are unaffected.

### Trust races the explicit pair

Setting `Trusted = true` makes bluez attempt a **background auto-connect the moment the
device is discovered**. If the UI then calls `Pair()`, that auto-connect is already
in flight and bluez returns `org.bluez.Error.InProgress`. Observed repeatedly: the only
pairings that succeeded were against a fresh, untrusted device.

So: **pair first, trust second** — never trust a device we have not finished pairing.
And treat `InProgress` as "an attempt is already running, wait for its result", not as a
failure to surface to the user.

### Addresses rotate; do not key state on MAC alone

BLE devices using resolvable private addresses re-randomise regularly — a Fitbit in the
room appeared under three different addresses (`74:9F:EF:44:A6:99`,
`55:4F:14:89:F7:5F`, `43:9C:27:65:0F:DB`) across one session. A "known devices" store
keyed purely on MAC will accumulate duplicates and fail to recognise returning devices.

The EV-1-WL itself is safe (`AddressType=static` — a random *static* address, which does
not rotate), and for bonded devices bluez resolves RPAs via the IRK. But the store
should key on MAC **plus** name, treat a MAC change under the same name as the same
device, and never present a raw MAC to the user as identity.

### Some devices never bond — and that changes the model

The EV-1-WL **refuses bonding at the protocol level**. From a `btmon` capture of the
SMP exchange:

```
Authentication requirement: Bonding, MITM, SC, No Keypresses, CT2 (0x2d)   ← BlueZ asks
Authentication requirement: No bonding, No MITM, Legacy, No Keypresses (0x00)  ← device refuses
```

An LTK is derived for the session, but the peer declared it must not be stored, so
`Bonded: no` and a `/var/lib/bluetooth/<adapter>/<mac>/info` containing only
`[General]` and `[ConnectionParameters]` is *correct behaviour*, not a fault. This was
confirmed independent of the client: it reproduces with the adapter `Pairable`, with
`JustWorksRepairing = always`, and when driving `bluetoothctl` under a real pty (ruling
out [bluez#748](https://github.com/bluez/bluez/issues/748), where piped stdin yields
`store_hint 0` and keys silently aren't persisted — still a good reason to prefer a
properly registered agent).

The consequence is severe and drives the UI: **for a non-bonding device, a plain
`Disconnect` sets `Paired` back to `no`.** There is no key, so there is nothing to be
paired with. Every reconnection — after sleep, going out of range, a power cycle, or a
`bluetoothd` restart — needs the device physically put back into pairing mode.

So there are two device classes, and the menu must express both:

| | Bonding device (most BLE-MIDI, HID) | Non-bonding device (EV-1-WL) |
|---|---|---|
| Survives disconnect | yes, stays paired | **no**, drops to unpaired |
| Survives reboot | yes | no |
| Reconnect | automatic, or a `Connect()` call | requires the physical pairing button |

Design consequences:

- **The paired list cannot come from bluez alone.** A non-bonding device vanishes from
  `Paired` the moment it disconnects, so it would silently disappear from the menu. Keep
  our own small "known devices" store (MAC → name, last connected) and render the root
  list from the union of that and bluez's paired set.
- **A known-but-disconnected row must say what to do**, not just "Disconnected" — e.g.
  `EV-1-WL · press its pairing button`. Tapping it should start discovery and pair as
  soon as it appears, so the user's only job is the button press.
- **Do not promise auto-reconnect in the UI.** Attempt it (it works for bonding
  devices), and fall back to the pairing-mode prompt when the device is gone.
- Forget = remove from our store *and* `RemoveDevice` from bluez.

## Architecture

Three layers, mirroring `modalapi/wifi/` exactly.

```
modalapi/bluetooth/
  __init__.py     re-export surface, like modalapi/wifi/__init__.py
  types.py        BtDevice TypedDict, DeviceKind enum, parse_bluez_error()
  bluez.py        dbus-fast client owning an asyncio loop in its own thread
  agent.py        org.bluez.Agent1, NoInputNoOutput (Just Works, no prompts)
  ops.py          stateless verbs: scan/pair/trust/connect/disconnect/remove
  manager.py      BluetoothManager: adapter-state thread + CommandQueue + poll()
  commands.py     ScanCmd, PairCmd, ConnectCmd, DisconnectCmd, ForgetCmd, PowerCmd
```

**Threading.** `bluez.py` starts one asyncio thread hosting the dbus-fast connection,
the agent, and the `InterfacesAdded` / `PropertiesChanged` subscriptions. Discovered
state is accumulated into a lock-guarded dict. `BluetoothManager.poll()` runs on the
main thread from `Modhandler.poll_bluetooth()` and does two things: drain the
`CommandQueue` result queue, and publish a changed adapter/device snapshot through
`on_status_change`. **No panel-stack mutation ever happens off the main thread** — the
`assert threading.current_thread() is threading.main_thread()` in `CommandQueue.poll`
stays.

**Signals instead of polling.** Unlike WiFi, there is no 5s status poll: bluez pushes
`PropertiesChanged`. The manager keeps a `changed` flag the same way `WifiManager` does,
so the handler-side contract is identical.

**The agent.** `NoInputNoOutput` — BLE MIDI is Just Works, so every pairing
auto-accepts and the user sees zero passkey prompts. Registered once at manager start
via `AgentManager1.RegisterAgent` + `RequestDefaultAgent`. We are central-only (bluez's
`midi` plugin is a GATT *client*), so the adapter never needs to be discoverable —
`Discoverable` stays false, which is also why an auto-accept agent is safe here.

## UI

```
ui/bluetooth_menu.py     BluetoothMenu — a plain controller, NOT a Panel
```

Modelled on `ui/wifi_menu.py`: holds `Optional[Menu]` refs, reaches the handler through
a structural `_BluetoothHost` Protocol, pushes menus via `lcd.draw_selection_menu`, and
copies these idioms verbatim:

- `_rows_sig()` content signature so RSSI jitter never triggers a rebuild
  (BT RSSI is noisier than WiFi's — this matters more here than there)
- `_rerender_*()` pop-and-rebuild preserving the cursor by `label_key`
- the `notify_status_change` modal guard (refuse to rebuild unless our menu is
  `pstack.current`, so a rebuild can't yank a dialog out from under the user)
- `MessageDialog` for every failure, success silent
- `Spacer()` + `SignalBarsGlyph` rich rows for right-aligned RSSI bars
- `PillGlyph` for the M/I type badge, as the wifi menu does for open networks

`declare_bindings()` returns `()` — a settings menu is NAV-only, which is the
documented default and the only thing v2 hardware has.

Wiring:

- `Lcd.__init__` (`pistomp/lcd320x240.py` ~L225) constructs `BluetoothMenu(self)`
  next to `self.wifi_menu`
- `WifiMenu._build_items` gains a conditional `"Bluetooth · <device> >"` row beside
  the existing `"Wired Connection"` row, gated on adapter presence
- `Modhandler.poll_bluetooth()` next to `poll_wifi`, called from the `period % 200`
  branch of `modalapistomp.py`

## HID input

```
pistomp/hid_controller.py   HidController(Controller) + HidDeviceWatcher
```

`ControlRef.id` already accepts `str` for footswitch-class identity (`"channel:CC"`
today), so a HID button is `"hid:<mac>:KEY_PAGEDOWN"` with **no schema change**. The
controller fits the existing source/sink model: `poll_hw()` does a non-blocking read of
`/dev/input/eventN` and packages a `SwitchEvent`, exactly as a GPIO footswitch does.

No new dependency: a Linux input event is a fixed 24-byte struct on 64-bit, so
`struct.unpack` beats pulling in `python-evdev` (a C extension with thin aarch64 wheel
coverage). Open the fd `O_NONBLOCK` and drain it each tick.

`HidDeviceWatcher` rescans `/dev/input/by-id/*` on the 2s poll to pick up hotplug when
a device pairs or reconnects — no udev rule, no root-owned daemon.

Config, alongside `footswitches:` and `encoders:`:

```yaml
  # hid_controllers:
  # Bluetooth or USB HID devices — presenters, page-turners, keyboards, mice.
  # key: <KEY_ name>             The Linux keycode the device emits (required)
  # midi_CC: <integer>           CC sent on press; MIDI-learn it in MOD-UI (optional)
  # nav: <left|right|click>      Synthesize a NAV event instead of / as well as CC
  # longpress: <callback_name>   Handler method on long press (optional)
  hid_controllers:
    - key: KEY_PAGEDOWN
      midi_CC: 80
    - key: KEY_PAGEUP
      midi_CC: 81
      longpress: previous_snapshot
    - key: KEY_RIGHT
      nav: right
    - key: KEY_LEFT
      nav: left
    - key: KEY_ENTER
      nav: click
```

Synthesizing NAV from a HID key does **not** violate the NAV axiom: the axiom forbids
panels from *consuming* raw NAV events and forbids `cls=NAV` binding rows. A new
physical *source* producing NAV events is the intended shape, and is worth real
consideration for v2 hardware, where NAV is the only control.

The schema in `pistomp/config.py` (the dict literal at L28) gains a `hid_controllers`
array; `longpress` reuses the existing callback-name enum.

## Implementation tree

```
pi-stomp/
├── pyproject.toml                        + dbus-fast dep      → run `uv sync`
├── uv.lock                               regenerated
├── docs/bluetooth-menu.md                this file
│
├── modalapi/bluetooth/                   NEW — mirrors modalapi/wifi/
│   ├── __init__.py
│   ├── types.py                          BtDevice, DeviceKind, parse_bluez_error
│   ├── bluez.py                          dbus-fast client + asyncio thread
│   ├── agent.py                          org.bluez.Agent1 (NoInputNoOutput)
│   ├── ops.py                            scan/pair/trust/connect/disconnect/remove
│   ├── commands.py                       Command subclasses (reuses wifi CommandQueue)
│   └── manager.py                        BluetoothManager
│
├── ui/bluetooth_menu.py                  NEW — BluetoothMenu controller
│
├── pistomp/
│   ├── hid_controller.py                 NEW — HidController + HidDeviceWatcher
│   ├── config.py                         + hid_controllers schema (L28 dict)
│   └── lcd320x240.py                     + self.bluetooth_menu (~L225)
│
├── ui/wifi_menu.py                       + conditional "Bluetooth ·  >" row
├── modalapi/modhandler.py                + poll_bluetooth(), + hid controller wiring
├── modalapistomp.py                      + poll_bluetooth() in the period%200 branch
├── emulator/stubs.py                     + StubBluetoothManager
├── emulator/modhandler.py                + swap in the stub
├── setup/config_templates/
│   └── default_config_pistomptre.yml     + commented hid_controllers example
│
└── tests/
    ├── test_bluetooth_manager.py         NEW — ops/manager against a mocked bluez
    ├── test_hid_controller.py            NEW — struct decode, event synthesis
    ├── v3/conftest.py                    + bluetooth_state fixture (inline queue shim)
    ├── v3/test_bluetooth_menu.py         NEW — snapshot suite
    └── snapshots/v3/test_bluetooth_menu/ NEW baselines
```

Nothing in `pi-gen-pistomp` changes for the Python side.

## What pi-gen-pistomp must provide

Written to be implemented on a **fresh branch**; do not assume `feat/bluetooth`
survives. Everything below was verified on a live Pi 5 running the current image.

### Required

1. **A `bluetooth.service` drop-in** at
   `stage2/05-pistomp/files/services/pistomp.conf` →
   `/etc/systemd/system/bluetooth.service.d/pistomp.conf`:

   ```ini
   # pi-stomp: -E activates bluez's BLE-MIDI GATT plugin (an experimental profile);
   # without it no ALSA seq port is ever created. The Pi 5 BT radio boots
   # rfkill soft-blocked, which leaves the adapter PowerState=off-blocked.
   [Service]
   ExecStartPre=-/bin/sh -c 'for f in /sys/class/rfkill/*; do [ "$(cat $f/type)" = bluetooth ] && echo 0 > $f/soft; done'
   ExecStart=
   ExecStart=/usr/libexec/bluetooth/bluetoothd -E
   ```

   This one file replaces three things `feat/bluetooth` used: the 374-line `main.conf`
   copy, the `rfkill` package, and a separate rfkill drop-in. Verified: with
   `main.conf` at stock and the radio deliberately re-blocked, the adapter still comes
   up `Powered: yes` and experimental profiles still probe.

2. **Remove the unconditional Bluetooth disable from `firstboot.sh`.** `main` currently
   runs `systemctl disable --now bluetooth.service hciuart.service`. Bluetooth stays
   off until that line goes.

3. `bluez` — already installed on `main` (`stage2/01-sys-tweaks/00-packages`). Debian
   trixie ships 5.82 built with the MIDI plugin; no rebuild, no pin.

### Not needed — do not carry these over

| `feat/bluetooth` change | Why not |
|---|---|
| `bluetooth-main.conf` (374 lines) | `main.conf` is a **dpkg conffile**; shipping a copy means owning it forever and taking a conffile conflict on every bluez upgrade. `-E` in the drop-in gets the same result with no ownership. |
| `BLUETOOTH_ENABLED` in `pistomp.conf` | The menu owns enable/disable at runtime. The flag is also first-boot-only, so it silently does nothing when edited later — a trap, not a feature. |
| `firstboot.sh` conditional enable/disable | Falls out with the flag. |
| `rfkill` package (+ the `00-packages-nr` comment) | The drop-in's `ExecStartPre` unblocks via sysfs, keyed on `type` = `bluetooth` so it doesn't depend on the rfkill index. |
| separate `bluetooth-rfkill-unblock.conf` | Folded into the single drop-in. |
| anything touching `hciuart.service` | `pi-bluetooth` is not installed, so the unit does not exist and the call is a no-op swallowed by `|| true`. Pi 5 attaches BT over serdev (`hci_uart` + `btbcm`, `hci0 Bus: UART`). |
| `debpkgs/mod-ui/debian/changelog` | Unrelated (session recording) — it rode along on the branch. |

### Possibly required — pending the bonding investigation

`JustWorksRepairing` and adapter `Pairable` may need to be set. `Pairable` is an
adapter property the UI can set over D-Bus at runtime (preferred — no image change).
`JustWorksRepairing` is `main.conf`-only, so if it proves necessary the cheapest form
is a targeted `sed` of the packaged file during the build, not a wholesale copy.

## Verification

**Unit / snapshot** — `uv run pytest`, `uv run pyright` clean.

Mirror the wifi suite's categories, which are the ones that caught real bugs there:
multi-frame sagas via a deferred-callback list; scan pacing (`tick()` must not rescan
while the root menu is open); parametrized error kinds; modal-safety (a status change
must not close an open dialog); and pure-function tests of the filter predicate with no
fixture. The `bluetooth_state` fixture copies `wifi_state`'s inline `CommandQueue` shim
so callbacks fire synchronously and no worker thread runs under pytest.

State the expected snapshot changes before running `--snapshot-update`: the WiFi root
menu baselines gain a Bluetooth row and must be regenerated; everything else is new.

**Device state left behind by the investigation** (pistomp.local, 2026-08-06). None of
this is required by the implementation; it is recorded so it can be undone or
reproduced:

1. `echo 0 > /sys/class/rfkill/rfkill0/soft` — radio unblocked. Non-persistent.
2. `systemctl start bluetooth` — `start`, not `enable`. Non-persistent.
3. `/etc/bluetooth/main.conf` line 128 `Experimental = true` — **reverted** to the
   stock `#Experimental = false`; experimental now comes from `-E` in the drop-in.
4. `/etc/bluetooth/main.conf` line 104 `#JustWorksRepairing = never` →
   `JustWorksRepairing = always`. **Persistent, no backup file.** Made no difference to
   bonding; revert by restoring the comment unless it proves useful for other devices.
5. `/etc/systemd/system/bluetooth.service.d/pistomp.conf` — the drop-in from
   "What pi-gen-pistomp must provide". **Persistent.** This one we want to keep; it is
   the thing being proposed for the image.
6. Adapter set `Pairable: yes` (persists in `/var/lib/bluetooth/<adapter>/settings`).
   The UI should set this explicitly over D-Bus rather than relying on it.
7. The EV-1-WL pairing was removed at the end of testing — no device entry remains.

**On hardware** (Pi 5 with `feat/bluetooth` flashed or `Experimental = true` set):

1. `grep -c '^Experimental' /etc/bluetooth/main.conf` → 1, `systemctl is-active bluetooth`
2. Menu → Network → Bluetooth. Turn on. Nearby devices → the EV-1-WL appears with an
   `M` badge and RSSI bars, and **only** MIDI/HID devices are listed.
3. Tap it → `Pairing…` → `Connecting…` → ✔. Confirm `aconnect -l` shows a new ALSA seq
   client named for the device, that it appears as a JACK MIDI port, and that mod-ui
   offers it for MIDI-learn.
4. Power-cycle the pedal → it reconnects unprompted. **Run this early** — see "Open
   risk: pairing without bonding". If it fails, paired rows need an explicit
   "Reconnect" action.
5. Long-press → Forget → it leaves the paired list and stops auto-connecting.
6. Reboot → still paired, still auto-connects, `bluetooth.service` still enabled.
7. Pair a presenter → `/dev/input/eventN` appears; its arrow keys scan the NAV
   reticule and its click activates; a mapped key emits its CC and is MIDI-learnable in
   mod-ui.
8. Regression: on a Pi 3/4 image, the Network menu shows **no** Bluetooth row.
```
