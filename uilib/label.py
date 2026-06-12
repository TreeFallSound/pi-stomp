from uilib.box import Box
from uilib.widget import Widget

_PAD = 1  # px around bbox to absorb anti-aliasing fringe


class Label(Widget):
    """Positioned text widget with surgical dirty-rectangle updates.

    set_text() recomputes the bounding box and refreshes only the union of
    old and new bboxes, so a one-character change pushes a few-pixel column
    to the LCD rather than the whole parent.

    The widget's box tracks the text bbox (with _PAD around it). Empty text
    collapses the box to a zero-area point at the anchor — _draw_erase and
    _draw both become no-ops, so an unset Label is invisible without any
    state hacks.
    """

    def __init__(self, x: int, y: int, font, parent: Widget | None = None, **kwargs) -> None:
        super().__init__(box=Box(x, y, x, y), parent=parent, **kwargs)
        self._font = font
        self._anchor_x = x
        self._anchor_y = y
        self._text: str | None = None
        self._color: tuple | None = None

    @property
    def text(self) -> str | None:
        return self._text

    def _measure(self, text: str, x: int, y: int) -> Box:
        tb = self._font.getbbox(text)
        return Box(x + tb[0] - _PAD, y + tb[1] - _PAD, x + tb[2] + _PAD, y + tb[3] + _PAD)

    def set_text(self, text: str | None, color: tuple, *, x: int | None = None) -> None:
        rx = x if x is not None else self._anchor_x
        if text == self._text and color == self._color and rx == self._anchor_x:
            return

        old_box = self.box
        new_box = (
            self._measure(text, rx, self._anchor_y)
            if text
            else Box(rx, self._anchor_y, rx, self._anchor_y)
        )

        if self._text and text:
            dirty = old_box.union(new_box)
        elif self._text:
            dirty = old_box
        elif text:
            dirty = new_box
        else:
            # both empty — anchor may have moved, but there's nothing to repaint
            self._anchor_x = rx
            self.box = new_box
            return

        self._text = text
        self._color = color
        self._anchor_x = rx
        self.box = dirty
        self.refresh()
        self.box = new_box

    def _draw_erase(self, image, draw, box) -> None:
        # Skip the rounded-rect path in the default _draw_erase; a zero-area
        # box would still trigger a one-pixel artifact.
        if box.width <= 0 or box.height <= 0:
            return
        draw.rectangle(box.PIL_rect, fill=self.bkgnd_color)

    def _draw(self, image, draw, real_box) -> None:
        if not self._text:
            return
        # Translate parent-relative anchor → image coordinates via the
        # offset between self.box (parent-rel) and real_box (image-rel).
        ox = real_box.x0 - self.box.x0
        oy = real_box.y0 - self.box.y0
        draw.text(
            (self._anchor_x + ox, self._anchor_y + oy),
            self._text,
            font=self._font,
            fill=self._color,
        )
