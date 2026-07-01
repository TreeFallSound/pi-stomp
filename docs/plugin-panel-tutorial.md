# Building a Plugin Panel: Tutorial

Step-by-step guide for adding a custom UI for an LV2 plugin. For the class
hierarchy, glyph ecosystem, encoder conventions, and UI constraints referenced
below, see `plugin-customization-guide.md`.

## Step 0: Discover the Plugin's Port Symbols

Use the on-device/cache inspection commands in `CLAUDE.md` ("Finding LV2
Plugin Port Symbols") to get the `lv2:symbol` values, ranges, and URI. Skip
audio ports and `:bypass` — the framework handles those.

---

## Step 1: Pick a Presentation

```
How many parameters, and are they band-based (freq/gain/Q)?

  Band-based, 3+ bands           → ParametricEqPanel or GraphicEqPanel
  Compressor (thr/rat/mak[/kn])  → CompressorPanel subclass
  Up to ~10 flat parameters      → MultibandWindow subclass
  Needs a bespoke visualization  → FullscreenPluginPanel subclass
  Read-only display              → FullscreenPluginPanel[None]
  Non-parameter workflow (NAM)   → bare FullscreenPanel, not PluginPanel
```

Create the directory and files:

```bash
mkdir -p plugins/<name>/
```

- `__init__.py` — registration (always required)
- `panel.py` — panel/window class
- `band_spec.py` — only for EQ panels

---

## Step 2A: Compressor (`CompressorPanel`)

Covers any plugin with Threshold/Ratio/Makeup(/Knee). Gets the arc column,
gain-reduction reticule graph, and live GR meter for free.

`plugins/<name>/panel.py`:
```python
from plugins.compressor_base import CompressorPanel, CompressorSpec

class MyCompPanel(CompressorPanel):
    SPEC = CompressorSpec(thr_sym="thresh", rat_sym="ratio", mak_sym="makeup", kn_sym="knee")
```

`plugins/<name>/__init__.py`:
```python
from plugins.customization import PluginCustomization, register
from plugins.<name>.panel import MyCompPanel

register(
    "urn:my-plugin-uri",
    customization=PluginCustomization(panel_cls=MyCompPanel, display_name="My Compressor"),
)
```

Omit `kn_sym` if the plugin has no knee control. If the audio ports aren't
named `lv2_audio_in_1`/`lv2_audio_out_1`, pass `in_audio_sym`/`out_audio_sym`.

---

## Step 2B: MultibandWindow (flat parameter grid)

For 1-10 parameters that don't need a full-screen visualization — a compact
card with one arc ring per parameter.

`plugins/<name>/panel.py` (or `window.py`, matching existing plugins):
```python
from plugins.multiband_menu import MultibandWindow, ParamSlot

class MyWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("drive", "Drive", (255, 180, 80)),
            ParamSlot("tone", "Tone", (130, 220, 110)),
            ParamSlot("level", "Level", (200, 200, 200)),
        ]
```

`plugins/<name>/__init__.py`:
```python
from plugins.customization import PluginCustomization, register
from plugins.<name>.panel import MyWindow

register(
    "urn:my-plugin-uri",
    customization=PluginCustomization(panel_cls=MyWindow, display_name="My Plugin"),
)
```

`ParamSlot(symbol, label, color, display_fn=None)`; add `display_fn` (a
`Callable[[float], str]`) for units like Hz. Layout, Tweak1 editing, and
LONG_CLICK reset are handled by the base.

---

## Step 2C: Parametric or Graphic EQ

`plugins/<name>/band_spec.py`:
```python
from plugins.eq.band_spec import BandSpec

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("L", "shelf", "enable_l", "freq_l", "q_l", "gain_l", "low",
             20.0, 20000.0, 0.1, 4.0, color=(255, 180, 80)),
    BandSpec("1", "peak", "enable_1", "freq_1", "q_1", "gain_1", None,
             20.0, 20000.0, 0.1, 4.0, color=(255, 230, 80)),
    BandSpec("H", "shelf", "enable_h", "freq_h", "q_h", "gain_h", "high",
             20.0, 20000.0, 0.1, 4.0, color=(210, 130, 230)),
)
```

`plugins/<name>/panel.py`:
```python
from plugins.eq.parametric import ParametricEqPanel
from plugins.<name>.band_spec import BAND_SPECS

class MyEqPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
```

For a graphic (bar-style) EQ, use `GraphicBandSpec` + `GraphicEqPanel`
instead:
```python
from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette

_BANDS = [("100Hz", 100.0, "band1"), ("200Hz", 200.0, "band2"), ...]
BAND_SPECS = tuple(
    GraphicBandSpec(name=n, freq_hz=f, gain_sym=s, color=c)
    for (n, f, s), c in zip(_BANDS, _graphic_palette(len(_BANDS)))
)
```
```python
from plugins.eq.graphic import GraphicEqPanel
from plugins.<name>.band_spec import BAND_SPECS

class MyGraphicEqPanel(GraphicEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
```

Registration is the same `PluginCustomization(panel_cls=..., display_name=...)`
pattern as above.

---

## Step 2D: Bespoke Fullscreen Panel

Only reach for this when the compressor/window/EQ bases don't fit (e.g. a
reverb with a custom decay/size/mix layout, or a read-only viewer).

```python
from dataclasses import dataclass
from plugins.fullscreen import FullscreenPluginPanel
from uilib.box import Box
from uilib.config import Config

@dataclass(frozen=True)
class MyState:
    param1: float
    param2: float

class MyPanel(FullscreenPluginPanel[MyState]):

    def snapshot_state(self) -> MyState:
        params = self.plugin.parameters
        return MyState(
            param1=float(params.get("symbol1", ...).value or 0.0),
            param2=float(params.get("symbol2", ...).value or 0.0),
        )

    def apply_state(self, state: MyState) -> None:
        self._state = state
        self._widget1.set_value(state.param1)
        self._widget2.set_value(state.param2)

    def build_widgets(self) -> None:
        self._state = self.snapshot_state()
        font = Config().get_font("default")
        self._widget1 = MyParamWidget(box=Box.xywh(10, 10, 140, 180), label="Param 1",
                                       min_val=0.0, max_val=1.0, font=font, parent=self)
        self._widget2 = MyParamWidget(box=Box.xywh(170, 10, 140, 180), label="Param 2",
                                       min_val=0.0, max_val=100.0, font=font, parent=self)
        self.add_sel_widget(self._widget1)
        self.add_sel_widget(self._widget2)

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id == 1:
            new_val = max(0.0, min(1.0, self._state.param1 + rotations * 0.01))
            self.set_param("symbol1", new_val)
            self._state = MyState(param1=new_val, param2=self._state.param2)
            self._widget1.set_value(new_val)
            return True
        return False
```

For a read-only panel with no editable state, use `FullscreenPluginPanel[None]`
(see `plugins/notes/panel.py`) and set `intercept_shortpress=True` in the
registration if a short-press should open it instead of toggling bypass.

---

## Step 3: Register in `plugins/__init__.py`

```python
import plugins.<name>  # noqa: F401
```

Without this import, `lookup()` returns a blank `PluginCustomization()` no
matter what `plugins/<name>/__init__.py` registers.

---

## Step 4: Test

```bash
uv run pytest tests/v3/test_plugin_panel_bypass_refresh.py
uv run pytest tests/v3/test_eq_panel.py            # if EQ
uv run pytest tests/v3/test_acomp_panel.py          # compressor-family example
```

Create `tests/v3/test_<name>_panel.py` following an existing example above,
and `uv run pytest --snapshot-update` to accept new/changed LCD baselines.

---

## Common Pitfalls

1. **URI mismatch** — must match `manifest.ttl` exactly (trailing `#` or not).
2. **Port symbol mismatch** — use the `lv2:symbol`, not `lv2:name` or port index.
3. **Forgetting `super().tick()`** — if you override `tick()`, the param queue
   never drains without it.
4. **Bare `pygame.Surface((w,h))`** — see the Surface Formats note in
   `plugin-customization-guide.md`'s UI Constraints table.
5. **Not importing in `plugins/__init__.py`** — registration never runs.
