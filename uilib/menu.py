# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from typing import Any, Callable, Sequence

from uilib.box import Box
from uilib.config import Config
from uilib.dialog import Dialog
from uilib.misc import InputEvent, TextHAlign, get_text_size, trace
from uilib.rich_text import RichTextWidget, Segment
from uilib.text import TextWidget

# A menu row label. Either a plain string (rendered as a `TextWidget`) or a
# sequence of `Segment`s (rendered as a `RichTextWidget` — emoji-style glyphs,
# spacers for left/right alignment, etc.).
Label = str | Sequence[Segment]

# Action stored in slot 1 of a `MenuItem`. The menu framework never invokes
# this directly — the per-item callable is decorative context that the
# menu-level `action` callback unpacks from `data` at click time. Typed
# loosely (any signature) so existing callers (`self._dismiss`, bound methods
# with mismatched arities) keep type-checking.
MenuAction = Callable[..., Any]

# Menu items are positional tuples — callers construct them inline as
# `(label, action, arg)`, `(label, action, arg, selected)`, or
# `(label, action, arg, selected, long_action)`. The 5-tuple form is consumed
# by user-supplied menu-level actions (e.g. `lcd.draw_selection_menu` dispatches
# `long_action` on LONG_CLICK) — Menu itself only reads slots 0 and 3.
# Slot 3 may be `None` when callers want to pass slot 4 without a selection flag.
MenuItem = (
    tuple[Label, MenuAction | None, Any]
    | tuple[Label, MenuAction | None, Any, bool | None]
    | tuple[Label, MenuAction | None, Any, bool | None, MenuAction | None]
)


def _item_label(i: MenuItem) -> Label:
    return i[0]


def _item_selected(i: MenuItem) -> bool:
    return len(i) >= 4 and bool(i[3])


class Menu(Dialog):
    """A pop-up menu panel with lines of text to select.

    `items` is a list of `MenuItem` tuples; the first element is the label.
    """
    def __init__(self, items: list[MenuItem], font=None,
                 max_width: int | None = None, max_height: int | None = None,
                 text_halign: TextHAlign = TextHAlign.CENTRE,
                 auto_dismiss: bool = True, dismiss_option: bool = False,
                 default_item: str | None = None, **kwargs) -> None:
        self.max_height = max_height
        self.max_width = max_width
        self.items: list[MenuItem] = items
        self.auto_dismiss = auto_dismiss
        if auto_dismiss is False or dismiss_option is True:
            # without auto_dismiss provide a back arrow to close menu
            self.items.append(('\u2b05', self._dismiss, None))
        if font is None:
            font = Config().get_font('default')
        self.font = font
        self.item_h: int = 0
        self.text_halign = text_halign
        self.default_item = default_item
        super(Menu, self).__init__(width=0, height=0, **kwargs)

        # Create item widgets
        h = 0
        for i in self.items:
            t = _item_label(i)
            b = Box.xywh(0, h, self.box.width, self.item_h)
            if isinstance(t, str):
                if _item_selected(i):
                    t = '\u2714 ' + t
                w: TextWidget | RichTextWidget = TextWidget(
                    box=b, text_halign=self.text_halign, font=self.font,
                    text=t, parent=self, action=self._item_action)
            else:
                # Rich rows ignore `selected` for now — the checkmark prefix
                # only makes sense on string labels.
                w = RichTextWidget(box=b, segments=t, font=self.font,
                                   h_margin=5, v_margin=1,
                                   parent=self, action=self._item_action)
            # Stash the source item on the widget for `_item_action` to recover.
            setattr(w, 'data', i)
            self.add_sel_widget(w)
            if t == self.default_item:
                self.sel_widget(w)
            h = h + self.item_h

        self.refresh()

    def _scroll_delta(self, box: Box, movex: int, movey: int, orig_box: Box):
        # Vertical movement only, pixel-precise (no page-snap, no y0==0 reset)
        return 0, movey

    def _dismiss(self, arg=None):
        stack = self._get_stack()
        if stack:
            stack.pop_panel(self)

    def _item_action(self, event, source):
        trace(self, "item action !", event, source)
        if event == InputEvent.CLICK or event == InputEvent.LONG_CLICK:
            data = source.data
            action = self.action
            if self.auto_dismiss:
                self._dismiss()
            if action is not None:
                action(event, data)

    def _adjust_box(self):
        trace(self, "menu box adjust, parent=", self.parent)

        # Calculate height and width
        #
        # TODO: Make margins configurable
        #
        # Note: we assume the height of a line is constant. This might be a tad
        # optimistic but it helps getting smooth scrolling.
        #
        # TODO: Re-adjust item widgets here instead of in constructor. Right
        # now we rely on the pass done in the constructor (without a parent)
        # because it calculates item_h which is then use to layout the menu
        # items. But we could just pile them on top of each other and move
        # them once attached.
        #
        w = 240
        v_margin = 0
        # Row height = max across all items so a tall rich row (e.g. a glyph
        # bigger than the text line) doesn't get clipped. Strings measure via
        # get_text_size; rich rows measure each segment.
        _, line_h = get_text_size('', self.font)
        item_h = line_h
        for i in self.items:
            t = _item_label(i)
            if isinstance(t, str):
                _, th = get_text_size(t, self.font)
                th = th + v_margin * 2
            else:
                # Rich rows: 1px top inset, no bottom padding.
                th = max((seg.measure(self.font)[1] for seg in t), default=line_h)
                th = th + 1
            if th > item_h:
                item_h = th
        self.item_h = item_h
        h = item_h * len(self.items)
        mw = self.max_width
        mh = self.max_height
        if mw is not None and w > mw:
            w = 240
        if mh is not None and h > mh:
            # Content taller than viewport: enable JIT paint with a tall backing image
            self.virtual = True
            self._content_height = h
            h = mh
        self.box = Box.xywh(0,0,w,h)
        super(Menu,self)._adjust_box()
