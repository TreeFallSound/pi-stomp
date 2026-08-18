# Padding vs margin: the stance

We had six names for two ideas (`_ARC_MARGIN`, `_LABEL_GAP`, `_LINE_GAP`,
`h_margin`/`v_margin`, `BTN_GAP`, `_CONTENT_PAD`) and therefore no rule to appeal to
when spacing broke. Each break got fixed by nudging one magic number in one widget.
This is the rule to appeal to instead.

## The bug that forced it

`ArcDialWidget._cy()` centred **the ring** in the box and let the label hang out of
flow above it:

```python
center = self.box.height // 2
return max(center, half + _LABEL_GAP + lh)   # label_pos == "top"
```

The label only eats into the top half, so the bottom always carried
`_LABEL_GAP + label_h` more slack than the top. In a roomy box (Tap Reverb, GX
Cabinet) that asymmetry is invisible. In a tight box (a CAPS Noisegate slot) the top
slack hit zero, the `max()` clamped, and the label clipped under the 2px selection
reticule — while the bottom of the box sat empty.

The roomy panels were never correct. They were padded.

## The rules

1. **Margin is outside the box; padding is inside it.** The box is the layout unit.
   The *parent* owns space between boxes (`gap`); the *widget* owns space inside its
   own box (`pad`). A widget never draws outside its box, and never draws in its own
   padding.

2. **The selection reticule lives in the padding.** `sel_width` is an *inset* border,
   so `pad >= sel_width` is an invariant for any selectable widget — not a per-widget
   nudge. Without this rule, content that reaches the box edge gets painted over the
   moment it is selected, and we rediscover it once per widget forever.

3. **A widget centres its content block, not one child of it.** If it has out-of-flow
   decoration (a label above a ring, a badge in a cutout), the block *including* that
   decoration is what gets centred.

## Status

Rules **2 and 3 are implemented** in `ArcDialWidget._cy()` and `dial_box_size()`:
the dial now centres `label + gap + ring` within `sel_width` of padding at every edge,
and callers laying out a grid of dials size their cells from `dial_box_size()` rather
than from the ring alone.

Rule **1 is not enforced anywhere.** Applying it across `uilib` means: one name for
between-siblings (`gap`), one for inside-box (`pad`), the six-way naming retired, and
`pad >= sel_width` made structural in `Widget` rather than re-derived per widget.
It is a wide diff with wide snapshot churn, which is why it did not ride along with
the parameter-menu migration. Own branch.
