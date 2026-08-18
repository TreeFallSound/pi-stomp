# Session Recording Plan (pi-Stomp side)

Trigger and reflect session recording from the pedal itself. mod-ui owns the
actual recording (jack_capture → WAV in `/home/pistomp/data/user-files/Audio
Recordings/`, mod-ui's existing user-files category, so recordings show up in
MOD-UI's file dialogs and file-player plugins like NAM captures do);
pi-Stomp is one of three control surfaces (browser, Pistomp-Mobile, pedal),
all converging on mod-ui's REST endpoints on port 80.

Counterpart plan: `mod-ui/docs/session-recording.md` (recorder, REST, WS
protocol changes).

## Why WebSocket sync is required

Yes — REST alone can't keep three surfaces coherent. A REST response only
informs the *initiator*; if recording is started from the phone, the pedal's
REC indicator must light anyway, and a stale local flag would make our
"toggle" callback send a spurious `/recording/start`. This is exactly the
bypass-state problem we already solved: **emit optimistically, reconcile
against mod-ui's broadcast**. mod-ui will broadcast:

```
recording start <filename>
recording stop <filename> <duration_seconds>
```

and replay current state to each newly opened WebSocket, which covers the
pi-Stomp-restart and WS-reconnect cases (our bridge reconnects with backoff;
without connect-time replay we'd wake up blind).

## Changes

### 1. Protocol (`modalapi/ws_protocol.py`)

New frozen dataclass:

```python
@dataclass(frozen=True)
class RecordingStateMessage:
    recording: bool
    filename: str
    duration: float | None   # only on stop
```

Parse `["recording", "start", fname]` and `["recording", "stop", fname, dur]`
in `parse_message()`. Filenames are space-free by construction (timestamp+slug).

### 2. Handler (`modalapi/modhandler.py`)

- State: `self._recording: bool = False`, `self._recording_started_at: float | None`.
- `_handle_ws_message()`: new `RecordingStateMessage` branch — set state,
  stamp start time (for elapsed display), call `self.lcd.update_recording(...)`.
  This is the single reconciliation point for all surfaces.
- `toggle_recording(*argv)`:
  - If not recording: optimistic `self._recording = True`, indicator on, then
    `_rest_get(root_uri + "recording/start")`. On failure (`None` response or
    `ok: false` — e.g. disk guard), revert and show
    `lcd.draw_message_dialog(...)` with the error.
  - Else: `recording/stop`, optimistic indicator off.
  - The WS echo overwrites, never compounds — same contract as footswitch
    bypass.
- Register in `self.callbacks`:
  ```python
  "toggle_recording": self.toggle_recording,
  ```
  That one line makes it available to **both** encoder longpress and
  footswitch longpress groups — `chord_helper.rebuild(self.handler.callbacks)`
  (`pistomp/hardware.py:141`) and the encoder longpress path
  (`modhandler.py:307`) both resolve names from this dict. Per-pedalboard (or
  default) config opts in:
  ```yaml
  footswitches:
    - id: 2
      longpress_groups: [toggle_recording]
  ```
  A two-switch chord (both members list the group) works with zero extra code,
  mirroring `toggle_tuner_enable`.
- On startup / after WS reconnect, `GET /recording/status` once to seed state
  (belt-and-suspenders alongside mod-ui's connect-time replay).

### 3. Visual feedback (`pistomp/lcd320x240.py`)

- **Toolbar REC indicator**, positioned like the wifi widget (`w_wifi`) in
  `draw_tools()`, but painted analytically — no PNG assets. A small widget
  whose `_draw` blits `CircleGlyph` (`uilib/glyphs/circle.py`) tinted red via
  `tint_mask`, exactly as the footswitch LED dot does
  (`uilib/footswitch.py:194`); idle state is a dim `RingGlyph` outline (or
  nothing). Blink while recording by toggling the tint from
  `update_recording()` — the handler already ticks indicators every 20 ms
  (`poll_indicators`); pace at ~1 Hz from `time.monotonic()` like the wifi
  spinner. Note `draw_title`'s shrinking label already stops short of the
  toolbar (`MAX_X1 = 200`), so a new icon slots into the existing icon row.
- Tapping the indicator (it's a `sel_widget`, like wifi) opens a small dialog:
  elapsed time + "Stop recording" / "Start recording".
- **Lifecycle**: toolbar widgets are recreated whenever `draw_main_panel()`
  runs (pedalboard load). Like `update_wifi`'s `w_wifi is None` guard, the
  handler must re-apply `self._recording` to the fresh widget after a reload —
  recording deliberately continues across pedalboard switches.
- **Footswitch LED**: skip in v1. LEDs are pedalboard-bound state; overloading
  one as a REC lamp needs an ownership story (what happens on pedalboard
  reload?). The LCD indicator is the source of truth; revisit if playing-
  position feedback demands it.
- v1 (`lcdgfx`/`mod.py`): out of scope, consistent with tuner and other
  Modhandler-only features.

### 4. System menu — Recordings (`pistomp/lcd320x240.py`, `modhandler.py`)

Add to `draw_system_menu()`:

```
("Recordings >", self.draw_recordings_menu, None)
```

with items:

- **Start/Stop recording** — same `toggle_recording` path (label reflects
  current state).
- **Copy recordings to USB** — see §5.
- **Clear recordings...** — see §5.

### 5. USB offload: copy-to-USB and clear

Recordings accumulate at ~1 GB/hour; the pedal is often headless, so the
stick is the primary way audio leaves the device.

**Reuse the existing USB plumbing** (`modhandler.py:1152-1202`):
`_usb_media_mounts()` (pi-gen's `pistomp-usb-mount` udev script populates
`/media`), `_choose_usb_drive()` for multi-stick selection, `_drive_label()`.
Target directory: `<mount>/recordings/` (sibling of the existing
`backups/`).

**Copy flow** (`copy_recordings_to_usb`):

1. Enumerate `/home/pistomp/data/user-files/Audio Recordings/*.wav`,
   **excluding the
   in-progress file** when `self._recording` (its name is known from the WS
   message).
2. Pre-flight: total size vs `shutil.disk_usage(mount).free`; refuse with a
   clear dialog if it doesn't fit ("Need 3.2GB, stick has 1.1GB free").
3. Copy via a new `util/recordings-copy.sh` (rsync-style: skip files already
   present with matching size).
4. **Run it off the UI thread.** Unlike the backup zip (small config files),
   copying gigabytes to a USB2 stick takes minutes. Follow the established
   worker-thread + poll-drain pattern used by the wifi manager — the existing
   synchronous `subprocess.check_output` style of `_do_backup_data` would
   freeze the 10 ms loop and drop MIDI. Show "Copying… (n/total)" via
   `draw_info_message`, completion dialog at the end.

**Clear flow — the paranoid part.** Deletion is only ever *verify-then-delete,
per file*:

- For each local WAV, delete **only if** a file of the same name **and same
  byte size** exists in the stick's `recordings/` dir. (Size match on a
  just-written WAV is a reasonable integrity proxy; upgrade to sampled
  checksum if we ever see corruption.) No blanket `rm -rf`, no "clear"
  decoupled from evidence of a copy.
- Files that fail verification are skipped and reported: "Cleared 12,
  kept 2 not found on USB".
- Never delete the in-progress recording.
- Confirmation dialog before anything is removed, stating exactly what will
  happen: "Delete 14 recordings (3.2GB) verified on USB 'SANDISK'? Files not
  on the stick are kept."
- Menu shape: **"Copy & clear"** as the primary flow (copy, verify, then the
  confirm-delete step), plus a standalone **"Clear recordings..."** that runs
  the same verify-against-USB logic — meaning it requires a mounted stick
  holding the copies. There is deliberately *no* way to bulk-delete
  recordings that exist nowhere else; the escape hatch for a truly full disk
  is per-file delete via mod-ui's `/recording/delete/<name>` (or ssh).

**Backup interaction** (`util/data-backup.sh`): add
`-x "user-files/Audio Recordings/*"`
alongside the existing `-x ".lv2/*"` zip exclusion. Otherwise the first
hour-long session makes `pistomp_backup.zip` multi-GB and the restore path
untestable. Recordings move via the dedicated copy flow, not the backup zip.

## Sequencing

1. mod-ui side lands first (endpoints + WS messages are the contract).
2. pi-stomp: ws_protocol parsing + handler state + toolbar indicator.
3. Callback registration + config docs (`toggle_recording`).
4. Recordings menu + USB copy/clear + backup exclusion.

Each step is independently shippable; 2–4 degrade gracefully against an old
mod-ui (REST 404 → dialog, no WS messages → indicator simply never lights).

## Notes

- **Restore is recording-safe**: `util/data-restore.sh` uses `unzip -o -u`
  (overlay, no deletion), so restoring a backup never destroys recordings.
  Only the copy-verified clear flow deletes them.
- **Recording spans disruptive actions**: a pedalboard switch mutes processing
  briefly (`feature_enable processing 0`), leaving a short silence in the
  file — expected. "Restart sound engine" (jack restart) kills jack_capture;
  mod-ui's crash-watch broadcasts the stop and the indicator clears.
- **Emulator**: MOD Desktop on macOS doesn't run our mod-ui fork or
  jack_capture, so recording isn't testable end-to-end in the emulator — only
  the REST-failure path exercises there (which is itself worth a manual
  check).

## Test plan

- `ws_protocol` unit tests for both `recording` message forms + malformed.
- v3 snapshot tests: indicator off→on→off via injected WS messages; menu
  navigation to Recordings; copy-flow dialogs with a fake `/media` mount
  (tmpdir + monkeypatched `_usb_media_mounts`).
- Clear-flow unit tests: size-mismatch file survives, in-progress file
  survives, verified files deleted, empty-stick refusal.
- On-device: chord-start from footswitches while MOD-UI browser page is open —
  both indicators light; stop from the browser — pedal indicator clears.
