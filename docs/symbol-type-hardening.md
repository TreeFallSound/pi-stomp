# `Symbol` is not a type, and `Any` is hiding it

Surfaced while fixing a badge regression on `feat/parameter-menu`. The instances are
fixed; the class of bug is not. Wants its own branch.

## The confusion

`Parameter` has both a `name` (the LV2 shortName, e.g. `"bypass"`) and a `symbol`
(the port symbol, e.g. `":bypass"`). `ParamEffect.symbol`, `edit_symbol()`, and the
`plugin.parameters` dict are all keyed by **symbol**. Nothing enforces that.

Two producers were passing `name` where a symbol belongs:

```python
ParamEffect(plugin=plugin, symbol=param.name)   # controller_manager.py, 2 sites
effect.symbol == param.name                     # lcd320x240.py badge helpers
```

This works for most LV2 ports — their shortName *happens* to equal their symbol — and
fails for `:bypass`, the one parameter every plugin has. The visible symptom was a
missing badge on the Bypass button. The latent one was worse: any param whose
shortName diverged from its symbol would silently fail to **dispatch**, not just to
badge. Both are fixed (`param.symbol` everywhere), but nothing stops the next one.

## Why pyright can't catch it

Two reasons, stacked.

**`common/util.DICT_GET` returns `Any`.** Every `Parameter` field is built through it,
so `param.name` and `param.symbol` are `Any` — they satisfy *every* parameter type in
the codebase. `ParamEffect(symbol=param.name)` typechecks for the same reason
`ParamEffect(symbol=param.minimum)` would. Note `self.minimum: float = DICT_GET(...)`
is *annotated* `float` and can still hand you `None` at runtime — same laundering,
better disguised. Any field read off `Parameter` is currently unchecked, and "pyright
zero" is measuring nothing there.

**Even fully annotated, `str` vs `str` is indistinguishable.** A symbol and a
shortName are different domains wearing the same type. Annotating alone fixes the
`Any` hole but not the confusion.

This is the failure the `getattr`/`hasattr` ban in CLAUDE.md aims at, in a different
costume: when a value's type is `Any`, the checker isn't checking.

## The fix

1. Annotate `Parameter`'s fields for real (`symbol: str`, `name: str`,
   `minimum: float`, …), **validating** `DICT_GET`'s results rather than assuming
   them.
2. `Symbol = NewType("Symbol", str)`, applied to `ParamEffect.symbol` and the
   `plugin.parameters` dict key.

Then `symbol=param.name` is a hard pyright error at the point of the mistake.

**Blast radius:** `Parameter`, `common/contexts.py`, and every `ParamEffect`
construction site (each plugin panel's `declare_bindings`). Expect step 1 alone to
surface other latent errors that `Any` was absorbing — that is the point, but it means
this cannot be a drive-by change.
