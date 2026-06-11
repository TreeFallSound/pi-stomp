"""Label widget — unit tests (pygame ctx model)."""

import pygame

from uilib.box import Box
from uilib.container import ContainerWidget
from uilib.label import Label
from uilib.pygame_init import font as make_font

WHITE = (255, 255, 255)
GREEN = (0, 200, 0)


def _font():
    return make_font("fonts/DejaVuSans.ttf", 16)


class _Parent(ContainerWidget):
    """A real backing-surface container that records each child refresh.

    Label.refresh() paints straight into our surface; we wrap it to capture the
    dirty box (self.box at call time) so tests can assert refresh count + region
    without reaching into the framework."""

    def __init__(self, width: int = 200, height: int = 50) -> None:
        super().__init__(box=Box(0, 0, width, height))

    def adopt(self, label: Label) -> Label:
        self.refreshes: list[Box] = []
        orig = label.refresh

        def spy(box=None):
            self.refreshes.append(label.box.copy())
            return orig(box)

        label.refresh = spy  # type: ignore[method-assign]
        return label


def _label(parent, x=10, y=5):
    return parent.adopt(Label(x, y, _font(), parent=parent))


def _pixel_present(surface, box, color) -> bool:
    for px in range(int(box.x0), int(box.x1)):
        for py in range(int(box.y0), int(box.y1)):
            if tuple(surface.get_at((px, py)))[:3] == color:
                return True
    return False


class TestLabelSetText:
    def test_initial_set_text_refreshes(self):
        parent = _Parent()
        label = _label(parent)
        label.set_text("A4", WHITE)
        assert label.text == "A4"
        assert label.box.width > 0
        assert len(parent.refreshes) == 1

    def test_same_text_color_and_x_no_refresh(self):
        parent = _Parent()
        label = _label(parent)
        label.set_text("A4", WHITE)
        parent.refreshes.clear()
        label.set_text("A4", WHITE)
        assert parent.refreshes == []

    def test_new_text_refreshes_over_union(self):
        parent = _Parent()
        label = _label(parent)
        label.set_text("A4", WHITE)
        old_box = label.box
        parent.refreshes.clear()
        label.set_text("C#4", WHITE)
        assert len(parent.refreshes) == 1
        dirty = parent.refreshes[0]
        # dirty must cover both the old and the new bbox
        assert dirty.x0 <= old_box.x0 and dirty.x1 >= old_box.x1
        assert dirty.x0 <= label.box.x0 and dirty.x1 >= label.box.x1

    def test_color_change_refreshes(self):
        parent = _Parent()
        label = _label(parent)
        label.set_text("A4", WHITE)
        parent.refreshes.clear()
        label.set_text("A4", GREEN)
        assert len(parent.refreshes) == 1

    def test_text_to_none_refreshes_then_collapses(self):
        parent = _Parent()
        label = _label(parent)
        label.set_text("A4", WHITE)
        old_box = label.box
        parent.refreshes.clear()
        label.set_text(None, WHITE)
        assert len(parent.refreshes) == 1
        # dirty was the old box; the widget's own box is now zero-area
        assert parent.refreshes[0] == old_box
        assert label.box.width == 0 and label.box.height == 0
        assert label.text is None

    def test_none_to_none_does_not_refresh(self):
        parent = _Parent()
        label = _label(parent)
        parent.refreshes.clear()
        label.set_text(None, WHITE)
        assert parent.refreshes == []

    def test_anchor_move_changes_bbox(self):
        parent = _Parent()
        label = _label(parent)
        label.set_text("X", WHITE)
        first = label.box
        label.set_text("X", WHITE, x=80)
        # same text, but moved → bbox slid right
        assert label.box.x0 > first.x0


class TestLabelDrawing:
    """Confirm pixels actually land where Label says they should."""

    def test_draw_renders_text_into_backing_surface(self):
        parent = _Parent()
        label = _label(parent, 50, 20)
        label.set_text("X", WHITE)
        assert _pixel_present(parent.surface, label.box, WHITE)

    def test_text_lands_at_new_anchor_after_move(self):
        """Regression: when the label moves rightward, _draw must place text
        at the new anchor — not shifted left by (new_x - old_x)."""
        parent = _Parent(width=320)
        label = _label(parent, 50, 20)
        label.set_text("X", WHITE, x=50)
        # Wipe and re-draw at a new x to isolate the second render.
        assert parent.surface is not None
        parent.surface.fill((0, 0, 0))
        label.set_text("X", WHITE, x=200)
        # New bbox should hold white pixels; old bbox should be empty.
        assert _pixel_present(parent.surface, label.box, WHITE)
        assert not _pixel_present(parent.surface, Box(40, 0, 80, 50), WHITE)

    def test_clear_erases_old_pixels(self):
        parent = _Parent()
        label = _label(parent, 50, 20)
        label.set_text("X", WHITE)
        label.set_text(None, WHITE)
        # After clearing, no white pixel remains anywhere on the surface.
        assert not _pixel_present(parent.surface, Box(0, 0, 200, 50), WHITE)


class TestLabelBbox:
    def test_bbox_has_width(self):
        parent = _Parent()
        label = _label(parent)
        label.set_text("XX", WHITE)
        assert label.box.width > 0

    def test_bbox_x_includes_anchor(self):
        parent = _Parent()
        label = _label(parent, 50, 5)
        label.set_text("X", WHITE)
        assert label.box.x0 >= 49  # anchor - 1px padding
