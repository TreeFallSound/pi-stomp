"""
Tests for ContainerWidget._cache_valid flag and push-up mechanism.

Contracts verified:
  1. Flag transitions — valid/invalid at the right moments
  2. Cache-hit skips rebuild — no child _draw calls on a valid cache
  3. Push-up pixel parity — cached blit produces identical pixels to a full rebuild
"""

import pytest
from PIL import Image, ImageDraw

from uilib.box import Box
from uilib.paint import PaintContext, BufferPool
from uilib.container import ContainerWidget
from uilib.widget import Widget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

W, H = 100, 60


class _ColorWidget(Widget):
    def __init__(self, color, **kwargs):
        self.color = color
        super().__init__(**kwargs)

    def _draw(self, ctx):
        ctx.fill(self.color)


def _container(w=W, h=H):
    return ContainerWidget(box=Box.xywh(0, 0, w, h))


def _render(container, w=W, h=H):
    """Blit container into a fresh image and return it."""
    img = Image.new("RGB", (w, h), (128, 128, 128))
    pool = BufferPool((w, h))
    ctx = PaintContext(img, ImageDraw.Draw(img), Box.xywh(0, 0, w, h), pool)
    container.do_draw(ctx, Box.xywh(0, 0, w, h))
    return img


# ---------------------------------------------------------------------------
# 1. Flag transitions
# ---------------------------------------------------------------------------


class TestFlagTransitions:
    def test_false_after_init(self):
        c = _container()
        assert c._cache_valid is False

    def test_true_after_nonvirtual_refresh(self):
        c = _container()
        c.refresh()
        assert c._cache_valid is True

    def test_true_after_virtual_refresh(self):
        c = ContainerWidget(box=Box.xywh(0, 0, W, H), virtual=True, content_height=H * 3)
        c.refresh()
        assert c._cache_valid is True

    def test_false_after_child_attach(self):
        c = _container()
        c.refresh()
        assert c._cache_valid is True
        _ColorWidget(color=(255, 0, 0), box=Box.xywh(0, 0, 10, 10), parent=c)
        assert c._cache_valid is False

    def test_false_after_child_detach(self):
        c = _container()
        leaf = _ColorWidget(color=(255, 0, 0), box=Box.xywh(0, 0, 10, 10), parent=c)
        c.refresh()
        assert c._cache_valid is True
        leaf.detach()
        assert c._cache_valid is False

    def test_false_after_setup_realloc(self):
        """_setup() resets the flag when a new image is allocated."""
        c = _container(W, H)
        c.refresh()
        assert c._cache_valid is True
        # Trigger reallocation by changing the box size
        c.set_box(Box.xywh(0, 0, W + 10, H + 10), refresh=False)
        c._setup()
        assert c._cache_valid is False

    def test_invalidation_bubbles_to_ancestor(self):
        """attach() on an inner container should bubble up to outer."""
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        outer.refresh()
        assert outer._cache_valid is True
        assert inner._cache_valid is True

        _ColorWidget(color=(0, 255, 0), box=Box.xywh(0, 0, 10, 10), parent=inner)

        assert inner._cache_valid is False
        assert outer._cache_valid is False

    def test_invalidation_stops_at_panelstack(self):
        """PanelStack._skip_cache_push=True; its own _cache_valid follows the normal
        bubble but PanelStack has no parent so the chain terminates there."""
        from uilib.panel import PanelStack
        from tests.conftest import FakeLcd

        lcd = FakeLcd()
        stack = PanelStack(lcd)
        assert stack._skip_cache_push is True

        # Attach a child container; invalidation must reach stack but no further
        # (stack has no parent, so there is nothing above it to corrupt).
        child = ContainerWidget(box=Box.xywh(0, 0, 50, 50), parent=stack)
        child.refresh()
        assert child._cache_valid is True

        _ColorWidget(color=(0, 0, 255), box=Box.xywh(0, 0, 10, 10), parent=child)
        assert child._cache_valid is False
        # stack itself gets invalidated too (it's a ContainerWidget)
        assert stack._cache_valid is False


# ---------------------------------------------------------------------------
# 2. Cache-hit skips rebuild
# ---------------------------------------------------------------------------


class TestCacheHitSkipsRebuild:
    def _spy_container(self):
        """Return (container, [leaf_widgets], draw_counts_dict)."""
        c = _container()
        COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        leaves = []
        for i, color in enumerate(COLORS):
            w = _ColorWidget(color=color, box=Box.xywh(i * 30, 0, 30, H), parent=c)
            leaves.append(w)
        c.refresh()
        assert c._cache_valid is True

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
        _render(c)  # full clip
        assert all(v == 0 for v in counts.values()), (
            f"Expected no child _draw calls on cache hit (full clip), got {counts}"
        )

    def test_partial_clip_no_child_draw(self):
        c, _, counts = self._spy_container()
        img = Image.new("RGB", (W, H), (128, 128, 128))
        pool = BufferPool((W, H))
        partial_clip = Box.xywh(0, 0, W // 2, H)
        ctx = PaintContext(img, ImageDraw.Draw(img), partial_clip, pool)
        c.do_draw(ctx, Box.xywh(0, 0, W, H))
        assert all(v == 0 for v in counts.values()), (
            f"Expected no child _draw calls on cache hit (partial clip), got {counts}"
        )

    def test_cache_miss_does_invoke_child_draw(self):
        """Sanity check: if cache is invalid, children must be redrawn."""
        c, _, counts = self._spy_container()
        c._cache_valid = False  # force miss
        _render(c)
        assert all(v == 1 for v in counts.values()), (
            f"Expected one _draw per child on cache miss, got {counts}"
        )


# ---------------------------------------------------------------------------
# 3. Push-up pixel parity
# ---------------------------------------------------------------------------


class TestPushUpPixelParity:
    """The pixels produced by a cache-blit must match those from a full rebuild,
    both after initial render and after a leaf update pushed up via propagate_dirty."""

    def test_initial_render_blit_equals_rebuild(self):
        """After refresh(), a cache-blit and a forced rebuild must be identical."""
        c = _container()
        _ColorWidget(color=(200, 100, 50), box=Box.xywh(0, 0, 50, 30), parent=c)
        _ColorWidget(color=(50, 150, 200), box=Box.xywh(50, 30, 50, 30), parent=c)
        c.refresh()

        cached = _render(c)           # cache hit → pure blit
        c._cache_valid = False
        rebuilt = _render(c)          # cache miss → full rebuild

        assert cached.tobytes() == rebuilt.tobytes(), (
            "Cache blit diverged from rebuild on initial render"
        )

    def test_leaf_color_change_push_up_parity(self):
        """After a leaf widget changes color and calls refresh(), the push-up
        should update the parent cache so a blit produces the same result as
        a full rebuild."""
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        leaf = _ColorWidget(color=(255, 0, 0), box=Box.xywh(10, 10, 40, 20), parent=inner)

        outer.refresh()
        assert outer._cache_valid is True

        # Change leaf and trigger push-up
        leaf.color = (0, 0, 255)
        leaf.refresh()

        # Optimized path: outer._cache_valid is still True; do_draw blits outer.image
        assert outer._cache_valid is True, (
            "Push-up must not invalidate the outer cache; it updates outer.image in place"
        )
        optimized = _render(outer)

        # Baseline path: force rebuild of everything
        outer._cache_valid = False
        inner._cache_valid = False
        rebuilt = _render(outer)

        assert optimized.tobytes() == rebuilt.tobytes(), (
            "Push-up result diverged from full rebuild after leaf color change"
        )

    def test_leaf_hide_push_up_parity(self):
        """Hiding a leaf triggers parent.refresh() which re-renders the container.
        The resulting outer cache should match a forced rebuild."""
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        leaf = _ColorWidget(color=(0, 200, 0), box=Box.xywh(5, 5, 30, 20), parent=inner)
        _ColorWidget(color=(200, 0, 0), box=Box.xywh(40, 5, 30, 20), parent=inner)

        outer.refresh()

        # hide() calls parent.refresh() → inner.refresh() → propagate_dirty into outer
        leaf.hide()

        optimized = _render(outer)

        outer._cache_valid = False
        inner._cache_valid = False
        rebuilt = _render(outer)

        assert optimized.tobytes() == rebuilt.tobytes(), (
            "Push-up result diverged from full rebuild after leaf hide"
        )

    def test_partial_scroll_push_up_parity(self):
        """A virtual child's scroll() pushes up into the outer cache.
        The blitted result must match a forced rebuild."""
        outer = _container()
        virtual = ContainerWidget(
            box=Box.xywh(0, 0, W, H),
            virtual=True,
            content_height=H * 3,
            parent=outer,
        )
        ITEM_H = H // 3
        COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
                  (255, 255, 0), (0, 255, 255), (255, 0, 255),
                  (128, 128, 0), (0, 128, 128), (128, 0, 128)]
        for i, color in enumerate(COLORS):
            _ColorWidget(color=color, box=Box.xywh(0, i * ITEM_H, W, ITEM_H), parent=virtual)

        outer.refresh()

        # Scroll virtual child; scroll() calls propagate_dirty → push-up into outer
        virtual.scroll((0, H))

        optimized = _render(outer)

        outer._cache_valid = False
        rebuilt = _render(outer)

        assert optimized.tobytes() == rebuilt.tobytes(), (
            "Push-up result diverged from full rebuild after virtual child scroll"
        )
