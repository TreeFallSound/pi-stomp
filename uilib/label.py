from uilib.box import Box
from uilib.widget import Widget

_PAD = 1  # px around bbox to absorb anti-aliasing fringe


class Label:
    """Positioned text cell with dirty-rectangle tracking for surgical LCD updates.

    Bake font, background color, and default anchor (x, y) at construction.
    render() is called from a widget's _draw pass (full redraw).
    update() does a surgical clear-then-redraw, pushing only the dirty region
    to the LCD via the host widget's _focus/_unfocus.
    Pass x= to override the anchor per call (e.g. for right-aligned text).
    """

    def __init__(self, x: int, y: int, font, bg_color: tuple) -> None:
        self._x = x
        self._y = y
        self._font = font
        self._bg = bg_color
        self._text: str | None = None
        self._color: tuple | None = None
        self._bbox: Box | None = None

    @property
    def text(self) -> str | None:
        return self._text

    def _measure(self, text: str, x: int) -> Box:
        tb = self._font.getbbox(text)
        return Box(x + tb[0] - _PAD, self._y + tb[1] - _PAD, x + tb[2] + _PAD, self._y + tb[3] + _PAD)

    def render(self, draw, color: tuple, text: str | None, *, x: int | None = None) -> None:
        """Draw into an already-obtained draw context; record bbox."""
        rx = x if x is not None else self._x
        self._x = rx
        self._color = color
        if text:
            draw.text((rx, self._y), text, font=self._font, fill=color)
            self._bbox = self._measure(text, rx)
        else:
            self._bbox = None
        self._text = text

    def update(self, widget: Widget, color: tuple, text: str | None, *, x: int | None = None) -> None:
        """Surgical update: clear old bbox, draw new text, push to LCD."""
        rx = x if x is not None else self._x
        if text == self._text and rx == self._x and color == self._color:
            return
        new_bbox = self._measure(text, rx) if text else None
        if self._bbox and new_bbox:
            dirty = self._bbox.union(new_bbox)
        elif self._bbox or new_bbox:
            dirty = self._bbox or new_bbox
        else:
            dirty = None
        self._text = text
        self._color = color
        self._bbox = new_bbox
        self._x = rx
        if dirty is None:
            return
        image, draw, _ = widget._focus(dirty)
        if image is None or draw is None:
            return
        draw.rectangle(dirty.PIL_rect, fill=self._bg)
        if text:
            draw.text((rx, self._y), text, font=self._font, fill=color)
        widget._unfocus(dirty)
