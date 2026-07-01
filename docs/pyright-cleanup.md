# Pyright / Ruff cleanup — remaining work & how to fix it

Goal: **zero pyright errors** in the in-scope trees **without adding any new inline
`# type: ignore` / `# pyright: ignore`** (existing 57 stay), no new `getattr`/`hasattr`
(banned), dependencies remain a DAG. Ruff issues get cleaned up in every file we touch
(the user asked for star-import removal specifically, plus the cheap wins).

## Status

| | count |
|---|---|
| pyright errors (whole repo) | **127** (down from 356) |
| pyright errors, in-scope only | **114** |
| pyright errors, out-of-scope (`tools/ ui/ plugins/ util/`) | 13 |
| pyright warnings (`reportMissingModuleSource`, hardware imports) | 12 |
| ruff findings | 86 (36 auto-fixable) |

**In scope:** `pistomp/`, `modalapi/`, `uilib/`, `common/`, `blend/`, `tests/`,
`emulator/`, root `modalapistomp.py`.
**Out of scope (leave):** `tools/`, `ui/`, `plugins/`, `util/`.

Done so far: G1 (module-as-type in `parameterdialog`), G2 (LCD DI + deletion of the
vestigial `pistomp.lcd.Lcd` / dead `pistomp.lcdbase.Lcdbase`), G3 (asserting `@property`
for `handler.current` / `ws_bridge`), G4 (deleted `pistomp/testhost.py`, dropped the
`"test"` host, added no-op `set_tuner_source_spec` to the `Handler` base).

---

## Guiding principles (from steering)

1. **Fix at the type-declaration source**, not the call site — one annotation fix
   cascades and clears many errors.
2. **Prefer real dependency injection**; use an asserting `@property` with a private
   `_x` backing field only for genuine lifecycle/runtime state (the pattern already
   used for `current`, `ws_bridge`, `lcd`).
3. **Delete dead/vestigial code** rather than annotate it into compliance. Understand
   what an abstraction is *for* before keeping it (this is how `pistomp.lcd.Lcd`,
   `lcdbase.py`, and `testhost.py` went away).
4. **No new ignores, no getattr/hasattr.** Narrow with `isinstance` / assert / early
   return.
5. Fixing overrides means **aligning the signature to the base** (param names, keyword
   vs positional, return type) — not loosening the base with `*args/**kwargs` unless
   the base genuinely has no consumers (in which case, question whether the base method
   should exist).

---

## pyright, by root cause

### P1 — Read-only `@property` on base, assigned in subclass (~18: "Cannot assign to attribute")

`Handler.hardware` is a getter-only `@property` (mirrors the pre-existing `current` /
`ws_bridge` shape) but `Generichost.__init__`/`add_hardware` do `self.hardware = ...`,
and the emulator hardware base assigns `self.relay`.

**Fix (source):** extend the same asserting-property idiom to `hardware` on the base —
`_hardware: Hardware | None` backing field + getter that asserts + setter. Then
`Generichost` and emulator subclasses assign through the setter for free. This is the
DAG-friendly fix and matches `current`/`ws_bridge` exactly.

The **test** occurrences of this message (`sink`, `wifi_manager`, `banks_file_timestamp`,
`flush_callback`, `bkgnd_color`, `refresh`, `return_value` on `MethodType`) are a
different flavour — see P6.

### P2 — Incompatible method overrides (~24: "overrides class … in an incompatible manner" / "overrides symbol of same name")

Split into three sub-cases; fix each **against its declared base**:

- **Param-name / positional-vs-keyword drift** — rename the override's params to match
  the base (e.g. `clip`/`local_clip`, `ctx`/`wm`, `symbol`/`param_name`,
  `value`/`bypass`). Pure rename, no behaviour change.
- **Return-type drift** — align the annotation (base `bool`/`None` vs override; the
  `get_display_info` returning `dict` vs `AnalogDisplayInfo` case in `emulator/controls.py`).
- **`footswitch.py:33` `id` overrides `Controller.id`; emulator `recovery_available`** —
  these override a symbol with an incompatible declared type. Align the type, or if the
  base declaration is wrong/too narrow, fix it at the base.

Concentrated in `emulator/{stubs,mod,modhandler,controls,hardware_v1,hardware_base}.py`,
`pistomp/{footswitch,iqaudiocodec,pistomp}.py`. The emulator `system_menu_reboot` /
`system_menu_reload` / audiocard-stub overrides are the bulk — the emulator shims drifted
from the real classes they stand in for; realign the shim signatures.

### P3 — Optional member access (22: `reportOptionalMemberAccess`)

Value is `X | None` at the use site. Ranked fixes: (1) it was never really Optional →
fix the annotation; (2) genuinely Optional but guaranteed at this point → narrow with an
early `if … is None: return` or `assert`; (3) lifecycle state accessed everywhere →
promote to the asserting-`@property` idiom (as with `current`). **Never** an ignore.
Check whether each is already downstream of a fixed property before hand-editing —
several will evaporate once P1 lands.

### P4 — Bad argument types (18 "Argument … cannot be assigned" + 6 `reportCallIssue`)

Real nullability/coercion bugs, mostly at boundaries:
- `modalapi/pedalboard.py:216,327` — TTL parse yields `float | int | str | None` handed
  to a `float` param. Coerce/validate at the parse boundary (the TTL reader), not the
  `Parameter` constructor.
- `pistomp/audiocard.py:129/140/151` — `re.search(pattern, str | None)`; guard the
  `None` (subprocess output) before searching.
- `emulator/hardware_base.py`, `emulator/stubs.py:110` — mock/stub types not
  substitutable for the real ones → make the stub actually subclass (or match) the real
  type. Overlaps with P2.

### P5 — `Invalid exception class or object` (5: singleton `raise self.__single`)

`Audiocardfactory`, `Handlerfactory`, `Hardwarefactory`, `Pistomp`, `Pistompcore` all do
`if cls.__single: raise cls.__single` — raising a **stored instance of the class itself**,
not an exception. pyright is correct: this is a latent bug (raising a non-`BaseException`).

**Fix:** these are singleton guards. Raise a real exception —
`raise RuntimeError(f"{cls.__name__} already instantiated")` — instead of raising the
prior instance. Behaviour-equivalent for the "already constructed" guard and actually
valid. (Confirm no caller catches the instance by identity; none should.)

### P6 — Tests assigning to methods / typed attrs (~15, mostly `tests/`)

Two shapes:
- **`return_value` on `MethodType`** (`test_system_menu`, `test_failfast_startup`) —
  test assigns `handler.foo.return_value = …` on a real bound method instead of a Mock.
  Fix the test to wrap the target in `unittest.mock.MagicMock` / use `patch.object`.
- **Assigning to a typed slot the class declares differently** (`sink` on `Footswitch`/
  `EncoderController`/`AnalogMidiControl`, `wifi_manager`, `flush_callback`, custom
  `_SloppyWidget`/`StrobeWidget` attrs) — the test pokes an attribute the type says is
  read-only or another type. Prefer the real setter / constructor arg; if the attribute
  is legitimately settable in production too, fix the declaration at the source (P1).

`test_label.py` (12) and `test_footswitch.py` (5) are the biggest test files — expect a
mix of P3/P4/P6 there.

### P7 — Possibly-unbound (2 in-scope: `reportPossiblyUnboundVariable`)

`pistomp/pistomp.py:126 cfg_fs` and `uilib/glyphs/rounded_rect.py:267 fill_rgb` are
assigned only inside a conditional then read unconditionally. Initialize before the
branch (or restructure so the read is inside the same guard). Real latent bug.

### P8 — Not iterable / not subscriptable / invalid type form (5)

- `reportOptionalIterable` ×3 / `reportOptionalSubscript` — iterate/subscript over an
  `X | None`; guard the `None`.
- `uilib/paint.py:194 reportInvalidTypeForm` "Variable not allowed in type expression" —
  a runtime value is being used where a type annotation is expected. Rewrite the
  annotation to use the actual type (or `TypeAlias`).

### P9 — Hardware-only imports (config-level; **2 errors + 12 warnings**) — task G8

`reportMissingImports: alsaaudio` (+`importlib` attr) and `reportMissingModuleSource`
warnings for `RPi`, `spidev`, `serial`, `adafruit_rgb_display`. These modules exist only
on-device.

**Fix (config-level, per steering — NOT inline):** add minimal `.pyi` stubs under the
already-configured `typings/` `stubPath` for the modules/attributes actually used (a few
symbols each), and/or a scoped `[tool.pyright]` setting. No inline ignores. Note some of
the 12 warnings live in out-of-scope `tools/` — clearing the stub fixes them for free.

---

## ruff, by rule

Clean these up **in files we already touch** for pyright (the user asked for star-import
removal explicitly; the rest are cheap). Run `uv run ruff check --fix` for the 36
auto-fixable, then hand-fix the rest. **Do not** blanket-fix out-of-scope trees.

| rule | count | what | fix |
|---|---|---|---|
| F401 | 31 | unused imports | `--fix` (auto) |
| F403 | 14 | `from X import *` | **explicit imports** — in-scope hit is `uilib/__init__.py` (and the `rtmidi` stub). Enumerate the names actually re-exported. |
| F841 | 12 | unused local var | remove or prefix `_` |
| E722 | 10 | bare `except:` | name the exception (`except Exception:`); note `modalapistomp.py`'s bare `except: raise` went away with the `test` host removal |
| F541 | 4 | f-string w/o placeholders | drop the `f` |
| E731 | 4 | lambda assigned to name | `def` instead |
| E712 | 3 | `== True/False` | `is`/truthiness |
| E401 | 3 | multiple imports on one line | split |
| E741 | 2 | ambiguous name (`l`/`I`/`O`) | rename |
| E711 | 2 | `== None` | `is None` |
| F821 | 1 | undefined `note` (`util/tuner_analyze.py`) | **out of scope** — leave |

F405 (name may be undefined from star import) resolves automatically once the F403 star
imports become explicit.

---

## Suggested order

1. **P5** (5) + **P7** (2) — tiny, self-contained, real bugs, no cascade risk.
2. **P1** (`hardware` property on base) — cascades into P3, unblocks `Generichost`/emulator.
3. **P3** re-measure, then narrow the survivors.
4. **P2** override alignment (biggest single cluster; emulator-heavy).
5. **P4** boundary coercions (`pedalboard.py`, `audiocard.py`).
6. **P6** test fixups.
7. **P8** stragglers.
8. **P9** hardware stubs (config-level).
9. ruff sweep on touched files (`--fix` + explicit star-import expansion).

## Verify (task #8)

- `uv run pyright` → 0 errors in-scope (tools/ui/plugins/util residue acceptable, called
  out explicitly).
- `grep -rn 'type: ignore\|pyright: ignore' --include='*.py'` → **still 57**.
- No new `getattr`/`hasattr`.
- `uv run pytest` green (type edits must not change runtime behaviour; snapshots unaffected).
