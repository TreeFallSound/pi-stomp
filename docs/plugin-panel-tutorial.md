# Building a Plugin Panel: Tutorial

This tutorial covers the two ways to add a custom UI for an LV2 plugin:
a **fullscreen panel** (for complex visualizations) and a **menu widget**
(for 2-8 parameter arc-ring controls). Pick the approach that fits your
plugin's parameter count and visual needs.

---

## Step 0: Discover the Plugin's Port Symbols

Before writing any code, find the LV2 port symbols. On the device:

```bash
# Find the plugin bundle
ls ~/.lv2/ | grep -i <plugin-name>

# Read the manifest to find the TTL file
cat ~/.lv2/<name>.lv2/manifest.ttl

# Read the plugin TTL for port definitions
cat ~/.lv2/<name>.lv2/<name>.ttl | grep -E "lv2:symbol|lv2:name|lv2:minimum|lv2:maximum|lv2:default"
```

The `lv2:symbol` values are what you'll use in `set_param()` and in
`BandSpec`/`ParamSlot` definitions. Skip audio ports and `:bypass` —
those are handled by the framework.

---

## Step 1: Create the Plugin Directory

```bash
mkdir -p plugins/<name>/
```

You'll need at minimum:
- `__init__.py` — registration
- `panel.py` — the panel class (for fullscreen panels)
- `menu_widget.py` — the widget class (for menu widgets)
- `band_spec.py` — band definitions (for EQ panels)

---

## Step 2A: Fullscreen Panel (e.g. a Reverb)

### Registration (`plugins/<name>/__init__.py`)

```python
from plugins.customization import PluginCustomization, register
from plugins.<name>.panel import MyPanel

register(
    "urn:my-plugin-uri",
    customization=PluginCustomization(
        panel_cls=MyPanel,
        display_name="My Plugin",
    ),
)
```

### Panel (`plugins/<name>/panel.py`)

```python
from __future__ import annotations

from typing import Optional

from plugins.base import PluginPanel
from uilib.box import Box
from uilib.config import Config
from uilib.misc import get_text_size
from uilib.widget import Widget
from uilib.text import Button

_W = 320
_H = 240

# ── layout constants ──────────────────────────────────────────────────────

CONTENT_Y0 = 0
CONTENT_Y1 = 210  # chrome row starts at 210

# ── state type ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MyState:
    param1: float
    param2: float

# ── panel ────────────────────────────────────────────────────────────────

class MyPanel(PluginPanel[MyState]):

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
        cfg = Config()
        font = cfg.get_font("default")

        # Create your custom widgets here
        self._widget1 = MyParamWidget(
            box=Box.xywh(10, 10, 140, 180),
            label="Param 1",
            min_val=0.0, max_val=1.0,
            font=font, parent=self,
        )
        self._widget2 = MyParamWidget(
            box=Box.xywh(170, 10, 140, 180),
            label="Param 2",
            min_val=0.0, max_val=100.0,
            font=font, parent=self,
        )

        # Register selectable widgets for Nav cycling
        self.add_sel_widget(self._widget1)
        self.add_sel_widget(self._widget2)

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id == 1:
            # Tweak1 adjusts param1
            new_val = self._state.param1 + rotations * 0.01
            new_val = max(0.0, min(1.0, new_val))
            self.set_param("symbol1", new_val)
            self._state = MyState(param1=new_val, param2=self._state.param2)
            self._widget1.set_value(new_val)
            return True
        elif encoder_id == 2:
            # Tweak2 adjusts param2
            new_val = self._state.param2 + rotations * 0.5
            new_val = max(0.0, min(100.0, new_val))
            self.set_param("symbol2", new_val)
            self._state = MyState(param1=self._state.param1, param2=new_val)
            self._widget2.set_value(new_val)
            return True
        return False

    def tick(self) -> None:
        # Check bypass state changes, then drain param queue
        super().tick()
```

### Custom Widget (`plugins/<name>/panel.py` or separate file)

```python
class MyParamWidget(Widget):
    """A simple value display with label."""

    def __init__(self, box, label, min_val, max_val, font, parent):
        super().__init__(box=box, bkgnd_color=(0, 0, 0), parent=parent)
        self._label = label
        self._min = min_val
        self._max = max_val
        self._font = font
        self._value = min_val

    def set_value(self, value: float) -> None:
        self._value = max(self._min, min(self._max, value))
        self.refresh()

    def _draw(self, ctx) -> None:
        # Draw label
        ctx.draw_text((ctx.width // 2, 10), self._label,
                      fill=(200, 200, 200), font=self._font, anchor="mt")
        # Draw value
        text = f"{self._value:.1f}"
        ctx.draw_text((ctx.width // 2, ctx.height // 2), text,
                      fill=(255, 255, 255), font=self._font, anchor="mm")
```

---

## Step 2B: Menu Widget (e.g. a 3-knob Distortion)

### Registration (`plugins/<name>/__init__.py`)

```python
from plugins.customization import PluginCustomization, register
from plugins.<name>.menu_widget import MyMenuWidget

register(
    "urn:my-plugin-uri",
    customization=PluginCustomization(
        menu_widget_cls=MyMenuWidget,
        display_name="My Plugin",
    ),
)
```

### Menu Widget (`plugins/<name>/menu_widget.py`)

```python
from plugins.multiband_menu import CustomMenuWidget, ParamSlot

class MyMenuWidget(CustomMenuWidget):
    def build_slots(self):
        return [
            ParamSlot("drive", "Drive", (255, 180, 80)),
            ParamSlot("tone", "Tone", (130, 220, 110)),
            ParamSlot("level", "Level", (200, 200, 200)),
        ]
```

That's it. The `CustomMenuWidget` base handles:
- Layout (1 row of 3 in this case)
- Arc ring rendering with value/label
- Tweak1 encoder editing
- CLICK (no-op) and LONG_CLICK (reset to snapshot)

---

## Step 2C: Parametric EQ Panel (e.g. a new EQ)

### Registration (`plugins/<name>/__init__.py`)

```python
from plugins.customization import PluginCustomization, register
from plugins.<name>.panel import MyEqPanel

register(
    "urn:my-eq-uri",
    customization=PluginCustomization(
        panel_cls=MyEqPanel,
        display_name="My EQ",
    ),
)
```

### Band Spec (`plugins/<name>/band_spec.py`)

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

### Panel (`plugins/<name>/panel.py`)

```python
from plugins.eq.parametric import ParametricEqPanel
from plugins.<name>.band_spec import BAND_SPECS

class MyEqPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
```

That's it. The `ParametricEqPanel` base handles:
- Frequency-response curve rendering (320px wide, 20Hz-20kHz log scale)
- Band node circles with selection halo
- Tweak1 = gain, Tweak2 = frequency, Tweak3 = Q
- Readout bar with name/freq/Q/gain
- Band enable toggle (CLICK) and reset (LONG_CLICK)

---

## Step 2D: Graphic EQ Panel (e.g. a new graphic EQ)

Same pattern as parametric, but use `GraphicEqPanel` and `GraphicBandSpec`:

### Band Spec

```python
from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette

_BANDS = [
    ("100Hz", 100.0, "band1"),
    ("200Hz", 200.0, "band2"),
    ("400Hz", 400.0, "band3"),
    ("800Hz", 800.0, "band4"),
    ("1.6k", 1600.0, "band5"),
    ("3.2k", 3200.0, "band6"),
    ("6.4k", 6400.0, "band7"),
]

BAND_SPECS = tuple(
    GraphicBandSpec(name=n, freq_hz=f, gain_sym=s, color=c)
    for (n, f, s), c in zip(_BANDS, _graphic_palette(len(_BANDS)))
)
```

### Panel

```python
from plugins.eq.graphic import GraphicEqPanel
from plugins.<name>.band_spec import BAND_SPECS

class MyGraphicEqPanel(GraphicEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
```

---

## Step 3: Register in `plugins/__init__.py`

Add your import to the list:

```python
import plugins.<name>  # noqa: F401
```

---

## Step 4: Test

```bash
uv run pytest tests/test_plugin_panels.py
uv run pytest tests/v3/test_eq_panel.py  # if EQ
```

For snapshot tests, create `tests/v3/test_<name>_panel.py` following the
pattern in `test_eq_panel.py` or `test_nam_panel.py`.

---

## Decision Flowchart

```
How many parameters does the plugin have?

  1-3 params
    └─ Is it a simple gain/level/tone?
         ├─ Yes → Menu widget (CustomMenuWidget)
         └─ No  → Fullscreen panel (PluginPanel)

  4-8 params
    └─ Are they band-based (freq/gain/Q)?
         ├─ Yes → Parametric EQ (ParametricEqPanel)
         └─ No  → Menu widget (CustomMenuWidget)

  8+ params
    └─ Are they band-based?
         ├─ Yes → Graphic EQ (GraphicEqPanel) or Parametric EQ
         └─ No  → Fullscreen panel (PluginPanel)

  Special cases:
    ├─ Read-only display (notes, meters) → PluginPanel[None]
    ├─ Non-parameter workflow (NAM capture) → FullscreenPanel (not PluginPanel)
    └─ Multi-instance state (model files, text) → extra_data_fn
```

---

## Common Pitfalls

1. **URI mismatch** — The URI in `register()` must match the plugin's
   `manifest.ttl` exactly. Check for trailing `#` or missing `#`.

2. **Port symbol mismatch** — The `lv2:symbol` in the plugin TTL is what
   you use in `set_param()`. Not the `lv2:name`. Not the port index.

3. **Forgetting `super().tick()`** — If you override `tick()`, call
   `super().tick()` or the param queue never drains.

4. **Bare `pygame.Surface((w,h))`** — Always specify `SRCALPHA` for alpha
   surfaces, or `depth=32, masks=(0xFF0000, 0xFF00, 0xFF, 0)` for opaque
   RGB. Bare surfaces inherit the display format and break compositing.

5. **Not registering in `plugins/__init__.py`** — The import triggers
   registration. Without it, `lookup()` returns `PluginCustomization()`.
