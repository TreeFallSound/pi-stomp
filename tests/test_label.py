"""Label widget — unit tests."""

from unittest.mock import Mock

from PIL import Image, ImageDraw, ImageFont

from uilib.box import Box
from uilib.label import Label
from uilib.widget import Widget


class _FakeParent(Widget):
    """Minimal Widget parent backed by its own PIL image, intercepting focus/unfocus."""

    def __init__(self, width: int = 200, height: int = 50) -> None:
        super().__init__(box=Box(0, 0, width, height), parent=None)
        self.image = Image.new("RGB", (width, height), (0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.focus_calls: list[Box] = []
        self.unfocus_calls: list[Box] = []

    def _focus(self, box):
        self.focus_calls.append(box)
        return self.image, self.draw, box

    def _unfocus(self, box):
        self.unfocus_calls.append(box)


def _font():
    return ImageFont.truetype("DejaVuSans.ttf", 16)


class TestLabelSetText:
    def test_initial_set_text_refreshes(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        label.set_text("A4", (255, 255, 255))
        assert label.text == "A4"
        assert label.box.width > 0
        assert len(parent.focus_calls) == 1
        assert len(parent.unfocus_calls) == 1

    def test_same_text_color_and_x_no_refresh(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        label.set_text("A4", (255, 255, 255))
        parent.focus_calls.clear()
        parent.unfocus_calls.clear()
        label.set_text("A4", (255, 255, 255))
        assert parent.focus_calls == []
        assert parent.unfocus_calls == []

    def test_new_text_refreshes_over_union(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        label.set_text("A4", (255, 255, 255))
        old_box = label.box
        parent.focus_calls.clear()
        label.set_text("C#4", (255, 255, 255))
        assert len(parent.focus_calls) == 1
        dirty = parent.focus_calls[0]
        # dirty must cover both the old and the new bbox
        assert dirty.x0 <= old_box.x0 and dirty.x1 >= old_box.x1
        assert dirty.x0 <= label.box.x0 and dirty.x1 >= label.box.x1

    def test_color_change_refreshes(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        label.set_text("A4", (255, 255, 255))
        parent.focus_calls.clear()
        label.set_text("A4", (0, 200, 0))
        assert len(parent.focus_calls) == 1

    def test_text_to_none_refreshes_then_collapses(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        label.set_text("A4", (255, 255, 255))
        old_box = label.box
        parent.focus_calls.clear()
        label.set_text(None, (255, 255, 255))
        assert len(parent.focus_calls) == 1
        # dirty was the old box; the widget's own box is now zero-area
        assert parent.focus_calls[0] == old_box
        assert label.box.width == 0 and label.box.height == 0
        assert label.text is None

    def test_none_to_none_does_not_refresh(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        parent.focus_calls.clear()
        label.set_text(None, (255, 255, 255))
        assert parent.focus_calls == []

    def test_anchor_move_changes_bbox(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        label.set_text("X", (255, 255, 255))
        first = label.box
        label.set_text("X", (255, 255, 255), x=80)
        # same text, but moved → bbox slid right
        assert label.box.x0 > first.x0


class TestLabelDrawing:
    """Confirm pixels actually land where Label says they should."""

    def test_draw_renders_text_into_backing_image(self):
        parent = _FakeParent()
        label = Label(50, 20, _font(), parent=parent)
        label.set_text("X", (255, 255, 255))
        # Some white pixel must exist inside the label's bbox.
        bx = label.box
        cropped = parent.image.crop((bx.x0, bx.y0, bx.x1, bx.y1))
        assert any(p == (255, 255, 255) for p in cropped.getdata())

    def test_text_lands_at_new_anchor_after_move(self):
        """Regression: when the label moves rightward, _draw must place text
        at the new anchor — not shifted left by (new_x - old_x)."""
        parent = _FakeParent(width=320)
        label = Label(50, 20, _font(), parent=parent)
        label.set_text("X", (255, 255, 255), x=50)
        # Wipe and re-draw at a new x to isolate the second render.
        parent.image.paste((0, 0, 0), (0, 0, 320, 50))
        label.set_text("X", (255, 255, 255), x=200)
        # New bbox should hold white pixels; old bbox should be empty.
        new_crop = parent.image.crop(label.box.PIL_rect)
        assert any(p == (255, 255, 255) for p in new_crop.getdata())
        old_crop = parent.image.crop((40, 0, 80, 50))
        assert all(p == (0, 0, 0) for p in old_crop.getdata())

    def test_clear_erases_old_pixels(self):
        parent = _FakeParent()
        label = Label(50, 20, _font(), parent=parent)
        label.set_text("X", (255, 255, 255))
        label.set_text(None, (255, 255, 255))
        # After clearing, the old bbox region is all background.
        assert all(p == (0, 0, 0) for p in parent.image.getdata())


class TestLabelBbox:
    def test_bbox_has_width(self):
        parent = _FakeParent()
        label = Label(10, 5, _font(), parent=parent)
        label.set_text("XX", (255, 255, 255))
        assert label.box.width > 0

    def test_bbox_x_includes_anchor(self):
        parent = _FakeParent()
        label = Label(50, 5, _font(), parent=parent)
        label.set_text("X", (255, 255, 255))
        assert label.box.x0 >= 49  # anchor - 1px padding
