# `Symbol` is not a type, and `Any` was hiding it

Surfaced while fixing a badge regression on `feat/parameter-menu`. Done on
`refactor/input-sink-transport`, so the whole input-contexts stack inherits it.

## The confusion

`Parameter` has both a `name` (the LV2 shortName, e.g. `"Threshold"`) and a
`symbol` (the port symbol, e.g. `"THRES"`). `ParamEffect.symbol`, `edit_symbol()`,
and the `plugin.parameters` dict were all keyed by **symbol**, and nothing
enforced it. Two producers were passing `name` where a symbol belongs:

```python
ParamEffect(plugin=plugin, symbol=param.name)   # controller_manager.py, 2 sites
effect.symbol == param.name                     # lcd320x240.py badge helpers
```

The visible symptom was a missing badge on the Bypass button. The latent one was
worse: a param whose shortName diverges from its symbol fails to **dispatch**,
not just to badge.

### How often do they actually diverge?

Measured against the live device — all 663 plugins, 5913 control-input ports,
via the same `/effect/get` call `Pedalboard.get_plugin_data` makes:

| | |
|---|---|
| ports where `shortName != symbol` | **4902 / 5913 (83%)** |
| ports missing `ranges.default` | 0 |
| ports missing `minimum` or `maximum` | 0 |
| ports with no `shortName` | 0 |
| ports whose `units` carry no symbol/label | 4610 |
| `enumeration` ports with no `scalePoints` | 1 |

Divergence is the **norm**, not the exception (`THRES`/`Threshold`,
`PREGAIN`/`INPUT`, `gain_l`/`Gain L`). `:bypass` was not a special case that
slipped through — it was merely the first symbol a panel happened to pass
`param.name` for. The other 4901 were waiting.

## Why pyright couldn't catch it

**`common/util.DICT_GET` returned `Any`.** Every `Parameter` field was built
through it, so `param.name` and `param.symbol` were `Any` — they satisfied
*every* parameter type in the codebase. `ParamEffect(symbol=param.name)`
typechecked for the same reason `ParamEffect(symbol=param.minimum)` would have.
"pyright zero" was measuring nothing there.

**And even fully annotated, `str` vs `str` is indistinguishable.** A symbol and a
shortName are different domains wearing the same type.

This is the failure the `getattr`/`hasattr` ban aims at, in a different costume:
when a value's type is `Any`, the checker isn't checking.

## What landed

1. **`PortInfo`** (`common/parameter.py`) — a TypedDict for one row of an LV2
   plugin's control-input ports, as mod-ui reports it, with `Ranges`, `Units`,
   `ScalePoint`. `Parameter.__init__` takes it and validates: no symbol is a
   hard `ValueError`, not a `None` that surfaces three screens later.

2. **`Symbol = NewType("Symbol", str)`** — applied to `ParamEffect.symbol`, the
   `plugin.parameters` key, `pedalboard_snapshot`, and the panel plumbing
   (`edit_symbol`, `set_param`, `param_roles`, the band/compressor spec tables).
   `symbol=param.name` is now a pyright error at the point of the mistake.

   `Symbol` is **not** "LV2 port symbol" — it is *the key that identifies a
   `Parameter`*. That covers real LV2 ports, ALSA mixer controls (`"MASTER"`),
   and ids we synthesise (`"external_1_7"`). What it is never is a shortName.

3. **`blend/types.py` had a second, fake `Symbol`** — `Symbol: TypeAlias = str`,
   documentation-only, enforcing nothing. It now re-exports the real NewType, so
   blend's `dict[InstanceId, dict[Symbol, ParamData]]` is genuinely checked.

4. **DICT_GET / Token are gone from the Parameter blast radius** —
   `common/parameter.py`, `modalapi/pedalboard.py`, `connections.py`,
   `plugin.py`. Ten now-dead LV2 keys were dropped from `common/token.py`; the
   config and direction keys stay. The ~60 hardware/wifi/LCD `DICT_GET` sites are
   untouched and remain a follow-up.

5. **`Symbol` reaches the selection and outbound paths too.** The first pass
   stopped at `plugin.parameters` and the panels, which left three surfaces
   still typed `str` — each *laundering* a `Symbol` its caller already held:

   - `Selectable.symbol_for() -> str | None`, the NAV selection path. Every
     implementation already returned a real `Symbol` (`band.gain_sym`,
     `self.symbol`); the protocol widened it back to `str`, and `dispatch.fire`
     then re-asserted it with `Symbol(symbol)`. A cast that exists only because
     a signature threw the type away is the very hole the NewType is for.
   - `blend/parameter_setter.send_parameter`, which cast `Symbol(symbol)` twice
     in one body — once for the dedup key, once for the bridge call.
   - `Handler.is_symbol_locked`, `AsyncWebSocketBridge.send_parameter`, and
     NAM's `edit_symbol` — the last of which *widened* the base class's param
     back to `str` in an override. Legal contravariance, so pyright never said a
     word, and the hole reopened inside NAM's whole capture flow.

## Where a cast is still legitimate

`Symbol(...)` should appear only at **ingress**, never mid-graph. After this,
every remaining production cast is one of:

| site | why |
|---|---|
| `Parameter.__init__` | raw mod-ui JSON (`PortInfo.symbol` stays `str`) |
| `modhandler` param_set handling | raw inbound WS parse (`ParamSetMessage.symbol` stays `str`) |
| `modhandler` volume bind | ALSA mixer control name off the audio card |
| `controller_manager`, `hardware` | ids we synthesise (`external_1_7`) |

Deliberately **not** a `Symbol`: `CompressorSpec.in_audio_sym` /
`out_audio_sym`. Those are JACK port names (`"lv2_audio_in_1"`), not keys of a
`Parameter` — a different domain that happens to share the word "symbol".

## Bugs it surfaced

- **`modhandler._bind_volume_encoder` never guarded `audiocard.MASTER`,** which
  is `None` on the base class and on hifiberry. It was building a `Parameter`
  with `symbol=None` and binding an encoder to it. Now guarded.

- **The `float` annotations were lying, but not about mod-ui.** `minimum`,
  `maximum` and `default` are never absent from a real port (0/5913) — mod-ui
  normalises the TTL. The `None`s came entirely from the four `PortInfo`s *we*
  synthesise (bypass, volume, VU calibration, external MIDI). So `default` is
  now plain `float` (falling back to `minimum`), `value` is plain `float`, and
  the ~15 defensive `p.value is None` / `p.default is None` guards scattered
  through the panels were dead code and are gone.

`unit_symbol` / `unit_label` stay `str | None` and `enum_values` stays possibly
empty — the table above shows both are load-bearing.
