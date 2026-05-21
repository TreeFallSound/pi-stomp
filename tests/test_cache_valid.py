"""
Tests for ContainerWidget._dirty_region accumulation and lazy-rebuild semantics.

Contracts verified:
  1. Dirty-region transitions — set on init/invalidation, cleared on rebuild
  2. Cache-hit skips rebuild — no child _draw calls when dirty_region is None
  3. Rebuild pixel parity — a stale cache rebuilt on demand produces the same
     pixels as a freshly-painted one
  4. Small-clip refresh stays cheap — Widget.refresh(small_box) confines the
     parent's next rebuild to only the children that intersect that box
"""

import pygame

from uilib.box import Box
from uilib.paint import PaintContext
from uilib.container import ContainerWidget
from uilib.widget import Widget


W, H = 100, 60


class _ColorWidget(Widget):
    def __init__(self, color, **kwargs):
        self.color: tuple[int, int, int] = color
        super().__init__(**kwargs)

    def _draw(self, ctx):
        ctx.fill(self.color)


def _container(w=W, h=H):
    return ContainerWidget(box=Box.xywh(0, 0, w, h))


def _render(container, w=W, h=H):
    """Blit container into a fresh surface and return it."""
    surf = pygame.Surface((w, h))
    surf.fill((128, 128, 128))
    ctx = PaintContext(surf, Box.xywh(0, 0, w, h))
    container.do_draw(ctx, Box.xywh(0, 0, w, h))
    return surf


def _bytes(surf):
    return pygame.image.tobytes(surf, "RGB")


def _force_dirty(c):
    """Mark a container fully stale (test helper for forcing a rebuild)."""
    c._dirty_region = c._content_bounds()


# ---------------------------------------------------------------------------
# 1. Dirty-region transitions
# ---------------------------------------------------------------------------


class TestDirtyRegionTransitions:
    def test_initial_full_dirty(self):
        c = _container()
        assert c._dirty_region == c._content_bounds()

    def test_clean_after_nonvirtual_refresh(self):
        c = _container()
        c.refresh()
        assert c._dirty_region is None

    def test_clean_after_virtual_refresh(self):
        c = ContainerWidget(box=Box.xywh(0, 0, W, H), virtual=True, content_height=H * 3)
        c.refresh()
        assert c._dirty_region is None

    def test_dirty_after_child_attach(self):
        c = _container()
        c.refresh()
        assert c._dirty_region is None
        _ColorWidget(color=(255, 0, 0), box=Box.xywh(0, 0, 10, 10), parent=c)
        assert c._dirty_region is not None

    def test_dirty_after_child_detach(self):
        c = _container()
        leaf = _ColorWidget(color=(255, 0, 0), box=Box.xywh(0, 0, 10, 10), parent=c)
        c.refresh()
        assert c._dirty_region is None
        leaf.detach()
        assert c._dirty_region is not None

    def test_dirty_after_setup_realloc(self):
        c = _container(W, H)
        c.refresh()
        assert c._dirty_region is None
        c.set_box(Box.xywh(0, 0, W + 10, H + 10), refresh=False)
        c._setup()
        assert c._dirty_region is not None

    def test_invalidation_bubbles_to_ancestor(self):
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        outer.refresh()
        assert outer._dirty_region is None
        assert inner._dirty_region is None

        _ColorWidget(color=(0, 255, 0), box=Box.xywh(0, 0, 10, 10), parent=inner)

        assert inner._dirty_region is not None
        assert outer._dirty_region is not None

    def test_invalidation_bubbles_through_panelstack(self):
        from uilib.panel import PanelStack
        from tests.conftest import FakeLcd

        lcd = FakeLcd()
        stack = PanelStack(lcd)

        child = ContainerWidget(box=Box.xywh(0, 0, 50, 50), parent=stack)
        child.refresh()
        assert child._dirty_region is None

        _ColorWidget(color=(0, 0, 255), box=Box.xywh(0, 0, 10, 10), parent=child)
        assert child._dirty_region is not None
        assert stack._dirty_region is not None

    def test_disjoint_invalidations_union_into_bbox(self):
        c = _container()
        c.refresh()
        assert c._dirty_region is None
        c._invalidate_cache(Box.xywh(0, 0, 10, 10))
        c._invalidate_cache(Box.xywh(80, 50, 10, 10))
        assert c._dirty_region == Box.xywh(0, 0, 90, 60)


# ---------------------------------------------------------------------------
# 2. Cache-hit skips rebuild
# ---------------------------------------------------------------------------


class TestCacheHitSkipsRebuild:
    def _spy_container(self):
        c = _container()
        COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        leaves = []
        for i, color in enumerate(COLORS):
            w = _ColorWidget(color=color, box=Box.xywh(i * 30, 0, 30, H), parent=c)
            leaves.append(w)
        c.refresh()
        assert c._dirty_region is None

        counts = {i: 0 for i in range(len(leaves))}
        for i, w in enumerate(leaves):
            orig = w._draw

            def make_spy(orig, idx):
                def _spy(ctx):
                    counts[idx] += 1
                    orig(ctx)

                return _spy

            w._draw = make_spy(orig, i)

        return c, leaves, counts

    def test_full_clip_no_child_draw(self):
        c, _, counts = self._spy_container()
        _render(c)
        assert all(v == 0 for v in counts.values()), (
            f"Expected no child _draw calls on cache hit (full clip), got {counts}"
        )

    def test_partial_clip_no_child_draw(self):
        c, _, counts = self._spy_container()
        surf = pygame.Surface((W, H))
        surf.fill((128, 128, 128))
        partial_clip = Box.xywh(0, 0, W // 2, H)
        ctx = PaintContext(surface=surf, clip=partial_clip)
        c.do_draw(ctx, Box.xywh(0, 0, W, H))
        assert all(v == 0 for v in counts.values()), (
            f"Expected no child _draw calls on cache hit (partial clip), got {counts}"
        )

    def test_cache_miss_does_invoke_child_draw(self):
        c, _, counts = self._spy_container()
        _force_dirty(c)
        _render(c)
        assert all(v == 1 for v in counts.values()), f"Expected one _draw per child on cache miss, got {counts}"


# ---------------------------------------------------------------------------
# 3. Rebuild pixel parity — stale-cache rebuild matches fresh paint
# ---------------------------------------------------------------------------


class TestRebuildPixelParity:
    def test_initial_render_blit_equals_rebuild(self):
        c = _container()
        _ColorWidget(color=(200, 100, 50), box=Box.xywh(0, 0, 50, 30), parent=c)
        _ColorWidget(color=(50, 150, 200), box=Box.xywh(50, 30, 50, 30), parent=c)
        c.refresh()

        cached = _render(c)
        _force_dirty(c)
        rebuilt = _render(c)

        assert _bytes(cached) == _bytes(rebuilt), "Cache blit diverged from rebuild on initial render"

    def test_leaf_color_change_rebuild_parity(self):
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        leaf = _ColorWidget(color=(255, 0, 0), box=Box.xywh(10, 10, 40, 20), parent=inner)

        outer.refresh()
        leaf.color = (0, 0, 255)
        leaf.refresh()

        lazy_rebuild = _render(outer)

        _force_dirty(outer)
        _force_dirty(inner)
        forced_rebuild = _render(outer)

        assert _bytes(lazy_rebuild) == _bytes(forced_rebuild)

    def test_leaf_hide_rebuild_parity(self):
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        leaf = _ColorWidget(color=(0, 200, 0), box=Box.xywh(5, 5, 30, 20), parent=inner)
        _ColorWidget(color=(200, 0, 0), box=Box.xywh(40, 5, 30, 20), parent=inner)

        outer.refresh()
        leaf.hide()

        lazy_rebuild = _render(outer)

        _force_dirty(outer)
        _force_dirty(inner)
        forced_rebuild = _render(outer)

        assert _bytes(lazy_rebuild) == _bytes(forced_rebuild)

    def test_partial_scroll_rebuild_parity(self):
        outer = _container()
        virtual = ContainerWidget(
            box=Box.xywh(0, 0, W, H),
            virtual=True,
            content_height=H * 3,
            parent=outer,
        )
        ITEM_H = H // 3
        COLORS = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255),
            (255, 255, 0), (0, 255, 255), (255, 0, 255),
            (128, 128, 0), (0, 128, 128), (128, 0, 128),
        ]
        for i, color in enumerate(COLORS):
            _ColorWidget(color=color, box=Box.xywh(0, i * ITEM_H, W, ITEM_H), parent=virtual)

        outer.refresh()
        virtual.scroll((0, H))

        lazy_rebuild = _render(outer)

        _force_dirty(outer)
        forced_rebuild = _render(outer)

        assert _bytes(lazy_rebuild) == _bytes(forced_rebuild)


# ---------------------------------------------------------------------------
# 4. Small-clip refresh stays cheap
# ---------------------------------------------------------------------------


class TestSmallClipRefreshIsCheap:
    """A leaf widget that calls Widget.refresh(box=small_box) for frequent
    point updates (e.g. an animated VU meter, a single tab toggle) must not
    force a full sibling re-paint on the parent's next render. The parent's
    dirty_region scopes the rebuild to only the children that overlap."""

    def _make(self):
        """Three side-by-side leaves on a parent that's already cached."""
        c = _container()
        leaves = [
            _ColorWidget(color=(255, 0, 0), box=Box.xywh(0, 0, 30, H), parent=c),
            _ColorWidget(color=(0, 255, 0), box=Box.xywh(30, 0, 30, H), parent=c),
            _ColorWidget(color=(0, 0, 255), box=Box.xywh(60, 0, 30, H), parent=c),
        ]
        # Establish the cache.
        c.refresh()
        assert c._dirty_region is None

        counts = {i: 0 for i in range(len(leaves))}
        for i, w in enumerate(leaves):
            orig = w._draw

            def make_spy(orig, idx):
                def _spy(ctx):
                    counts[idx] += 1
                    orig(ctx)

                return _spy

            w._draw = make_spy(orig, i)
        return c, leaves, counts

    def test_widget_refresh_box_marks_only_that_rect_dirty(self):
        c, leaves, _ = self._make()
        small = Box.xywh(2, 2, 5, 5)
        leaves[0].refresh(box=small)
        # Leaf painted into c.surface directly (clip-respecting). Outer cache
        # was already clean — propagate_dirty from c bubbles to its parent
        # (None here), so c.dirty_region stays None. The leaf itself doesn't
        # accumulate region in c — only propagate_dirty does. Wrap c in a
        # parent to observe accumulation.
        assert c._dirty_region is None  # c is its own paint target; no upward dirty

    def test_parent_rebuild_scoped_to_dirty_rect(self):
        """Widget.refresh(box) on a leaf invalidates the grandparent's cache
        with that rect; the grandparent's next render rebuilds only via the
        children whose boxes intersect the rect."""
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        leaves = [
            _ColorWidget(color=(255, 0, 0), box=Box.xywh(0, 0, 30, H), parent=inner),
            _ColorWidget(color=(0, 255, 0), box=Box.xywh(30, 0, 30, H), parent=inner),
            _ColorWidget(color=(0, 0, 255), box=Box.xywh(60, 0, 30, H), parent=inner),
        ]
        outer.refresh()
        assert outer._dirty_region is None

        # Spy on leaf draws AFTER the warm-up render.
        counts = {i: 0 for i in range(len(leaves))}
        for i, w in enumerate(leaves):
            orig = w._draw

            def make_spy(orig, idx):
                def _spy(ctx):
                    counts[idx] += 1
                    orig(ctx)

                return _spy

            w._draw = make_spy(orig, i)

        # A tiny in-leaf-0 redraw.
        small = Box.xywh(2, 2, 5, 5)
        leaves[0].refresh(box=small)

        # outer's dirty_region must be exactly the small rect (no sibling
        # contribution): leaf0.box + inner.box offsets = same rect since both
        # are at (0,0).
        assert outer._dirty_region == small

        # Now render outer. Cache-miss inside outer scopes the rebuild to
        # `small`. Only inner intersects, so inner.do_draw fires once (cache
        # hit ⇒ pure blit, no child _draw). Leaves 1 and 2 must NOT see _draw.
        _render(outer)
        # leaf 0 painted once during refresh(box=small) (direct paint into
        # inner.surface). Outer's rebuild sees inner as a cache hit (inner's
        # own dirty_region is None) ⇒ pure blit, no child _draw.
        assert counts[0] == 1, f"leaf 0 painted exactly once via refresh, got {counts}"
        assert counts[1] == 0, f"leaf 1 outside dirty rect — must not re-paint, got {counts}"
        assert counts[2] == 0, f"leaf 2 outside dirty rect — must not re-paint, got {counts}"

    def test_repeated_small_refreshes_dont_force_full_rebuild(self):
        """Many disjoint small refreshes accumulate into a bounding box but
        still skip children that fall entirely outside that box."""
        outer = _container(200, 60)
        inner = ContainerWidget(box=Box.xywh(0, 0, 200, 60), parent=outer)
        leaves = [
            _ColorWidget(color=(255, 0, 0), box=Box.xywh(0, 0, 50, 60), parent=inner),
            _ColorWidget(color=(0, 255, 0), box=Box.xywh(50, 0, 50, 60), parent=inner),
            _ColorWidget(color=(0, 0, 255), box=Box.xywh(100, 0, 50, 60), parent=inner),
            _ColorWidget(color=(255, 255, 0), box=Box.xywh(150, 0, 50, 60), parent=inner),
        ]
        outer.refresh()
        surf = pygame.Surface((200, 60))
        surf.fill((0, 0, 0))
        outer.do_draw(PaintContext(surf, Box.xywh(0, 0, 200, 60)), Box.xywh(0, 0, 200, 60))

        counts = {i: 0 for i in range(len(leaves))}
        for i, w in enumerate(leaves):
            orig = w._draw

            def make_spy(orig, idx):
                def _spy(ctx):
                    counts[idx] += 1
                    orig(ctx)

                return _spy

            w._draw = make_spy(orig, i)

        # Refresh tiny rects inside leaves 0 and 1 only.
        leaves[0].refresh(box=Box.xywh(2, 2, 5, 5))
        leaves[1].refresh(box=Box.xywh(52, 2, 5, 5))

        # Outer's dirty_region is the bbox covering both refresh rects:
        # (2,2)-(7,7) ∪ (52,2)-(57,7) = (2,2)-(57,7).
        assert outer._dirty_region == Box(2, 2, 57, 7)

        outer.do_draw(PaintContext(surf, Box.xywh(0, 0, 200, 60)), Box.xywh(0, 0, 200, 60))

        # Leaves 0 and 1 already wrote into inner directly (counts stay 0 —
        # spies attached after the refreshes). Leaves 2 and 3 must never be
        # asked to repaint because they fall outside (57,7).
        assert counts[2] == 0, f"leaf 2 outside dirty bbox — must not re-paint, got {counts}"
        assert counts[3] == 0, f"leaf 3 outside dirty bbox — must not re-paint, got {counts}"
