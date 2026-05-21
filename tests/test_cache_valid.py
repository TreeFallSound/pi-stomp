"""
Tests for ContainerWidget._cache_valid flag and lazy-rebuild semantics.

Contracts verified:
  1. Flag transitions — valid/invalid at the right moments
  2. Cache-hit skips rebuild — no child _draw calls on a valid cache
  3. Rebuild pixel parity — a stale cache rebuilt on demand produces the same
     pixels as a freshly-painted one
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
        """_setup() resets the flag when a new surface is allocated."""
        c = _container(W, H)
        c.refresh()
        assert c._cache_valid is True
        c.set_box(Box.xywh(0, 0, W + 10, H + 10), refresh=False)
        c._setup()
        assert c._cache_valid is False

    def test_invalidation_bubbles_to_ancestor(self):
        outer = _container()
        inner = ContainerWidget(box=Box.xywh(0, 0, W, H), parent=outer)
        outer.refresh()
        assert outer._cache_valid is True
        assert inner._cache_valid is True

        _ColorWidget(color=(0, 255, 0), box=Box.xywh(0, 0, 10, 10), parent=inner)

        assert inner._cache_valid is False
        assert outer._cache_valid is False

    def test_invalidation_bubbles_through_panelstack(self):
        from uilib.panel import PanelStack
        from tests.conftest import FakeLcd

        lcd = FakeLcd()
        stack = PanelStack(lcd)

        child = ContainerWidget(box=Box.xywh(0, 0, 50, 50), parent=stack)
        child.refresh()
        assert child._cache_valid is True

        _ColorWidget(color=(0, 0, 255), box=Box.xywh(0, 0, 10, 10), parent=child)
        assert child._cache_valid is False
        assert stack._cache_valid is False


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
        c._cache_valid = False
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
        c._cache_valid = False
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

        outer._cache_valid = False
        inner._cache_valid = False
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

        outer._cache_valid = False
        inner._cache_valid = False
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

        outer._cache_valid = False
        forced_rebuild = _render(outer)

        assert _bytes(lazy_rebuild) == _bytes(forced_rebuild)
