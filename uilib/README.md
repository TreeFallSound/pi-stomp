# Paint system

The UI is a tree of widgets, each widget knowing its own rectangle in its parent's coordinate space. Non-leaf nodes (`ContainerWidget`s) each own a `pygame.Surface` that holds the composite of itself and its descendants. Leaf widgets have no buffer of their own: they draw straight into the nearest ancestor surface. The root of the tree is a `PanelStack`, whose surface is the one pushed to the LCD.

Drawing happens via `do_draw`; a `PaintContext` is passed to each widget's concrete `_draw` method. This context includes

* the (PyGame) surface being drawn into,
* the dirty `clip` rect in surface coords, and
* the current widget's `frame`.

The context manager `PaintContext.painting(frame)` builds a "sub-context" for drawing children. It uses SDL's capability to drop any primitive that strays outside the clip, so drawing methods can treat their own rect as if it were the whole world.

## Virtual painting

A container's surface is usually the same size as its box, but a virtual container can hold a surface taller (or wider) than its viewport. This is currently used for scrollable menus where content might run past the screen extents (we're working with a 320x240 LCD).

The container's `offset` field is the (x, y) of the viewport's top-left within that "tall" surface, while `_viewport_view()` returns a `pygame.Surface` subsurface of the cache at the current offset. For non-virtual containers `viewport == bounds`, so the view is the whole surface; for virtual containers it's a moving window. Either way, the same blit path serves both.

Virtual containers do, however, diverge from the standard path in a couple ways:

1. Their `refresh()` paints into "content" coordinates rather than "physical" ones, though children don't need to care about this because they draw in local coordinates anyhow.

2. `do_draw()` skips the lazy-rebuild path that non-virtual containers use because their cache is maintained externally by `refresh()` and `scroll()`: off-viewport children get a `_dirty` flag so that scrolling lazily paints them as they come into view, without losing previously-painted pixels.

## Caching

Each container caches its composite, keeping track of which regions are pending re-draws via `_dirty_Region: Box | None`. `None` means clean — the surface can be blitted as-is. A Box means that rectangle is stale and the rest of the cache is up-to-date.

When `do_draw` is called on a non-virtual container with a dirty region, it rebuilds only that slice: the `painting(frame)` clip drops everything outside it, and children whose boxes don't intersect the rect are skipped entirely. 

Cache invalidation happens two ways:

The first method `propagate_dirty(clip)` is called after pixels have been written somewhere (e.g. a leaf called `Widget.refresh(box)`). New pixels exist, but every cached composite is stale (for a certain rectangle) up to the tree root. The new "dirty rectangle" is unioned (after coordinate translation) with ancestors' existing `_dirty_rect`s.

The chain terminates at `PanelStack.propagate_dirty`, which is the only `propagate_dirty` that actually does something visible: it composes the stacked panels into the root surface. The LCD push is deferred — the dirty clip is unioned into `_pending_lcd_clip` and flushed as a single `lcd.update()` call by `poll_updates()` (or immediately by `refresh()`). This collapses N `propagate_dirty` calls in one tick into one SPI transfer instead of N. Structural changes (`push_panel`/`pop_panel`) set `_pending_lcd_clip = None` to request a full-screen recompose on the next flush; `propagate_dirty` treats `None` as "full screen already pending" and won't shrink it back to a partial clip.

The second method `_invalidate_cache(box)` is called when a widget is attached or detached from the widget tree; it uses the same logic to mark that area as stale.

## Masking

`RoundedPanel` introduces a per-corner alpha mask. For non-virtual panels the mask is multiplied into the cache once, in the `_finalize_cache()` hook called at the end of every rebuild, so the panel blits out as plain pixels from then on. Virtual panels can't pre-multiply, because the mask applies to different parts of the backing surface (via the viewport): instead, they apply the mask per-blit against a temporary copy of the viewport slice. 

Subclasses define their shape by overriding `_build_shape_mask()`.

## Badges

A badge is a small fixed-size marker glyph — a filled disc with one character
— that any widget can carry in addition to its normal content. `uilib` only
owns how a badge *paints*; it has no opinion on what one means or when a
caller should set one. (pi-Stomp's own use — marking which physical control
edits a widget, sourced from the resolved input-binding table — lives in
`pistomp/input/README.md`, not here.)

`BadgeGlyph` (`uilib/glyphs/badge.py`) is a filled white disc with a black
character baked into the pixels (cached per `(char, radius)`, since the
character can't be tinted at blit time the way a plain alpha-mask glyph can).

`Widget._draw_badge(ctx)` (`uilib/widget.py`) is the **one call site** in the
whole framework — `do_draw` calls it exactly once, right after `_draw`/
outline/selection. The default implementation blits `self._badge`
(set via `set_badge(BadgeGlyph | None)`) at a fixed left-edge, vertically
centered spot. A widget needing a different spot — `ArcDialWidget`
(`uilib/glyphs/arc_dial.py`, centered on the ring's axis opposite the label),
`TextWidget` (`uilib/text.py`, immediately left of its text), `ReadoutBar`
(`plugins/layouts/readout_bar.py`, tracks whichever text is currently
displayed) — overrides `_draw_badge` itself rather than adding a second
paint call: a second call site either double-paints (if it doesn't collide
with the base's automatic call) or silently paints nothing (if it shadows
`self._badge` under a different name — the base's automatic call still fires
against an inert field). A widget that genuinely needs more than one badge
at once (`ReadoutWidget` in parametric EQ, one per readout column) keeps its
own `dict[str, BadgeGlyph]` and overrides `_draw_badge` to paint all of them,
leaving the inherited single-slot `_badge`/`set_badge()` untouched and inert
on that class.

`ContainerWidget` (`uilib/container.py`) — the base every `Panel`/`Dialog`
inherits — has three separate paint paths of its own (virtual refresh,
non-virtual refresh, the dirty-rect rebuild inside `do_draw`) instead of one
`do_draw` like a plain `Widget`, so it calls `_draw_badge()` explicitly in
all three, right after `_draw_selection()`. This is *why* container-based
panels get badges "for free" today rather than by accident — a new
container-level paint path that skips the call will silently drop badges
with no error, so add the call whenever you add a fourth.
