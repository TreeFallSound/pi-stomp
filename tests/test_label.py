"""Label dirty-rectangle tracking — unit tests."""

from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw, ImageFont

from uilib.box import Box
from uilib.label import Label


def _draw_context(width=200, height=50):
    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    return img, draw


class TestLabelRender:
    def test_render_sets_text(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "Hello")
        assert label.text == "Hello"
        assert label._bbox is not None

    def test_render_none_clears_bbox(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "Hello")
        assert label._bbox is not None
        label.render(draw, (255, 255, 255), None)
        assert label._bbox is None

    def test_render_records_color(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (0, 200, 0), "A4")
        assert label._color == (0, 200, 0)


class TestLabelUpdateDirtyTracking:
    """Test update() dirty-rectangle logic without a live widget tree.

    Label.update() calls widget._focus/_unfocus which requires a full widget
    hierarchy. For pure logic tests we mock out _focus to return a draw context
    and track whether _unfocus was called.
    """

    def test_same_text_color_and_x_no_refresh(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "A4")

        widget = Mock()
        widget._focus.return_value = _draw_context()
        widget._unfocus = Mock()

        label.update(widget, (255, 255, 255), "A4")
        widget._focus.assert_not_called()
        widget._unfocus.assert_not_called()

    def test_new_text_triggers_refresh(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "A4")

        img, draw2 = _draw_context()
        widget = Mock()
        widget._focus.return_value = (img, draw2, Box(0, 0, 200, 50))
        widget._unfocus = Mock()

        label.update(widget, (255, 255, 255), "C4")
        widget._focus.assert_called_once()
        widget._unfocus.assert_called_once()

    def test_color_change_triggers_refresh(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "A4")

        img, draw2 = _draw_context()
        widget = Mock()
        widget._focus.return_value = (img, draw2, Box(0, 0, 200, 50))
        widget._unfocus = Mock()

        label.update(widget, (0, 200, 0), "A4")
        widget._focus.assert_called_once()

    def test_text_to_none_triggers_refresh(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "A4")

        img, draw2 = _draw_context()
        widget = Mock()
        widget._focus.return_value = (img, draw2, Box(0, 0, 200, 50))
        widget._unfocus = Mock()

        label.update(widget, (255, 255, 255), None)
        widget._focus.assert_called_once()

    def test_none_to_text_triggers_refresh(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), None)

        img, draw2 = _draw_context()
        widget = Mock()
        widget._focus.return_value = (img, draw2, Box(0, 0, 200, 50))
        widget._unfocus = Mock()

        label.update(widget, (0, 200, 0), "A4")
        widget._focus.assert_called_once()


class TestLabelMeasure:
    def test_bbox_has_width(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(10, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "XX")
        assert label._bbox is not None
        assert label._bbox.width > 0

    def test_bbox_x_includes_anchor(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        label = Label(50, 5, font, (0, 0, 0))
        _, draw = _draw_context()
        label.render(draw, (255, 255, 255), "X")
        assert label._bbox is not None
        assert label._bbox.x0 >= 49  # anchor - 1px padding