# Plugin Customization Guide

Architecture reference for `plugins/`. For step-by-step instructions on
adding a new plugin's UI, see `plugin-panel-tutorial.md`.

## Conceptual Dimensions

Every plugin customization is a point in a small space:

| Dimension | What it controls | Values |
|---|---|---|
| **Presentation** | Fullscreen vs compact card vs cosmetic-only | `FullscreenPluginPanel`, `PluginWindow`, or neither |
| **Visualization** | How the plugin's state is drawn | Curve (parametric EQ), bars (graphic EQ), arc column + GR graph (compressors), arc grid (multiband window), custom (Notes, NAM) |
| **Encoder routing** | Which tweak encoder does what | Per-panel-family convention, see below |
| **Tile chrome** | How the tile looks in the main grid | `tile_active_color`, `tile_border`, `display_name_fn`, `subtitle_fn` |
| **Extra data** | Per-instance state from `effect-N/` TTL | `extra_data_fn` → `PluginExtraData` subclass |

A plugin can combine a panel with custom tile chrome (most EQs/compressors),
or have only tile chrome with the real UI living elsewhere (NAM — panel opens
from the system menu, not a tile long-press).

---

## Registry & Dispatch

`plugins/customization.py` holds `dict[URI, PluginCustomization]`. Each
`plugins/{name}/__init__.py` registers at import time, and every module is
imported once from `plugins/__init__.py` to trigger registration — a plugin
missing from that import list is invisible to `lookup()`.

```python
register(
    "urn:distrho:a-comp",
    customization=PluginCustomization(panel_cls=AcompPanel, display_name="DISTRHO Compressor"),
)
```

The URI must match `manifest.ttl` and the pedalboard TTL's `lv2:prototype`
exactly — no normalization.

`lcd320x240.plugin_event()` on long-press:

1. `panel_cls` set → `handler.show_fullscreen_panel(plugin, panel_cls)`
2. Else → `draw_parameter_menu(plugin)` (generic parameter list)

`panel_cls` covers both fullscreen and windowed presentations — `PluginPanel`
subclasses share one constructor signature `(*, plugin, handler, on_dismiss)`,
so dispatch doesn't need to know which. `intercept_shortpress=True` (Notes)
also opens the panel on short-press instead of toggling bypass.

### `PluginCustomization` (`modalapi/plugin_customization.py`)

```python
@dataclass(frozen=True)
class PluginCustomization:
    panel_cls: type[PluginPanel] | None = None
    display_name: str | None = None
    display_name_fn: Callable[[Plugin], str | None] | None = None
    subtitle_fn: Callable[[Plugin], str | None] | None = None
    intercept_shortpress: bool = False
    tile_active_color: tuple[int, int, int] | None = None
    tile_border: RectBorder | None = None
    extra_data: PluginExtraData | None = None
```

---

## Panel Class Hierarchy

```
PluginPanel[TState]            plugins/base.py — geometry-agnostic core
├── FullscreenPluginPanel      plugins/fullscreen.py — whole 320×240 LCD
│   ├── ParametricEqPanel      plugins/eq/parametric.py
│   ├── GraphicEqPanel         plugins/eq/graphic.py
│   ├── CompressorPanel        plugins/compressor_base.py
│   └── NotesPanel, TapReverbPanel, Fil4Panel, ... (one-off panels)
└── PluginWindow                plugins/window.py — centered rounded card
    └── MultibandWindow         plugins/multiband_menu/__init__.py — arc-ring grid
```

`PluginPanel` owns the plugin/handler refs, param-send coalescing queue, and
Back/Bypass/Reset actions, but commits to no geometry. `FullscreenPluginPanel`
and `PluginWindow` each initialise a different `uilib` panel base
(`FullscreenPanel` vs `RoundedPanel`) and share the same bottom button row via
`plugins/chrome.py`'s `build_bottom_row()`.

### Subclass Contract

```python
class MyPanel(FullscreenPluginPanel[MyState]):  # or PluginWindow[MyState]

    def snapshot_state(self) -> MyState:
        """Read plugin.parameters into a typed state object."""

    def apply_state(self, state: MyState) -> None:
        """Push state back into the panel's widgets."""

    def build_widgets(self) -> None:
        """Create widgets; self.add_sel_widget(...) for Nav cycling.
        The base appends Back/Bypass/Reset chrome after this returns."""
```

- **Bypass**: toggles `plugin.set_bypass()`, sends WS, refreshes style.
- **Reset**: restores all non-bypass, non-locked symbols from
  `plugin.pedalboard_snapshot`.
- **Param-send coalescing**: `set_param(symbol, value)` queues a change;
  `tick()` drains it — rapid encoder spins collapse into one send per symbol.
  A subclass `tick()` override must call `super().tick()`.
- **InputSink**: `handle(event)` dispatches EncoderEvent (id 1/2/3) to
  `on_encoder_rotation(encoder_id, rotations) -> bool`.

### `PluginWindow` specifics

Compact card, `WIN_W`/`WIN_H`/`WIN_RADIUS` class attrs (default 304×208),
title band + same chrome row, `content_box` for subclass widgets. Registered
via `handler.show_fullscreen_panel` like a fullscreen panel — it participates
in the same fast-poll / board-change bookkeeping via `InputSink`.

### `MultibandWindow` — arc-ring grid (replaces the old menu-widget pattern)

For plugins with up to ~10 flat parameters. Subclass just implements
`build_slots()`; height grows with row count (1-4 slots → 1 row, 5-8 → 2 rows).

```python
class MyWindow(MultibandWindow):
    def build_slots(self) -> Sequence[ParamSlot]:
        return [
            ParamSlot("drive", "Drive", (255, 180, 80)),
            ParamSlot("tone", "Tone", (130, 220, 110)),
            ParamSlot("level", "Level", (200, 200, 200)),
        ]
```

`ParamSlot(symbol, label, color, display_fn=None)`. Handles layout, arc-ring
rendering, Tweak1 editing of the selected ring, and LONG_CLICK reset to
snapshot.

### `CompressorPanel` — shared compressor family (`plugins/compressor_base.py`)

Fullscreen: an arc column (Threshold/Ratio/Knee/Makeup) on the left, a
gain-reduction reticule graph + GR bar on the right, live-fed by
`GrMeterClient` (JACK ports `effect_{n}:{in,out}_audio_sym`). A concrete panel
is one line:

```python
class AcompPanel(CompressorPanel):
    SPEC = CompressorSpec(thr_sym="thr", rat_sym="rat", mak_sym="mak", kn_sym="kn")
```

`CompressorSpec(thr_sym, rat_sym, mak_sym, kn_sym=None, in_audio_sym=..., out_audio_sym=...)` —
`kn_sym=None` drops the Knee arc for plugins without one. Encoder routing:
Tweak2=Threshold, Tweak3=Ratio, Tweak1=whichever arc is Nav-selected.

Used by: `acomp`, `advanced_compressor`, `calf_monocompressor`,
`caps_compress`, `invadacompressor`, `mda_dynamics`, `zamcomp`.

### Encoder Convention by Family

| Encoder | Parametric/Graphic EQ | Compressor | MultibandWindow | Notes |
|---|---|---|---|---|
| Tweak1 (id=1) | Gain (parametric) | Nav-selected arc | Selected ring | — |
| Tweak2 (id=2) | Frequency | Threshold | — | — |
| Tweak3 (id=3) | Q | Ratio | — | — |
| Nav | Band select | Arc select | Ring select | Scroll |

---

## The Glyph Ecosystem

All glyphs live in `uilib/glyphs/`, render to SRCALPHA pygame surfaces, and
are blitted by widgets. Most are **alpha masks** (white RGB, coverage in
alpha) tinted at blit time via `BLEND_RGBA_MULT`; a few bake color into
`render()`.

| Glyph | File | What it draws | Used by |
|---|---|---|---|
| `ArcRingGlyph` | `arc_ring.py` | 300° arc ring from 7-o'clock, split at value t | `MultibandWindow` slots, `CompressorPanel` arc column, NAM knob widget |
| `CircleGlyph` | `circle.py` | Filled circle, AA edges | Parametric EQ band nodes, footswitch dots |
| `RingGlyph` | `circle.py` | Centered-stroke ring (hollow circle) | Parametric EQ selection halo |
| `KnobGlyph` | `knob.py` | Hollow ring + pointer line (potentiometer) | Analog control strip icons |
| `ExpressionPedalGlyph` | `expression_pedal.py` | Rocker pedal silhouette | Expression pedal icons |
| `PillGlyph` | `pill.py` | Rounded-rect badge with label | Status badges |
| `RoundedRectGlyph` | `rounded_rect.py` | Filled rounded rect, per-side border | Plugin tiles, buttons |
| `SignalBarsGlyph` | `signal_bars.py` | Cellphone-style signal bars | WiFi status |
| `SpinnerGlyph` | `spinner.py` | Tape-reel spinner | Loading indicators |
| `EthernetCableGlyph` | `ethernet_cable.py` | RJ45 plug silhouette | Ethernet status |
| `KeycapCornerGlyph` | `keycap_corner.py` | Top-left rounded corner arc | Footswitch keycap outlines |

Most glyphs cache their surface factory with `@lru_cache` so repeated renders
with the same parameters share one surface.

---

## The Two EQ Panel Families

**Parametric** (`plugins/eq/parametric.py`, `ParametricEqPanel`): frequency-
response curve across 320px with selectable band nodes. `BandSpec(name, kind,
enable_sym, freq_sym, q_sym, gain_sym, shelf_side, freq_min, freq_max, q_min,
q_max, color, gain_min=-18.0, gain_max=18.0)`, `kind` ∈
`peak|shelf|hp|lp`. CLICK toggles band enable, LONG_CLICK resets.

**Graphic** (`plugins/eq/graphic.py`, `GraphicEqPanel`): vertical bars, 10
visible at a time, scrollable. `GraphicBandSpec(name, freq_hz, gain_sym,
color, gain_min=-18.0, gain_max=18.0)`.

Both: a concrete panel just overrides `build_band_specs()`; the base handles
rendering, encoder routing, and state.

---

## Special Cases

- **NAM** (`pistomp/nam/panel.py`) — a bare `FullscreenPanel`, not a
  `PluginPanel`: it manages a capture session, not plugin parameters.
  `plugins/nam/__init__.py` registers cosmetic-only customization (tile
  color/border/name); the panel opens from the system menu.
- **Notes** (`plugins/notes/panel.py`) — `FullscreenPluginPanel[None]`, no
  editable state. Reads text via `extra_data_fn` from the `effect-N/` TTL and
  displays it as a scrollable viewer. `intercept_shortpress=True` so a single
  click opens the panel instead of toggling bypass.

---

## UI Constraints

| Constraint | Value |
|---|---|
| Display | 320 × 240 pixels, 16-bit RGB |
| SPI clock | 33 MHz (v3), 24 MHz (v2) |
| Poll rate | ~80ms normally, ~10ms with fullscreen panel mounted |
| Font sizes | `default` (20px), `small` (16px), `tiny` (14px), `default_title` (26px) |
| Chrome row | y=210-240, three buttons (`MIN_CHROME_WIDTH`=210 for windows) |
| Nav cycle | Widgets in `add_sel_widget()` order |
| Tweak encoders | 3 (v3) or 1 (v2), id 1/2/3 |
| Surface format | Never bare `pygame.Surface((w,h))` — `SRCALPHA` for alpha, or `depth=32, masks=(0xFF0000, 0xFF00, 0xFF, 0)` for opaque RGB |

---

## Plugin Coverage Status

### Registered (custom UI exists)

| URI | Panel class | Presentation |
|---|---|---|
| `urn:distrho:a-comp` | `AcompPanel` | Compressor |
| `http://moddevices.com/plugins/mod-devel/Advanced-Compressor` | `AdvancedCompressorPanel` | Compressor |
| `http://calf.sourceforge.net/plugins/MonoCompressor` | `CalfMonoCompressorPanel` | Compressor |
| `http://moddevices.com/plugins/caps/Compress` | `CapsCompressPanel` | Compressor |
| `http://invadarecords.com/plugins/lv2/compressor/{mono,stereo}` | `InvadaCompressorPanel` | Compressor |
| `http://moddevices.com/plugins/mda/Dynamics` | `MdaDynamicsPanel` | Compressor |
| `urn:zamaudio:ZamComp` | `ZamCompPanel` | Compressor |
| `http://moddevices.com/plugins/mod-devel/System-Compressor` | `SystemCompressorWindow` | MultibandWindow |
| `http://moddevices.com/plugins/caps/Noisegate` | `CapsNoisegateWindow` | MultibandWindow |
| `http://moddevices.com/plugins/mda/MultiBand` | `MdaMultiBandWindow` | MultibandWindow |
| `http://moddevices.com/plugins/mda/Bandisto` | `MdaBandistoWindow` | MultibandWindow |
| `http://moddevices.com/plugins/caps/Eq10X2` | `CapsEq10X2Window` | MultibandWindow |
| `http://distrho.sf.net/plugins/3BandEQ` | `ThreeBandEqWindow` | MultibandWindow |
| `http://distrho.sf.net/plugins/3BandSplitter` | `ThreeBandSplitterWindow` | MultibandWindow |
| `urn:distrho:a-eq` | `DistrhoAEqPanel` | Parametric EQ |
| `urn:zamaudio:ZamEQ2` | `ZamEQ2Panel` | Parametric EQ |
| `http://moddevices.com/plugins/tap/eq` | `TapEqPanel` | Parametric EQ |
| `http://moddevices.com/plugins/tap/eqbw` | `TapEqBwPanel` | Parametric EQ |
| `http://gareus.org/oss/lv2/fil4#{mono,stereo}` | `Fil4Panel` | Full panel |
| `http://moddevices.com/plugins/caps/Eq10` | `CapsEq10Panel` | Graphic EQ |
| `http://guitarix.sourceforge.net/plugins/gx_graphiceq_#_graphiceq_` | `GxGraphicEqPanel` | Graphic EQ |
| `http://guitarix.sourceforge.net/plugins/gx_barkgraphiceq_#_barkgraphiceq_` | `GxBarkGraphicEqPanel` | Graphic EQ |
| `urn:zamaudio:ZamGEQ31` | `ZamGEQ31Panel` | Graphic EQ |
| `http://moddevices.com/plugins/tap/reverb` | `TapReverbPanel` | Full panel |
| `http://guitarix.sourceforge.net/plugins/gx_cabinet#CABINET` | `GxCabinetPanel` | Full panel (mode selector + 3 arc knobs, same shape as `TapReverbPanel`) |
| `http://open-music-kontrollers.ch/lv2/notes#notes` | `NotesPanel` | Full panel (intercepts short-press) |
| NAM (`neural-amp-modeler-lv2`, `gareus.org/.../nam`, `tone3000.com/plugins/nam`) | `NamCapturePanel` | Cosmetic only, opened from system menu |

### Top Uncovered Plugins (by combined pedalboard frequency, GitHub + device)

| Combined | URI | Category | Suggested approach |
|---|---:|---|---|
| 16 | `http://moddevices.com/plugins/mod-devel/BigMuffPi` | Fuzz | MultibandWindow (3 knobs) |
| 14 | `http://guitarix.sourceforge.net/plugins/gx_hotbox_#_hotbox_` | Amp sim | Fullscreen (preamp+EQ) |
| 13 | `http://moddevices.com/plugins/tap/tubewarmth` | Saturation | MultibandWindow (1 knob) |
| 12 | `https://github.com/ninodewit/SHIRO-Plugins/plugins/modulay` | Modulation | Fullscreen (multi-mode) |
| 12 | `https://ca9.eu/lv2/bolliedelay` | Delay | MultibandWindow (3 knobs) |
| 12 | `http://guitarix.sourceforge.net/plugins/gx_amp#GUITARIX` | Amp sim | Fullscreen (amp head) |
| 11 | `http://moddevices.com/plugins/tap/reverb` | Reverb | done — `TapReverbPanel` |
| 9 | `http://distrho.sf.net/plugins/MVerb` | Reverb | Fullscreen (decay/size/mix) |
| 9 | `http://rakarrack.sourceforge.net/effects.html#chor` | Modulation | MultibandWindow |
| 9 | `http://guitarix.sourceforge.net/plugins/gx_luna_#_luna_` | Preamp | Fullscreen |
| 8 | `http://guitarix.sourceforge.net/plugins/gx_sd1sim_#_sd1sim_` | OD | MultibandWindow |
| 7 | `http://rakarrack.sourceforge.net/effects.html#eqp` | EQ | Parametric EQ |
| 7 | `http://moddevices.com/plugins/mod-devel/mixer` | Utility | MultibandWindow |
| 7 | `http://moddevices.com/plugins/tap/echo` | Delay | MultibandWindow |
| 6 | `http://moddevices.com/plugins/tap/tremolo` | Modulation | MultibandWindow |
| 6 | `http://moddevices.com/plugins/tap/chorusflanger` | Modulation | MultibandWindow |
| 6 | `http://moddevices.com/plugins/caps/PlateX2` | Reverb | MultibandWindow |
| 6 | `http://moddevices.com/plugins/caps/AmpVTS` | Amp sim | Fullscreen |
| 6 | `http://guitarix.sourceforge.net/plugins/gxautowah#wah` | Filter | MultibandWindow |
| 6 | `http://guitarix.sourceforge.net/plugins/gx_switchless_wah#wah` | Filter | MultibandWindow |
| 6 | `https://github.com/brummer10/CollisionDrive` | OD | MultibandWindow |
| 6 | `http://rakarrack.sourceforge.net/effects.html#StompBox_fuzz` | Fuzz | MultibandWindow |
| 5 | `http://guitarix.sourceforge.net/plugins/gx_bottlerocket_#_bottlerocket_` | Boost | MultibandWindow |
| 5 | `https://github.com/brummer10/Rumor` | Modulation | MultibandWindow |
| 5 | `http://plugin.org.uk/swh-plugins/valve` | Saturation | MultibandWindow |
| 4 | `urn:zamaudio:ZamComp` | Dynamics | done — `ZamCompPanel` |
| 3 | `http://moddevices.com/plugins/mod-devel/LowPassFilter` | Filter | MultibandWindow |
| 3 | `http://www.openavproductions.com/artyfx#roomy` | Reverb | MultibandWindow |
| 3 | `http://moddevices.com/plugins/tap/reflector` | Reverb | MultibandWindow |
| 3 | `http://moddevices.com/plugins/tap/doubler` | Modulation | MultibandWindow |
| 3 | `http://moddevices.com/plugins/sooperlooper` | Looper | Fullscreen (special) |
| 3 | `http://moddevices.com/plugins/mod-devel/SuperWhammy` | Pitch | MultibandWindow |
| 3 | `http://moddevices.com/plugins/mod-devel/DS1` | Distortion | MultibandWindow |
| 3 | `http://moddevices.com/plugins/mod-devel/Drop` | Pitch | MultibandWindow |
| 3 | `http://moddevices.com/plugins/mod-devel/2Voices` | Pitch | MultibandWindow |
| 2 | `urn:distrho:a-reverb` | Reverb | Fullscreen |
| 2 | `http://moddevices.com/plugins/caps/Plate` | Reverb | MultibandWindow |
| 2 | `http://moddevices.com/plugins/caps/PhaserII` | Modulation | MultibandWindow |
| 2 | `http://moddevices.com/plugins/caps/Compress` | Dynamics | done — `CapsCompressPanel` |
| 2 | `http://invadarecords.com/plugins/lv2/phaser/mono` | Modulation | MultibandWindow |
| 2 | `http://www.openavproductions.com/artyfx#kuiza` | Distortion | MultibandWindow |
| 2 | `http://moddevices.com/plugins/mod-devel/HighPassFilter` | Filter | MultibandWindow |
| 2 | `http://moddevices.com/plugins/caps/ChorusI` | Modulation | MultibandWindow |
| 2 | `http://VeJaPlugins.com/plugins/Release/cabsim` | Cab sim | MultibandWindow |
| 1 | `http://calf.sourceforge.net/plugins/MonoCompressor` | Dynamics | done — `CalfMonoCompressorPanel` |
| 1 | `http://moddevices.com/plugins/mod-devel/System-Compressor` | Dynamics | done — `SystemCompressorWindow` |
| 1 | `http://moddevices.com/plugins/mod-devel/Advanced-Compressor` | Dynamics | done — `AdvancedCompressorPanel` |
| 1 | `http://moddevices.com/plugins/mda/Ambience` | Reverb | MultibandWindow |
| 1 | `http://moddevices.com/plugins/mda/Stereo` | Utility | MultibandWindow |
| 1 | `http://moddevices.com/plugins/mda/Degrade` | Distortion | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_DOP250_#_DOP250_` | Distortion | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_guvnor_#_guvnor_` | Distortion | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_voodoo_#_voodoo_` | Distortion | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_fuzzfacefm_#_fuzzfacefm_` | Fuzz | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_liquiddrive_#_liquiddrive_` | OD | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_MicroAmp_#_MicroAmp_` | Amp sim | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_oc_2_#_oc_2_` | Octave | MultibandWindow |
| 1 | `http://guitarix.sourceforge.net/plugins/gxts9#ts9sim` | OD | MultibandWindow |
| 1 | `http://remaincalm.org/plugins/{avocado,floaty}` | Reverb | MultibandWindow |
| 1 | `http://remaincalm.org/plugins/{mud,paranoia}` | Distortion | MultibandWindow |
| 1 | `http://devcurmudgeon.com/alo` | Reverb | MultibandWindow |
| 1 | `http://gareus.org/oss/lv2/modmeter`, `.../string-machine`, `FluidPlug_Black_Pearl_4A`, `midi-display.lv2`, `carla/plugins/audiofile` | Utility/Instrument | — (low priority, ≤1 pedalboard each) |

Re-derive this ranking with the LV2-inspection commands in `CLAUDE.md` if it
needs refreshing — usage shifts as pedalboards are added.
