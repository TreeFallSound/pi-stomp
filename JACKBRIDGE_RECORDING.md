# pi-stomp ↔ JackBridge: recording-mode integration

This document specifies the pi-stomp UI and backend changes needed to integrate with **JackBridge** — a sibling project that turns a Mac into a DAW-side endpoint for the pi-stomp's audio. The actual JackBridge code lives outside this repo; you don't need to look at it. This doc gives you everything you need to do the pi-stomp side.

## What we're building, and why

Today, pi-stomp is a performance pedal: guitar in → mod-host runs LV2 effects → wet out to the headphone / line jack. The PREEMPT_RT kernel, ALSA + JACK stack, hardware footswitches and LCD UI are all tuned for live use.

We want to add a **second use case: recording**. The same device, on the same stage, after the show — plugged into a Mac via Ethernet, presenting itself as a 4-input / 2-output audio interface to Logic / Pro Tools / REAPER. The Mac side is a CoreAudio HAL plugin called JackBridge that we wrote separately. The protocol on the wire between them is **netJACK2** (specifically, `netadapter` running as an internal JACK client on the pi, talking unicast UDP to a `netmanager` instance on the Mac).

The four inputs the DAW sees:

| Channel | Source |
|---|---|
| In1, In2 | Raw hardware capture (the pi-stomp's iqaudio codec capture — the guitar signal pre-pedalboard) |
| ModOut1, ModOut2 | Post-mod-host output (the wet pedalboard signal — same audio you currently hear on the headphone jack) |

The two outputs are stereo monitor return from the DAW, summed into the pi's existing `system:playback_*` graph alongside mod-host's normal wet output. The user picks per-track whether they want dry, wet, or both; reamp workflows record dry and reprocess later.

**Key constraint: pi-stomp must keep working as a performance pedal even when JackBridge is "installed."** The stock `jack.service` + `mod-host` + `mod-ui` keep running. The recording integration is a *second* client of the same `jackd`, loaded on demand. When the user is on stage, recording mode is off (no netadapter, no CPU spent encoding UDP packets). When they want to record, they enable it from the LCD.

The CPU cost of netadapter (encoding 4×48k float → UDP, decoding 2×48k from UDP) is real and we don't want it running during a performance. Hence: **enable/disable from the LCD**.

## Two integration surfaces

There are two pieces of code that need to land in this repo:

1. **A new systemd service unit (and its install path) for the netadapter loader.** The actual unit file is owned by the JackBridge repo and gets installed onto the system image by `pistomp-arch`. You don't write the unit. But the pi-stomp UI needs to know its name (`pi-stomp-jackbridge.service`) so it can `systemctl start` / `systemctl stop` it.
2. **A new LCD menu surface, extending the existing WiFi menu pattern.**

Detail on #2 follows.

## The "Network" menu (extending WiFi)

Today the LCD has a **WiFi menu** at `ui/wifi_menu.py`. It scans nearby APs, shows saved networks with a check-mark for the active one, and lets the user connect / forget. It's the richest existing pattern for live status + actions and is the model to follow.

We are **extending** that menu to be a general-purpose network menu, not duplicating it.

### Top-of-menu insertion

When the user opens the WiFi menu and `/sys/class/net/end0/carrier == 1` (an Ethernet cable is physically plugged in), prepend one row at the top of the menu list:

```
[ethernet-cable glyph]  Wired Connection
[wifi-bars glyph]       MyHomeNetwork  ✔
[wifi-bars glyph]       NeighborWifi
[wifi-bars glyph]       CoffeeShop
...
```

The glyph is a new addition to `FontWithGlyphs` — implement `EthernetCableGlyph` parallel to the existing `PillGlyph` and `SignalBarsGlyph` in `uilib/font_with_glyphs.py`. Style: simple monochromatic RJ45 plug or a cable-with-tab silhouette. Reserve a sentinel codepoint in the PUA range (e.g. `\ue020`).

If `end0/carrier == 0` (no cable), the row is omitted entirely.

The row's label always reads "Wired Connection" — we don't try to show link state or activity in the row itself. State lives in the sub-screen.

### The "Wired Connection" sub-screen

Clicking the row pushes a new panel (mirror the way `_render_nearby_menu` pushes `Menu` instances onto `pstack`). The sub-screen is a `EthernetMenu` class living at `ui/ethernet_menu.py`.

Contents when the JackBridge service is **enabled** and running:

```
Ethernet Audio Interface
─────────────────────────
IP:           169.254.125.193/16
Sample Rate:  48000 Hz
Period:       128 frames
xruns 1m:     0
xruns 5m:     3
xruns 15m:    12

[Disable Ethernet Audio]
```

Contents when the JackBridge service is **disabled**:

```
Ethernet Audio Interface
─────────────────────────
IP:           169.254.125.193/16

[Enable Ethernet Audio]
```

Contents when the cable is unplugged *while* the sub-screen is open (or if the user enters the screen via a stale menu after unplugging): show a `MessageDialog` saying "Ethernet cable disconnected." with an OK that pops back to the WiFi menu. Use the same `MessageDialog` pattern `wifi_menu.py` uses for error reporting.

### Where each value comes from

- **IP**: parse `ip -4 -o addr show end0` for the `inet <addr>/<prefix>` field. The address is most commonly a `169.254.0.0/16` link-local (direct cable to Mac with no DHCP server), but it could be a normal LAN address if both pi and Mac are on a router. Show whatever's there. If no IPv4 is assigned, show "—".
- **Sample Rate** / **Period**: query the *running* jackd via `jack_bufsize` / `jack_samplerate` CLI tools, or via the existing pi-stomp jack-client connection. These are *jackd's* values, not netadapter-specific — the netadapter inherits them from the master jackd.
- **xrun stats (1m / 5m / 15m)**: read `/tmp/pi-stomp-jackbridge.xruns`, a plain-text file with one Unix-epoch timestamp per line (one per xrun event). Bucket by `time.time() - ts < 60 / 300 / 900`. **The service owns the file's size**: it truncates to empty on service start, and on each append it filters out entries older than 15 minutes and atomically rewrites the file (write to `.tmp`, `rename(2)` over the real path — so the UI never reads a torn file). The file is bounded to a few hundred lines worst case. The UI reads the whole file each poll — no tailing, no offset tracking. If the file is missing, show all three buckets as `—`.
- **Toggle action**: `subprocess.run(["sudo", "systemctl", "start", "pi-stomp-jackbridge.service"])` or `stop`. Use the same fire-and-forget pattern as `modalapi/mod.py:1041` (the existing `systemctl restart jack` call). Show a `MessageDialog` only on non-zero exit.
- **Service status (enabled vs disabled)**: `subprocess.call(["systemctl", "is-active", "--quiet", "pi-stomp-jackbridge.service"])` — exit code 0 = running, non-zero = stopped. Same pattern as the existing `usbmount@dev-sda1` check at `modalapi/mod.py:1058`.

### Live refresh

When the sub-screen is open and the service is running, we want the xrun counters to update without the user having to leave and re-enter. Use the same polling pattern as `WifiManager` (`modalapi/wifi/manager.py:64-69`): a thread that re-reads the xrun file and invokes a callback that triggers a panel redraw, on a 2-second cadence. Stop the thread when the panel is popped.

When the service is *stopped*, no polling needed — the screen is static (just IP).

### Cable-presence polling

Mirror the `WifiManager._is_wifi_connected()` pattern: a small `EthernetManager` (new file at `modalapi/ethernet/manager.py`) with a background thread that polls `/sys/class/net/end0/carrier` every 2 seconds and fires a callback on transition. The callback rebuilds the WiFi menu's row list so "Wired Connection" appears / disappears live. If the user is *inside* the Wired Connection sub-screen when carrier drops to 0, the manager triggers a transition that pops the sub-screen and shows the "cable disconnected" `MessageDialog`.

## What you do NOT need to do

- **You don't write the systemd unit file.** That lives in the JackBridge repo and gets installed by `pistomp-arch` onto the system image. You just call `systemctl start|stop pi-stomp-jackbridge.service` by name and trust it exists.
- **You don't configure netadapter.** The service handles `jack_load netadapter` with the right `-C 4 -P 2`, master IP, and the wiring of `system:capture_* → netadapter:playback_1/2`, `mod-host:output_* → netadapter:playback_3/4`, `netadapter:capture_* → system:playback_*`. From the UI's perspective the service is a black box: start/stop, plus the xrun-file side effect.
- **You don't talk to the Mac.** Zero-config from the pi side. netJACK2's multicast discovery handles Mac-side rendezvous (the Mac listens on the multicast group; the pi unicasts to whatever address the user has wired). The Mac is responsible for finding us, not vice versa.
- **You don't add a "performance vs recording mode" global switch.** Recording mode is purely additive — `jack.service` and mod-host keep running, the user can perform with the pedalboard *and* simultaneously record on the Mac if they want. The only switch is "is the netadapter client loaded?".

## File map summary

New files:

```
ui/ethernet_menu.py             # EthernetMenu class, mirrors wifi_menu.py
modalapi/ethernet/__init__.py
modalapi/ethernet/manager.py    # EthernetManager — carrier polling + xrun file reader
```

Modified files:

```
ui/wifi_menu.py                 # prepend "Wired Connection" row when carrier=1
uilib/font_with_glyphs.py       # add EthernetCableGlyph + sentinel codepoint
pistomp/lcd320x240.py           # instantiate EthernetManager alongside WifiManager
```

## Open questions to flag back, not decide on your own

If any of the following turn out to be wrong / unclear when you go to implement, surface them rather than guessing:

- The xrun-file contract (one Unix-epoch timestamp per line, service-side truncates entries older than 15 min on every append, fresh on service start) is agreed between this UI and the service. If you'd prefer a different format (e.g. a running JSON snapshot with pre-bucketed counts so the UI does no math), flag it and we'll adjust the service side.
- I'm assuming `end0` is the correct interface name on every pi-stomp board. If there are board variants where it's different, the interface name should be a config constant, not hardcoded.
- The "live refresh every 2s while sub-screen open" cadence is a guess. If the existing menu redraw cost makes that too jumpy, drop to 5s.
