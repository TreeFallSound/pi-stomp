# Input-Routing Unification (Path B): retire the fullscreen concept

**Status:** planned — characterization landed, refactor not yet executed.
**Scope:** v2/v3 only (`modhandler.py` + `lcd320x240.py`). v1 (`mod.py` / `lcdgfx`) untouched.
**Goal:** any panel or dialog on the stack — not just a "fullscreen" one — can receive
the full typed encoder stream (with encoder identity), so the multi-encoder
UX stops being a special case. Once routing goes to the top of the stack, the
parallel `_fullscreen_panel` bookkeeping is redundant and is deleted.

The concrete motivating feature is a wide **audio-menu graphic-EQ dialog** (5-band
DAC EQ + In/Out arcs). That is a follow-on; this plan is the enabling refactor.

---

## 1. Why

Today there are **two** input models, and which one a panel gets is decided solely
by `if self._fullscreen_panel is not None`:

- **Fullscreen panels are `InputSink`s.** They receive the *raw typed event* with
  encoder identity. `plugins/base.py:176` reads `cid = event.controller.id` and
  dispatches `on_encoder_rotation(cid, rotations)`. This — and only this — is why
  4 encoders can be live at once.
- **Every other stacked panel/dialog** is reached only via the **nav** encoder →
  `enc_step` → `pstack.input_event(InputEvent.RIGHT/LEFT/CLICK)`. Identity is
  flattened to a direction; tweak encoders 1–3 never arrive.

Fullscreen-ness has nothing to do with it. The fullscreen panel is just the one
thing wired to receive events *as an InputSink* instead of as degraded nav-steps.
Fix that and the distinction dissolves.

**Three reasons this refactor is worth doing now:**

1. **Multi-encoder UX for any panel.** A wide audio-menu GEQ dialog (§8) wants
   tweak encoders routed to it. Without this refactor, only "fullscreen" panels
   get that. With it, any panel can opt in.
2. **Dialog-over-panel semantics fix.** A parameter dialog pushed over a
   fullscreen panel (e.g. over the NAM panel) should receive input. Today, the
   buried fullscreen panel gets the input instead — a latent bug.
3. **Remove dual-source-of-truth.** `_fullscreen_panel` is mirrored in *both*
   `lcd320x240.py:217` and `modhandler.py:166`; the two copies must be
   hand-kept in sync. The new model has one source of truth: `pstack`.

---

## 2. Current architecture (anchors)

Dispatch cascade (`Modhandler.handle`, `modhandler.py:250`):

```
handler.handle(EncoderEvent)                       # modhandler.py:250
  └─ lcd.handle(event)                             # lcd320x240.py:296
       └─ if self._fullscreen_panel: fs.handle(event)   # ONLY the fullscreen panel
            └─ plugins/base.py:176  cid in (1,2,3) → on_encoder_rotation(cid, …)
  └─ active_blend_mode.intercept(event)            # modhandler.py:256
  └─ _handle_encoder(event)                        # modhandler.py:267  (fall-through)
        NAV    → universal_encoder_select → lcd.enc_step → pstack.input_event(RIGHT/LEFT)
        VOLUME → audiocard.set_volume_parameter(MASTER) + volume dialog
        KNOB   → (if bound) display+commit; then _emit_midi(new_midi_value)
```

**Two input paths, two semantics** — this asymmetry is load-bearing and survives
the refactor:

- **Tweak path (ControllerEvent)**: propagation, top-down through the stack.
  Top *input-accepting* panel (`pstack.current`) gets first crack; if it returns
  `False`, the event reaches the handler cascade. This is how `tweak3` falls
  through the EQ panel to the volume handler (`graphic.py:395`).
- **Navigation path (InputEvent)**: single-target dispatch. `pstack.input_event`
  (panel.py:482) calls `pstack.current.input_event(event)` exactly once. A
  dialog that doesn't handle the click does not pass it to the panel
  underneath — that would be wrong (the user clicked the dialog, not the
  panel below). `accepts_input=False` opts a panel out of being a navigation
  target.

`pstack.current` is the topmost panel with `accepts_input=True` — a *visual*
panel like the footswitch `ShroudedPanel` (lcd320x240.py:214) sits on top of
the main panel but does not become `current` because it has
`accepts_input=False`. The plan refers to "the top of the stack" but means
this — be precise.

### Encoder id ↔ type mapping (v3 default config)

| Enc    | `id`   | `type`         | Routing today |
|--------|--------|----------------|---------------|
| Nav    | `None` | `NAV`          | NAV branch → `enc_step` → `pstack.input_event` |
| Tweak1 | `1`    | `KNOB`, CC 70  | fullscreen: `on_encoder_rotation(1)`; else `_emit_midi` |
| Tweak2 | `2`    | `KNOB`, CC 71  | same, CC 71 |
| Tweak3 | `3`    | `VOLUME`       | fullscreen: `on_encoder_rotation(3)`; else audiocard `MASTER` |

(Nav encoder built directly with `type=NAV`, no `id` — `pistomptre.py:112`. Tweaks
from config via `create_encoders`, `hardware.py:313`. MIDI channel is the global
`get_real_midi_channel`, **not** 0 — characterization pins it from the encoder.)

### The fullscreen concept to be retired

- **Class**: `pistomp/fullscreen_panel.py` — `FullscreenPanel(Panel, InputSink)`
  with `tick()` abstract, `handle()` default `False`,
  `should_persist_on_board_change()` default `False`.
- **Field**: `lcd320x240.py:217` and `modhandler.py:166` — two mirrors of
  `self._fullscreen_panel: Panel | None`.
- **Methods**:
  - `lcd.show_fullscreen_panel` / `hide_fullscreen_panel` /
    `has_active_fullscreen_panel` / `plugin_panel` (lcd320x240.py:412-427)
  - `modhandler.show_fullscreen_panel` / `hide_fullscreen_panel`
    (modhandler.py:1417-1436) — the public factory helper + the
    "already open" gate
  - `modhandler._tuner_panel` / `_tuner_engine` (modhandler.py:1364-1371)
- **Callers of the field**:
  - Routing: `lcd.handle` (lcd320x240.py:299) and `lcd._poll_updates`
    tick (lcd320x240.py:319)
  - Divisor hint: `modhandler.lcd_poll_divisor` (modhandler.py:443-444)
  - Persist-on-board-change: `modhandler.set_current_pedalboard`
    (modhandler.py:788-790)
  - Tile refresh: `lcd320x240.py:684-685` (uses `lcd.plugin_panel`)
- **Three direct writers** of `self._fullscreen_panel` (modhandler.py):
  - `toggle_tuner_enable` (line 1388) — tuner
  - `show_fullscreen_panel` factory (line 1426) — plugin panel
  - `_mount_nam_capture_panel` (line 1448) — NAM capture
- **The plugin factory's "already open" gate** (line 1419): `if
  self._fullscreen_panel is not None: return`. Becomes
  `if self.pstack.find_panel_type(PluginPanel) is not None: return`.

---

## 3. Ratified decisions

1. **Route to top input-accepting panel.** Any panel that opts in to
   `InputSink` (i.e. is `pstack.current`) gets first crack at tweak encoder
   events. This is not just preservation — it *fixes* a latent bug: a
   parameter dialog pushed over a fullscreen panel should receive input and,
   on dismiss, pop back to reveal the panel.
2. **NAV stays on the legacy `enc_step`/`enc_sw` path.** The tweak path
   (`InputSink.handle`) is the new mechanism; NAV continues to flow through
   `_handle_encoder` NAV branch → `universal_encoder_select` → `lcd.enc_step`
   → `pstack.input_event(InputEvent.X)`. NAV has no fall-through, so
   propagating it through `Panel.handle` gains nothing; the dual-path
   design is asymmetric on purpose. See §2 "Two input paths, two semantics."
3. **Full retirement, no shims.** The `FullscreenPanel` *class* dies, the
   `_fullscreen_panel` *fields* die, the `show/hide/has_active_fullscreen_panel`
   *methods* die. The plugin factory helper stays (it encapsulates panel
   construction + dismiss wiring) but its internals are just
   `pstack.push_panel`.
4. **`pstack` is the single source of truth.** No parallel mirror, no
   computed-property shim. Every "is panel X loaded?" query is a
   `pstack.find_panel_type(X)` or `pstack.current` check.
5. **`should_persist_on_board_change` moves to `Panel`.** Default `False`.
   `TunerPanel` overrides to `True`. The persist test covers both directions.
6. **Two lookup patterns, by design.** `pstack.current` for "what's the user
   looking at / interacting with" (input routing, divisor hint). `pstack.find_panel_type(X)`
   for "is X loaded anywhere in the stack" (tuner mute, plugin tile refresh,
   plugin factory's "already open" gate).

---

## 4. Coverage map & characterization (landed)

New file `tests/v3/test_encoder_dispatch.py` pins the fall-through through the real
`Modhandler.handle` with real encoders (correct id/type/CC):

- `test_v3_encoder_id_type_mapping` — the mapping in §2 is the premise.
- `test_main_panel_tweak1_emits_cc70` / `_tweak2_emits_cc71` — gap 1.
- `test_main_panel_volume_encoder_sets_audiocard_master` — gap 2 (and asserts
  volume never emits MIDI).
- `test_lcd_handle_falls_through_without_fullscreen_panel` — the seam for the
  main-panel case (complements `test_graphic_eq_panel.py:251`, the fullscreen case).

Pre-existing coverage relied on: `test_graphic_eq_panel.py:251` (per-encoder
consume/release seam), `test_plugin_panels.py` (`on_encoder_rotation` dispatch),
panel editing tests (gx_cabinet/eq/nam/notes/tap_reverb/acomp), nav via
`enc_step`/`universal_encoder_select` (`test_selection_tree`, `test_menu_scrolling`).

**Tests to add during the refactor:**

- `should_persist_on_board_change` lifecycle: open tuner, push a non-persisting
  panel over it, change pedalboard, assert the panel is popped and the tuner
  is still on the stack. Also assert a plugin panel is popped on board change
  (non-persister).
- Dialog-over-panel pop-back: push a parameter dialog over a plugin panel,
  send a tweak event, assert the dialog receives it (not the buried panel);
  dismiss the dialog, assert the plugin panel reactivated.
- `wants_fast_tick` divisor: top `wants_fast_tick=True` → divisor=2; top
  `wants_fast_tick=False` (or `None`) → divisor=8.
- `find_panel_type(PluginPanel)` tile refresh: plugin changes bypass state,
  assert the plugin panel is found and refreshed even if a dialog is on top.

**Test files that read `handler._fullscreen_panel` directly** and need updates
in the single landing:

- `tests/v3/test_plugin_panel_bypass_refresh.py:75,92`
- `tests/v3/test_nam_panel.py:282,288-289`
- `tests/v3/test_encoder_dispatch.py:38`
- `tests/test_handler_cleanup.py:26`

---

## 5. Target design

### 5.1 Route to top input-accepting panel

`Lcd.handle` (lcd320x240.py:296) stops consulting `_fullscreen_panel`:

```python
def handle(self, event: ControllerEvent) -> bool:
    top = self.pstack.current  # top input-accepting panel
    return top.handle(event) if isinstance(top, InputSink) else False
```

- Existing fullscreen panels are already `InputSink`s and are `pstack.current` when
  shown → behavior identical for them.
- Existing non-`InputSink` dialogs (message/confirm/parameter) are not
  `InputSink` → still fall through, identical to today.
- Only panels that *opt in* to `InputSink` change behavior — exactly what we want.

### 5.2 Tweak-only `Panel.handle` (NAV stays on legacy path)

The new `Panel.handle` is **tweak-only**. NAV routing is unchanged.

```python
# v2/v3 Panel base (uilib/panel.py)
class Panel(ContainerWidget):
    def handle(self, event: ControllerEvent) -> bool:
        match event:
            case EncoderEvent() if event.controller.id in (1, 2, 3):
                return self.on_encoder_rotation(event.controller.id, event.rotations)
        return False

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        return False  # default: release (let handler cascade pick it up)
```

- `plugins/base.py:176` (PluginPanel.handle) becomes redundant — it inherits
  Panel's default and only overrides `on_encoder_rotation`. Delete it.
- `FullscreenPanel.handle` (fullscreen_panel.py:43) is also redundant — but
  `FullscreenPanel` is being deleted entirely (decision #3).
- `TunerPanel` and `NamCapturePanel` (which today have no custom `handle`) keep
  the default — they don't consume tweak events.

The dynamic per-encoder fall-through (`graphic.py:395` releases tweak3) is
preserved verbatim: `on_encoder_rotation` returns `False` for released encoders
and the handler cascade picks up.

### 5.3 Retire the fullscreen concept

`FullscreenPanel` class: **deleted**. The `Panel` base gets the methods that
were on `FullscreenPanel`:

```python
class Panel(ContainerWidget):
    def handle(self, event) -> bool: ...                       # §5.2
    def on_encoder_rotation(self, eid, rot) -> bool: return False
    def wants_fast_tick(self) -> bool: return False            # override in real-time panels
    def should_persist_on_board_change(self) -> bool: return False
```

Overrides:

| Panel | `wants_fast_tick` | `should_persist_on_board_change` |
|-------|-------------------|----------------------------------|
| `TunerPanel` | `True` | `True` |
| `PluginPanel` (base) | `True` | `False` |
| `NamCapturePanel` | `True` | `False` |
| (future audio-menu dialog, §8) | `True` | `False` |
| everything else | inherit `False` | inherit `False` |

`FullscreenPanel` subclasses become plain `Panel` subclasses (or `PluginPanel`
where applicable). The 320×240 box, `auto_destroy=True`, `no_dim=True` defaults
move to the call sites that need them.

### 5.4 Retire the `_fullscreen_panel` mirrors and helper methods

| Old | New |
|-----|-----|
| `lcd._fullscreen_panel` + routing (`lcd.handle`) | `pstack.current` (top input-accepting) |
| `lcd._fullscreen_panel` + tick (`lcd._poll_updates`) | `pstack.current.tick()` if it has one |
| `lcd.has_active_fullscreen_panel()` → `lcd_poll_divisor` | `pstack.current.wants_fast_tick()` if current else `False` |
| `lcd.plugin_panel` property | `pstack.find_panel_type(PluginPanel)` |
| `lcd.show_fullscreen_panel(panel)` | `pstack.push_panel(panel)` |
| `lcd.hide_fullscreen_panel()` | `pstack.pop_panel(panel)` |
| `modhandler._fullscreen_panel` field | (gone) |
| `modhandler.show_fullscreen_panel(plugin, cls)` factory | stays; internals are `pstack.push_panel` + `find_panel_type(PluginPanel)` "already open" gate |
| `modhandler.hide_fullscreen_panel()` | stays; pop and refresh |
| `modhandler._tuner_panel` | `pstack.find_panel_type(TunerPanel)` |
| `modhandler._tuner_engine` | (via `pstack.find_panel_type(TunerPanel)._engine`) |
| `should_persist_on_board_change` (FullscreenPanel) | on `Panel` (§5.3) |
| The "already open" gate in the plugin factory | `if pstack.find_panel_type(PluginPanel) is not None: return` |

### 5.5 The three direct `_fullscreen_panel` writers

All three converge on the same pattern: instantiate, push, query by name.

| Writer | Today | New |
|--------|-------|-----|
| Tuner mount (modhandler.py:1388) | `self._fullscreen_panel = panel; self.lcd.show_fullscreen_panel(panel)` | `self.pstack.push_panel(panel)` |
| Plugin factory (modhandler.py:1426) | same | same; "already open" gate uses `find_panel_type(PluginPanel)` |
| NAM mount (modhandler.py:1448) | same | `self.pstack.push_panel(panel)` |

Lookups that need the *current* input-accepting panel (input routing, divisor
hint) use `pstack.current`. Lookups that need *is X loaded* (tuner mute, tile
refresh, plugin factory gate) use `pstack.find_panel_type(X)`.

### 5.6 Board-change stack-walk

`set_current_pedalboard` (modhandler.py:787) walks the stack from top, popping
non-persisters and stopping at the first persister:

```python
def set_current_pedalboard(self, pedalboard):
    # Pop non-persisting panels above the first persister.
    while self.pstack.current is not None:
        top = self.pstack.current
        if top.should_persist_on_board_change():
            break  # leave this and everything below
        self.pstack.pop_panel(top)
    ...
```

Auto-dismiss for parameter dialogs falls out of this: they're
`should_persist_on_board_change() == False` by default, so they get popped
on pedalboard change. The dialog was editing the old pedalboard's state; the
new pedalboard has different parameters, so the dialog disappears. No
special-case code needed.

### 5.7 `lcd_poll_divisor` rewrite

```python
@property
def lcd_poll_divisor(self) -> int:
    if self._lcd is None:
        return 8
    top = self._lcd.pstack.current
    if top is not None and top.wants_fast_tick():
        return 2
    return self._lcd.poll_divisor
```

### 5.8 Tile refresh

The plugin tile repaint callback (lcd320x240.py:684-685) uses `find_panel_type`
so the refresh reaches the plugin even if a dialog is stacked on top:

```python
panel = self.pstack.find_panel_type(PluginPanel)
if panel is not None:
    panel.refresh()
```

### 5.9 Cleanup ordering

`modhandler.cleanup` (modhandler.py:189) currently calls
`_lcd.hide_fullscreen_panel()` then `_lcd.cleanup()`. After retirement,
`lcd.cleanup` walks the pstack and destroys all panels. `modhandler.cleanup`
just calls `lcd.cleanup` (and the rest of its current logic — tuner mute
revert, external MIDI close, WS bridge stop, ethernet shutdown — unchanged).

---

## 6. Implementation phases

1. **[done] Characterization** — `tests/v3/test_encoder_dispatch.py`, all green.
2. **Single landing** — §5.1 through §5.9 in one PR. No shim, no intermediate
   state. The diff is large but mechanical:
   - `lcd.handle` and `lcd._poll_updates` switch to `pstack.current` (§5.1, 5.4).
   - `Panel` base gets `handle`, `wants_fast_tick`, `should_persist_on_board_change`
     (§5.2, 5.3).
   - `FullscreenPanel` class deleted; subclasses become plain `Panel`/`PluginPanel`.
   - `modhandler._fullscreen_panel`, `lcd._fullscreen_panel`, helper methods
     deleted (§5.4).
   - Three direct writers converge on `pstack.push_panel` (§5.5).
   - Board-change stack-walk (§5.6), divisor rewrite (§5.7), tile refresh (§5.8),
     cleanup ordering (§5.9).
   - New tests (§4) land with the change.
3. **Verify** — full `uv run pytest`; reconcile real failures first, then
   `--snapshot-update` for intended LCD drift; confirm v1 untouched.

The single-landing approach is deliberate. The dual-source-of-truth bug
surface the refactor eliminates cannot survive a phased rollout with shims;
the plan's earlier "thin shim if needed" hedge is dropped per decision #3.

---

## 7. Risks

- **Main-panel parity (highest).** Tweak→MIDI and volume→audiocard fall-through must
  stay bit-identical. Guarded by §4 characterization; do not let those tests change
  meaning.
- **NAV path regressions.** `enc_step`/`universal_encoder_select` feed selection;
  keeping NAV on the existing path (§5.2) minimizes this. Nav test suite is the
  canary.
- **Dialog-over-panel semantics.** Decision #1 intentionally changes behavior here;
  add a test asserting the dialog receives input and pops back to the panel.
- **v1 isolation.** `lcdgfx`/`mod.py` have no `pstack`; ensure the changes are
  confined to the v2/v3 classes and are a no-op for v1. `lcdgfx.show/hide_fullscreen_panel`
  stubs stay (they're part of the v1 surface).
- **Snapshot drift.** LCD snapshots commonly shift; treat per the snapshot-mismatch
  workflow (fix real failures, then `--snapshot-update`, pause for review).
- **`pstack.current` vs `pstack.find_panel_type` confusion.** A panel that wants
  input consumes the top; a panel that wants to know "is X loaded?" queries by
  name. The plan's decision #6 codifies the rule. Code review should look for
  `pstack.current is X` used as a state query (should be `find_panel_type`).
- **Test churn.** Four test files read `handler._fullscreen_panel` directly
  (§4). They must be updated in the same landing. Failure to do so silently
  re-introduces the mirror.

---

## 8. Follow-on: the audio-menu graphic-EQ dialog

Once any dialog can receive multi-encoder input, build the original feature as a
**wide `Dialog`** (not a fullscreen panel):

- Left column: In/Out arc rings (Input Gain, Output Volume).
- Right region: 5-band DAC-EQ vertical bars, reusing the `BarWidget` render core
  from `plugins/eq/graphic.py`.
- Bottom chrome: repurpose the plugin-panel "Bypass" slot as **Calibrate → VU
  calibration** (bypass already has its own toolbar icon; there is no plugin to
  bypass here).
- **Data-model split** (per project rules): parameter-bound widgets stay in
  `plugins/`; plugin-agnostic render widgets move to `uilib/`. `BarWidget` +
  `GraphicEqState`/`GraphicBandParams` are already plugin-agnostic and relocate to
  `uilib/`; `ArcRingGlyph` already lives in `uilib/glyphs/`. The dialog uses the
  `uilib` widgets + the audiocard commit path (`audiocard.set_volume_parameter` /
  the handler's `system_menu_eqN_gain`), not `plugin.set_param`.
- Gate the menu entry on `audiocard.DAC_EQ is not None` (IQaudIO Codec only).
