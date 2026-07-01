# Plugin Customization Guide

## Conceptual Principal Components

The pi-stomp plugin customization system decomposes into five independent
dimensions. Every existing plugin implementation is a point in this space:

| Dimension | What it controls | Values |
|---|---|---|
| **Panel type** | Fullscreen vs menu-widget vs cosmetic-only | `panel_cls`, `menu_widget_cls`, or neither |
| **Visualization** | How the plugin's state is drawn | Curve (parametric EQ), bars (graphic EQ), arc rings (menu widget), custom (notes, NAM) |
| **Encoder routing** | Which tweak encoder does what | Tweak1/2/3 → gain/freq/Q, or custom per-panel |
| **Tile chrome** | How the plugin tile looks in the main grid | `tile_active_color`, `tile_border`, `display_name_fn`, `subtitle_fn` |
| **Extra data** | Per-instance state from `effect-N/` TTL | `extra_data_fn` → `PluginExtraData` subclass |

These five axes are orthogonal. A plugin can have:
- A fullscreen panel + custom tile chrome (most EQs)
- A menu widget + custom tile chrome (MDA Bandisto, 3BandEQ)
- Only custom tile chrome (NAM — the full panel lives in `pistomp/nam/`)
- A fullscreen panel that intercepts short-press (Notes)

---

## Architecture Overview

### The Registry

`plugins/customization.py` maintains a `dict[URI, PluginCustomization]`.
Registration happens at import time in each `plugins/{name}/__init__.py`:

```python
from plugins.customization import PluginCustomization, register

register(
    "urn:distrho:a-eq",
    customization=PluginCustomization(
        panel_cls=DistrhoAEqPanel,
        display_name="DISTRHO Audio EQ",
    ),
)
```

The URI must match **exactly** what appears in the plugin's `manifest.ttl`
and the pedalboard TTL's `lv2:prototype`. No normalization, no fuzzy matching.

### Dispatch Path

When a user long-presses a plugin tile in the main grid, `lcd320x240.py`
`plugin_event()` checks:

1. If `panel_cls` is set → `handler.show_fullscreen_panel(plugin, panel_cls)`
2. Else if `menu_widget_cls` is set → `_show_custom_layout_menu(plugin, menu_widget_cls)`
3. Else → `draw_parameter_menu(plugin)` (the generic parameter list)

If `intercept_shortpress=True` (Notes), a short-press also opens the panel.

### The PluginCustomization Dataclass

```python
@dataclass(frozen=True)
class PluginCustomization:
    panel_cls: type[PluginPanel] | None = None
    menu_widget_cls: type[Widget] | None = None
    display_name: str | None = None
    display_name_fn: Callable[[Plugin], str | None] | None = None
    subtitle_fn: Callable[[Plugin], str | None] | None = None
    intercept_shortpress: bool = False
    tile_active_color: tuple[int, int, int] | None = None
    tile_border: RectBorder | None = None
    extra_data: PluginExtraData | None = None
```

---

## Panel Type 1: Fullscreen Panel (`PluginPanel`)

### Base Class Contract

`plugins/base.py` defines `PluginPanel[TState]`, a generic abstract class
that subclasses `FullscreenPanel` (which subclasses `Panel` + `InputSink`).

Every fullscreen panel must implement:

```python
class MyPanel(PluginPanel[MyState]):

    def snapshot_state(self) -> MyState:
        """Read plugin.parameters into a typed state object."""

    def apply_state(self, state: MyState) -> None:
        """Push state back into the panel's widgets."""

    def build_widgets(self) -> None:
        """Create and register panel-specific widgets.
        Use self.add_sel_widget(...) for anything that should participate
        in Nav cycling. The base appends chrome (Back/Bypass/Reset) after
        this returns.
        """
```

### What the Base Provides

- **Chrome row**: Back / Bypass / Reset buttons fixed at the bottom (y=210-240).
  Bypass routes directly to the plugin + websocket push. Reset restores all
  symbols from `plugin.pedalboard_snapshot`, skipping blend-locked ones.
- **Param-send coalescing**: `set_param(symbol, value)` queues a change;
  `tick()` drains the queue. Rapid encoder spins collapse into one send per
  symbol.
- **InputSink**: `handle(event)` dispatches EncoderEvent (id 1/2/3) to
  `on_encoder_rotation(encoder_id, rotations)`. Return True to consume.

### Chrome Row Details

The chrome row is three buttons, each 104px wide, at y=210:

```
[ Back ]  [ Bypass ]  [ Reset ]
```

- **Back**: calls `on_dismiss()` (usually `handler.hide_fullscreen_panel()`)
- **Bypass**: toggles `plugin.set_bypass()`, sends WS, refreshes style
- **Reset**: restores all non-bypass, non-locked symbols from snapshot

Subclasses can hide buttons (e.g. Notes hides Bypass/Reset) and resize
Back to full width.

### Encoder Convention

| Encoder | Parametric EQ | Graphic EQ | Notes | NAM Capture |
|---|---|---|---|---|
| Tweak1 (id=1) | Gain | Gain | — | Nav select |
| Tweak2 (id=2) | Frequency | — | — | Input gain |
| Tweak3 (id=3) | Q | — | — | Headphone vol |
| Nav | — | — | Scroll | Nav select |

The convention is: Tweak1 = primary parameter, Tweak2 = secondary,
Tweak3 = tertiary. Return `True` from `on_encoder_rotation()` to consume.

### Tick

`tick()` is called every LCD poll cycle (~80ms normally, ~10ms when a
fullscreen panel is mounted). The base class drains the param queue.
Subclasses override to animate (NAM meters, bypass state changes).

---

## Panel Type 2: Menu Widget (`CustomMenuWidget`)

### When to Use

For plugins with 2-8 parameters that don't need a full-screen visualization.
The menu widget appears in a `CustomLayoutMenu` panel (title bar + widget +
Back button) when the user long-presses the plugin tile.

### Base Class Contract

`plugins/multiband_menu.py` defines `CustomMenuWidget(ContainerWidget)`:

```python
class MyMenuWidget(CustomMenuWidget):
    def build_slots(self) -> Sequence[ParamSlot]:
        return [
            ParamSlot("symbol", "Label", (R, G, B)),
            ParamSlot("symbol", "Label", (R, G, B), display_fn=my_formatter),
            ...
        ]
```

### ParamSlot

```python
@dataclass(frozen=True)
class ParamSlot:
    symbol: str           # LV2 port symbol
    label: str            # Display label (short, ≤8 chars)
    color: tuple[int,int,int]  # Arc ring fill color
    display_fn: Callable[[float], str] | None = None  # Optional formatter
```

### Layout

- 1-4 slots → single row of 4
- 5-8 slots → 2 rows of 4
- Each slot is an arc ring (ArcRingGlyph) with label + value text
- Tweak1 adjusts the selected parameter; Tweak2/3 are ignored
- CLICK on a slot is a no-op; LONG_CLICK resets to snapshot

### Example: MDA Bandisto

```python
class MdaBandistoMenuWidget(CustomMenuWidget):
    def build_slots(self):
        return [
            ParamSlot("l_m", "L↔M", (255, 180, 80), display_fn=self._fmt_hz),
            ParamSlot("m_h", "M↔H", (210, 130, 230), display_fn=self._fmt_hz),
            ParamSlot("l_dist", "L Dist", (255, 230, 80)),
            ParamSlot("m_dist", "M Dist", (130, 220, 110)),
            ParamSlot("h_dist", "H Dist", (110, 200, 230)),
            ParamSlot("l_out", "L Out", (200, 200, 200)),
            ParamSlot("m_out", "M Out", (180, 180, 180)),
            ParamSlot("h_out", "H Out", (160, 160, 160)),
        ]
```

---

## The Glyph Ecosystem

All glyphs live in `uilib/glyphs/`. They render to SRCALPHA pygame surfaces
and are blitted by widgets. Most are **alpha masks** (white RGB, coverage in
alpha) tinted at blit time via `BLEND_RGBA_MULT`.

| Glyph | File | What it draws | Used by |
|---|---|---|---|
| `ArcRingGlyph` | `arc_ring.py` | 300° arc ring from 7-o'clock, split at value t, with tip dot | Menu widget slots, NAM knob widget |
| `CircleGlyph` | `circle.py` | Filled circle, AA edges | Parametric EQ band nodes, footswitch dots |
| `RingGlyph` | `circle.py` | Centered-stroke ring (hollow circle) | Parametric EQ selection halo |
| `KnobGlyph` | `knob.py` | Hollow ring + pointer line (potentiometer) | Analog control strip icons |
| `ExpressionPedalGlyph` | `expression_pedal.py` | Rocker pedal silhouette | Expression pedal icons |
| `PillGlyph` | `pill.py` | Rounded-rect badge with label | Status badges |
| `RoundedRectGlyph` | `rounded_rect.py` | Filled rounded rect with per-side border | Plugin tiles, buttons |
| `SignalBarsGlyph` | `signal_bars.py` | Cellphone-style signal bars | WiFi status |
| `SpinnerGlyph` | `spinner.py` | Tape-reel spinner with rotating spokes | Loading indicators |
| `EthernetCableGlyph` | `ethernet_cable.py` | RJ45 plug silhouette | Ethernet status |
| `KeycapCornerGlyph` | `keycap_corner.py` | Top-left rounded corner arc | Footswitch keycap outlines |

### Glyph Usage Patterns

**Alpha mask (tinted at blit):** `CircleGlyph`, `RingGlyph`, `KnobGlyph`,
`ExpressionPedalGlyph`. The glyph renders white RGB with coverage in alpha;
the caller multiplies a color into it:

```python
tinted = mask.copy()
color_surf = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
color_surf.fill(color)
tinted.blit(color_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
```

**Color baked in:** `ArcRingGlyph`, `RoundedRectGlyph`, `SpinnerGlyph`,
`PillGlyph`, `SignalBarsGlyph`, `EthernetCableGlyph`. The color is passed
to `render()` and baked into the surface.

**Caching:** Most glyphs use `@lru_cache` on the underlying surface factory
so repeated renders with the same parameters share one surface.

---

## The Two EQ Panel Families

### Parametric EQ (`plugins/eq/parametric.py`)

A frequency-response curve across 320px, with band nodes (circles) that
the user selects via Nav and edits with Tweak1/2/3.

**BandSpec** (static schema):
```python
@dataclass(frozen=True)
class BandSpec:
    name: str
    kind: Literal["peak", "shelf", "hp", "lp"]
    enable_sym: str | None     # LV2 port for band enable
    freq_sym: str              # LV2 port for frequency
    q_sym: str | None          # LV2 port for Q (None = fixed)
    gain_sym: str | None       # LV2 port for gain (None = no gain)
    shelf_side: Literal["low", "high"] | None
    freq_min: float
    freq_max: float
    q_min: float
    q_max: float
    color: tuple[int, int, int]
    gain_min: float = -18.0
    gain_max: float = 18.0
```

**Concrete panel** (e.g. `DistrhoAEqPanel`):
```python
class DistrhoAEqPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
```

That's it. The base class handles all rendering, encoder routing, and
state management. The band_spec module maps LV2 port symbols to the
abstract BandSpec schema.

### Graphic EQ (`plugins/eq/graphic.py`)

Vertical bars, 10 visible at a time, scrollable. Each bar is 3px wide
in a 32px column.

**GraphicBandSpec** (static schema):
```python
@dataclass(frozen=True)
class GraphicBandSpec:
    name: str
    freq_hz: float
    gain_sym: str
    color: tuple[int, int, int]
    gain_min: float = -18.0
    gain_max: float = 18.0
```

**Concrete panel** (e.g. `CapsEq10Panel`):
```python
class CapsEq10Panel(GraphicEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
```

---

## The NAM Panel (Special Case)

`pistomp/nam/panel.py` is a `FullscreenPanel` (not a `PluginPanel`) because
it doesn't edit a plugin's parameters — it manages a capture session. It
registers via `plugins/nam/__init__.py` for cosmetic customization only
(tile color, border, display name), and the actual panel is opened from
the system menu, not from a plugin tile long-press.

This is the only panel that uses `ArcRingGlyph` for knob rendering
(`KnobWidget`), `ProgressBarWidget` for capture progress, and
`LevelMeter` for VU meters.

---

## The Notes Panel (Special Case)

`plugins/notes/panel.py` is a `PluginPanel[None]` — it has no state to
edit. It reads text from the `effect-N/` TTL via `extra_data_fn` and
displays it as a scrollable text viewer. It intercepts short-press so
a single click opens the panel instead of toggling bypass.

---

## UI Constraints

| Constraint | Value |
|---|---|
| Display | 320 × 240 pixels, 16-bit RGB |
| SPI clock | 33 MHz (v3), 24 MHz (v2) |
| Poll rate | ~80ms normally, ~10ms with fullscreen panel |
| Font sizes | `default` (20px), `small` (16px), `tiny` (14px), `default_title` (26px) |
| Chrome row | y=210-240, three 104px buttons |
| Nav cycle | Widgets in `add_sel_widget()` order, Nav encoder steps through |
| Tweak encoders | 3 (v3) or 1 (v2), id 1/2/3 |
| Surface format | Never `pygame.Surface((w,h))` bare — use `SRCALPHA` for alpha, or `depth=32, masks=(0xFF0000, 0xFF00, 0xFF, 0)` for opaque RGB |

---

## Complete Plugin Usage Data

### GitHub Pedalboards (master + v1 + v2, deduplicated)

| Count | URI | Plugin | Category |
|---|---:|---|---|
| 32 | `http://moddevices.com/plugins/caps/Noisegate` | caps Noisegate | Dynamics |
| 24 | `http://guitarix.sourceforge.net/plugins/gx_cabinet#CABINET` | gx_cabinet | Cab sim |
| 24 | `http://gareus.org/oss/lv2/tinygain#stereo` | tinygain stereo | Utility |
| 19 | `http://gareus.org/oss/lv2/tinygain#mono` | tinygain mono | Utility |
| 15 | `http://moddevices.com/plugins/mod-devel/BigMuffPi` | Big Muff Pi | Fuzz |
| 14 | `http://guitarix.sourceforge.net/plugins/gx_hotbox_#_hotbox_` | gx_hotbox | Amp sim |
| 12 | `https://github.com/ninodewit/SHIRO-Plugins/plugins/modulay` | Modulay | Modulation |
| 12 | `https://ca9.eu/lv2/bolliedelay` | BollieDelay | Delay |
| 12 | `http://moddevices.com/plugins/tap/tubewarmth` | TAP tubewarmth | Saturation |
| 12 | `http://guitarix.sourceforge.net/plugins/gx_amp#GUITARIX` | gx_amp | Amp sim |
| 11 | `http://moddevices.com/plugins/tap/reverb` | TAP reverb | Reverb |
| 10 | `http://moddevices.com/plugins/caps/Eq10` | caps Eq10 | EQ |
| 9 | `http://rakarrack.sourceforge.net/effects.html#chor` | Rakarrack chorus | Modulation |
| 9 | `http://guitarix.sourceforge.net/plugins/gx_luna_#_luna_` | gx_luna | Preamp |
| 9 | `http://distrho.sf.net/plugins/MVerb` | MVerb | Reverb |
| 8 | `http://guitarix.sourceforge.net/plugins/gx_sd1sim_#_sd1sim_` | gx_sd1sim | OD |
| 6 | `http://moddevices.com/plugins/tap/tremolo` | TAP tremolo | Modulation |
| 6 | `http://moddevices.com/plugins/tap/echo` | TAP echo | Delay |
| 6 | `http://moddevices.com/plugins/tap/chorusflanger` | TAP chorus/flanger | Modulation |
| 6 | `http://moddevices.com/plugins/caps/PlateX2` | caps PlateX2 | Reverb |
| 6 | `http://moddevices.com/plugins/caps/AmpVTS` | caps AmpVTS | Amp sim |
| 6 | `http://guitarix.sourceforge.net/plugins/gxautowah#wah` | gx_autowah | Filter |
| 6 | `http://guitarix.sourceforge.net/plugins/gx_switchless_wah#wah` | gx_switchless_wah | Filter |
| 5 | `http://guitarix.sourceforge.net/plugins/gx_bottlerocket_#_bottlerocket_` | gx_bottlerocket | Boost |
| 4 | `https://github.com/brummer10/CollisionDrive` | CollisionDrive | OD |
| 4 | `http://VeJaPlugins.com/plugins/Release/cabsim` | VeJa cabsim | Cab sim |
| 3 | `urn:zamaudio:ZamComp` | ZamComp | Compressor |
| 3 | `http://www.openavproductions.com/artyfx#roomy` | Artyfx roomy | Reverb |
| 3 | `http://rakarrack.sourceforge.net/effects.html#StompBox_fuzz` | Rakarrack fuzz | Fuzz |
| 3 | `http://rakarrack.sourceforge.net/effects.html#reve` | Rakarrack reverb | Reverb |
| 3 | `http://open-music-kontrollers.ch/lv2/notes#notes` | Notes | Utility |
| 3 | `http://moddevices.com/plugins/tap/reflector` | TAP reflector | Reverb |
| 3 | `http://moddevices.com/plugins/tap/eq` | TAP EQ | EQ |
| 3 | `http://moddevices.com/plugins/tap/doubler` | TAP doubler | Modulation |
| 3 | `http://moddevices.com/plugins/sooperlooper` | SooperLooper | Looper |
| 3 | `http://moddevices.com/plugins/mod-devel/SuperWhammy` | SuperWhammy | Pitch |
| 3 | `http://moddevices.com/plugins/mod-devel/DS1` | DS1 | Distortion |
| 3 | `http://moddevices.com/plugins/mod-devel/Drop` | Drop | Pitch |
| 3 | `http://moddevices.com/plugins/mod-devel/2Voices` | 2Voices | Pitch |
| 3 | `http://moddevices.com/plugins/mda/Dynamics` | MDA Dynamics | Dynamics |
| 2 | `http://github.com/mikeoliphant/neural-amp-modeler-lv2` | NAM | Amp sim |
| 2 | `urn:distrho:a-reverb` | DISTRHO reverb | Reverb |
| 2 | `http://moddevices.com/plugins/tap/eqbw` | TAP EQ/BW | EQ |
| 2 | `http://moddevices.com/plugins/caps/Plate` | caps Plate | Reverb |
| 2 | `http://moddevices.com/plugins/caps/PhaserII` | caps PhaserII | Modulation |
| 2 | `http://moddevices.com/plugins/caps/Compress` | caps Compress | Dynamics |
| 2 | `http://guitarix.sourceforge.net/plugins/gx_DOP250_#_DOP250_` | gx_DOP250 | Distortion |
| 2 | `http://guitarix.sourceforge.net/plugins/gx_guvnor_#_guvnor_` | gx_guvnor | Distortion |
| 2 | `http://guitarix.sourceforge.net/plugins/gx_voodoo_#_voodoo_` | gx_voodoo | Distortion |
| 2 | `http://guitarix.sourceforge.net/plugins/gx_digital_delay_#_digital_delay_` | gx_digital_delay | Delay |
| 2 | `http://guitarix.sourceforge.net/plugins/gx_digital_delay_st_#_digital_delay_st_` | gx_digital_delay_st | Delay |
| 2 | `http://invadarecords.com/plugins/lv2/phaser/mono` | Invada phaser | Modulation |
| 2 | `http://kxstudio.sf.net/carla/plugins/audiofile` | Carla audiofile | Utility |
| 1 | `http://moddevices.com/plugins/mda/Stereo` | MDA Stereo | Utility |
| 1 | `http://moddevices.com/plugins/mda/Ambience` | MDA Ambience | Reverb |
| 1 | `http://moddevices.com/plugins/mod-devel/Advanced-Compressor` | Advanced Compressor | Dynamics |
| 1 | `http://moddevices.com/plugins/mod-devel/System-Compressor` | System Compressor | Dynamics |
| 1 | `http://moddevices.com/plugins/caps/Wider` | caps Wider | Utility |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_bottlerocket_#_bottlerocket_` | gx_bottlerocket | Boost |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_fuzzfacefm_#_fuzzfacefm_` | gx_fuzzfacefm | Fuzz |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_liquiddrive_#_liquiddrive_` | gx_liquiddrive | OD |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_MicroAmp_#_MicroAmp_` | gx_MicroAmp | Amp sim |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_oc_2_#_oc_2_` | gx_oc_2 | Octave |
| 1 | `http://guitarix.sourceforge.net/plugins/gxts9#ts9sim` | gx_ts9 | OD |
| 1 | `http://remaincalm.org/plugins/avocado` | Avocado | Reverb |
| 1 | `http://remaincalm.org/plugins/floaty` | Floaty | Reverb |
| 1 | `http://remaincalm.org/plugins/mud` | Mud | Distortion |
| 1 | `http://remaincalm.org/plugins/paranoia` | Paranoia | Distortion |

### Device Pedalboards (pistomp@pistomp.local:~/data/.pedalboards)

| Count | URI | Plugin | Category |
|---|---:|---|---|
| 13 | `http://gareus.org/oss/lv2/tinygain#mono` | tinygain mono | Utility |
| 7 | `http://rakarrack.sourceforge.net/effects.html#eqp` | Rakarrack eqp | EQ |
| 7 | `http://moddevices.com/plugins/mod-devel/mixer` | MOD mixer | Utility |
| 6 | `https://github.com/brummer10/CollisionDrive` | CollisionDrive | OD |
| 6 | `http://rakarrack.sourceforge.net/effects.html#StompBox_fuzz` | Rakarrack fuzz | Fuzz |
| 5 | `https://github.com/brummer10/Rumor` | Rumor | Modulation |
| 5 | `http://plugin.org.uk/swh-plugins/valve` | SWH valve | Saturation |
| 5 | `http://invadarecords.com/plugins/lv2/compressor/mono` | Invada compressor | Dynamics |
| 5 | `http://gareus.org/oss/lv2/tinygain#stereo` | tinygain stereo | Utility |
| 5 | `http://gareus.org/oss/lv2/fil4#mono` | fil4 | Filter/EQ |
| 4 | `urn:distrho:a-eq` | DISTRHO Audio EQ | EQ |
| 3 | `urn:zamaudio:ZamGEQ31` | ZamGEQ31 | EQ |
| 3 | `urn:zamaudio:ZamEQ2` | ZamEQ2 | EQ |
| 3 | `http://moddevices.com/plugins/tap/eqbw` | TAP EQ/BW | EQ |
| 3 | `http://moddevices.com/plugins/tap/eq` | TAP EQ | EQ |
| 3 | `http://moddevices.com/plugins/mod-devel/LowPassFilter` | MOD LPF | Filter |
| 3 | `http://moddevices.com/plugins/caps/Eq10` | caps Eq10 | EQ |
| 3 | `http://guitarix.sourceforge.net/plugins/gx_barkgraphiceq_#_barkgraphiceq_` | gx_barkgraphiceq | EQ |
| 3 | `http://github.com/mikeoliphant/neural-amp-modeler-lv2` | NAM | Amp sim |
| 2 | `http://www.openavproductions.com/artyfx#kuiza` | Artyfx kuiza | Distortion |
| 2 | `http://moddevices.com/plugins/mod-devel/HighPassFilter` | MOD HPF | Filter |
| 2 | `http://moddevices.com/plugins/caps/ChorusI` | caps ChorusI | Modulation |
| 2 | `http://guitarix.sourceforge.net/plugins/gx_graphiceq_#_graphiceq_` | gx_graphiceq | EQ |
| 1 | `urn:distrho:a-comp` | DISTRHO compressor | Dynamics |
| 1 | `http://moddevices.com/plugins/tap/tubewarmth` | TAP tubewarmth | Saturation |
| 1 | `http://moddevices.com/plugins/tap/echo` | TAP echo | Delay |
| 1 | `http://moddevices.com/plugins/mod-devel/BigMuffPi` | Big Muff Pi | Fuzz |
| 1 | `http://moddevices.com/plugins/mod-devel/System-Compressor` | System Compressor | Dynamics |
| 1 | `http://moddevices.com/plugins/mod-devel/Advanced-Compressor` | Advanced Compressor | Dynamics |
| 1 | `http://moddevices.com/plugins/caps/Noisegate` | caps Noisegate | Dynamics |
| 1 | `http://moddevices.com/plugins/caps/Wider` | caps Wider | Utility |
| 1 | `http://moddevices.com/plugins/mda/EPiano` | MDA EPiano | Instrument |
| 1 | `http://moddevices.com/plugins/mda/Degrade` | MDA Degrade | Distortion |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_bottlerocket_#_bottlerocket_` | gx_bottlerocket | Boost |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_fuzzfacefm_#_fuzzfacefm_` | gx_fuzzfacefm | Fuzz |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_liquiddrive_#_liquiddrive_` | gx_liquiddrive | OD |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_MicroAmp_#_MicroAmp_` | gx_MicroAmp | Amp sim |
| 1 | `http://guitarix.sourceforge.net/plugins/gxts9#ts9sim` | gx_ts9 | OD |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_oc_2_#_oc_2_` | gx_oc_2 | Octave |
| 1 | `http://calf.sourceforge.net/plugins/MonoCompressor` | Calf MonoCompressor | Dynamics |
| 1 | `http://gareus.org/oss/lv2/modmeter` | modmeter | Utility |
| 1 | `http://gareus.org/oss/lv2/fil4#mono` | fil4 | Filter/EQ |
| 1 | `http://devcurmudgeon.com/alo` | alo | Reverb |
| 1 | `http://jpcima.sdf1.org/lv2/string-machine` | String machine | Instrument |
| 1 | `http://kxstudio.linuxaudio.org/plugins/FluidPlug_Black_Pearl_4A` | Black Pearl 4A | Instrument |
| 1 | `https://github.com/vallsv/midi-display.lv2` | MIDI display | Utility |
| 1 | `http://rakarrack.sourceforge.net/effects.html#delm` | Rakarrack delay | Delay |

### Already Registered (covered by custom UI)

| URI | Registration | Type |
|---|---|---|
| `http://guitarix.sourceforge.net/plugins/gx_barkgraphiceq_#_barkgraphiceq_` | `barkgraphiceq` | Full panel |
| `http://moddevices.com/plugins/caps/Eq10` | `capseq10` | Full panel |
| `http://moddevices.com/plugins/caps/Eq10X2` | `capseq10x2` | Menu widget |
| `urn:distrho:a-eq` | `distaq` | Full panel |
| `http://gareus.org/oss/lv2/fil4#mono` | `fil4` | Full panel |
| `http://gareus.org/oss/lv2/fil4#stereo` | `fil4` | Full panel |
| `http://guitarix.sourceforge.net/plugins/gx_graphiceq_#_graphiceq_` | `graphiceq` | Full panel |
| `http://moddevices.com/plugins/mda/Bandisto` | `mdabandisto` | Menu widget |
| `http://moddevices.com/plugins/mda/MultiBand` | `mdamultiband` | Menu widget |
| `http://github.com/mikeoliphant/neural-amp-modeler-lv2` | `nam` | Cosmetic only |
| `http://gareus.org/oss/lv2/nam#mono` | `nam` | Cosmetic only |
| `http://gareus.org/oss/lv2/nam#stereo` | `nam` | Cosmetic only |
| `https://tone3000.com/plugins/nam` | `nam` | Cosmetic only |
| `http://open-music-kontrollers.ch/lv2/notes#notes` | `notes` | Full panel |
| `http://moddevices.com/plugins/tap/eq` | `tapeq` | Full panel |
| `http://moddevices.com/plugins/tap/eqbw` | `tapeqbw` | Full panel |
| `http://distrho.sf.net/plugins/3BandEQ` | `three_band_eq` | Menu widget |
| `http://distrho.sf.net/plugins/3BandSplitter` | `three_band_splitter` | Menu widget |
| `urn:zamaudio:ZamEQ2` | `zameq2` | Full panel |
| `urn:zamaudio:ZamGEQ31` | `zamgeq31` | Full panel |

### Top Uncovered Plugins (by combined frequency)

| Combined | URI | Category | Suggested approach |
|---|---:|---|---|
| 33 | `http://moddevices.com/plugins/caps/Noisegate` | Dynamics | Menu widget (1-2 params) |
| 24 | `http://guitarix.sourceforge.net/plugins/gx_cabinet#CABINET` | Cab sim | Full panel (model + 3-band EQ) |
| 16 | `http://moddevices.com/plugins/mod-devel/BigMuffPi` | Fuzz | Menu widget (3 knobs) |
| 14 | `http://guitarix.sourceforge.net/plugins/gx_hotbox_#_hotbox_` | Amp sim | Full panel (preamp+EQ) |
| 13 | `http://moddevices.com/plugins/tap/tubewarmth` | Saturation | Menu widget (1 knob) |
| 12 | `https://github.com/ninodewit/SHIRO-Plugins/plugins/modulay` | Modulation | Full panel (multi-mode) |
| 12 | `https://ca9.eu/lv2/bolliedelay` | Delay | Menu widget (3 knobs) |
| 12 | `http://guitarix.sourceforge.net/plugins/gx_amp#GUITARIX` | Amp sim | Full panel (amp head) |
| 11 | `http://moddevices.com/plugins/tap/reverb` | Reverb | Full panel (decay/mix/tone) |
| 9 | `http://distrho.sf.net/plugins/MVerb` | Reverb | Full panel (decay/size/mix) |
| 9 | `http://rakarrack.sourceforge.net/effects.html#chor` | Modulation | Menu widget |
| 9 | `http://guitarix.sourceforge.net/plugins/gx_luna_#_luna_` | Preamp | Full panel |
| 8 | `http://guitarix.sourceforge.net/plugins/gx_sd1sim_#_sd1sim_` | OD | Menu widget |
| 7 | `http://rakarrack.sourceforge.net/effects.html#eqp` | EQ | Full panel (parametric) |
| 7 | `http://moddevices.com/plugins/mod-devel/mixer` | Utility | Menu widget |
| 7 | `http://moddevices.com/plugins/tap/echo` | Delay | Menu widget |
| 6 | `http://moddevices.com/plugins/tap/tremolo` | Modulation | Menu widget |
| 6 | `http://moddevices.com/plugins/tap/chorusflanger` | Modulation | Menu widget |
| 6 | `http://moddevices.com/plugins/caps/PlateX2` | Reverb | Menu widget |
| 6 | `http://moddevices.com/plugins/caps/AmpVTS` | Amp sim | Full panel |
| 6 | `http://guitarix.sourceforge.net/plugins/gxautowah#wah` | Filter | Menu widget |
| 6 | `http://guitarix.sourceforge.net/plugins/gx_switchless_wah#wah` | Filter | Menu widget |
| 6 | `https://github.com/brummer10/CollisionDrive` | OD | Menu widget |
| 6 | `http://rakarrack.sourceforge.net/effects.html#StompBox_fuzz` | Fuzz | Menu widget |
| 5 | `http://guitarix.sourceforge.net/plugins/gx_bottlerocket_#_bottlerocket_` | Boost | Menu widget |
| 5 | `https://github.com/brummer10/Rumor` | Modulation | Menu widget |
| 5 | `http://plugin.org.uk/swh-plugins/valve` | Saturation | Menu widget |
| 5 | `http://invadarecords.com/plugins/lv2/compressor/mono` | Dynamics | Full panel (compressor) |
| 4 | `urn:zamaudio:ZamComp` | Dynamics | Full panel (compressor) |
| 3 | `http://moddevices.com/plugins/mod-devel/LowPassFilter` | Filter | Menu widget |
| 3 | `http://www.openavproductions.com/artyfx#roomy` | Reverb | Menu widget |
| 3 | `http://moddevices.com/plugins/tap/reflector` | Reverb | Menu widget |
| 3 | `http://moddevices.com/plugins/tap/doubler` | Modulation | Menu widget |
| 3 | `http://moddevices.com/plugins/sooperlooper` | Looper | Full panel (special) |
| 3 | `http://moddevices.com/plugins/mod-devel/SuperWhammy` | Pitch | Menu widget |
| 3 | `http://moddevices.com/plugins/mod-devel/DS1` | Distortion | Menu widget |
| 3 | `http://moddevices.com/plugins/mod-devel/Drop` | Pitch | Menu widget |
| 3 | `http://moddevices.com/plugins/mod-devel/2Voices` | Pitch | Menu widget |
| 3 | `http://moddevices.com/plugins/mda/Dynamics` | Dynamics | Menu widget |
| 2 | `urn:distrho:a-reverb` | Reverb | Full panel |
| 2 | `http://moddevices.com/plugins/caps/Plate` | Reverb | Menu widget |
| 2 | `http://moddevices.com/plugins/caps/PhaserII` | Modulation | Menu widget |
| 2 | `http://moddevices.com/plugins/caps/Compress` | Dynamics | Menu widget |
| 2 | `http://invadarecords.com/plugins/lv2/phaser/mono` | Modulation | Menu widget |
| 2 | `http://www.openavproductions.com/artyfx#kuiza` | Distortion | Menu widget |
| 2 | `http://moddevices.com/plugins/mod-devel/HighPassFilter` | Filter | Menu widget |
| 2 | `http://moddevices.com/plugins/caps/ChorusI` | Modulation | Menu widget |
| 2 | `http://VeJaPlugins.com/plugins/Release/cabsim` | Cab sim | Menu widget |
| 1 | `urn:distrho:a-comp` | Dynamics | Full panel (compressor) |
| 1 | `http://calf.sourceforge.net/plugins/MonoCompressor` | Dynamics | Full panel (compressor) |
| 1 | `http://moddevices.com/plugins/mod-devel/System-Compressor` | Dynamics | Full panel (compressor) |
| 1 | `http://moddevices.com/plugins/mod-devel/Advanced-Compressor` | Dynamics | Full panel (compressor) |
| 1 | `http://moddevices.com/plugins/mda/Ambience` | Reverb | Menu widget |
| 1 | `http://moddevices.com/plugins/mda/Stereo` | Utility | Menu widget |
| 1 | `http://moddevices.com/plugins/mda/EPiano` | Instrument | — |
| 1 | `http://moddevices.com/plugins/mda/Degrade` | Distortion | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_DOP250_#_DOP250_` | Distortion | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_guvnor_#_guvnor_` | Distortion | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_voodoo_#_voodoo_` | Distortion | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_digital_delay_#_digital_delay_` | Delay | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_digital_delay_st_#_digital_delay_st_` | Delay | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_fuzzfacefm_#_fuzzfacefm_` | Fuzz | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_liquiddrive_#_liquiddrive_` | OD | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_MicroAmp_#_MicroAmp_` | Amp sim | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gx_oc_2_#_oc_2_` | Octave | Menu widget |
| 1 | `http://guitarix.sourceforge.net/plugins/gxts9#ts9sim` | OD | Menu widget |
| 1 | `http://remaincalm.org/plugins/avocado` | Reverb | Menu widget |
| 1 | `http://remaincalm.org/plugins/floaty` | Reverb | Menu widget |
| 1 | `http://remaincalm.org/plugins/mud` | Distortion | Menu widget |
| 1 | `http://remaincalm.org/plugins/paranoia` | Distortion | Menu widget |
| 1 | `http://devcurmudgeon.com/alo` | Reverb | Menu widget |
| 1 | `http://gareus.org/oss/lv2/modmeter` | Utility | — |
| 1 | `http://jpcima.sdf1.org/lv2/string-machine` | Instrument | — |
| 1 | `http://kxstudio.linuxaudio.org/plugins/FluidPlug_Black_Pearl_4A` | Instrument | — |
| 1 | `https://github.com/vallsv/midi-display.lv2` | Utility | — |
| 1 | `http://rakarrack.sourceforge.net/effects.html#delm` | Delay | Menu widget |
| 1 | `http://kxstudio.sf.net/carla/plugins/audiofile` | Utility | — |
