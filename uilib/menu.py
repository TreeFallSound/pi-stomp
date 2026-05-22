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

from typing import Any, Callable

from uilib.box import Box
from uilib.config import Config
from uilib.dialog import Dialog
from uilib.misc import InputEvent, TextHAlign, get_text_size, trace
from uilib.text import TextWidget

# A menu row label. `str` for now; the RichTextWidget step widens this to
# `str | Sequence[Segment]`.
Label = str

# Action stored in slot 1 of a `MenuItem`. The menu framework never invokes
# this directly — the per-item callable is decorative context that the
# menu-level `action` callback unpacks from `data` at click time. Typed
# loosely (any signature) so existing callers (`self._dismiss`, bound methods
# with mismatched arities) keep type-checking.
MenuAction = Callable[..., Any]

# Menu items are positional tuples — callers construct them inline as
# `(label, action, arg)` or `(label, action, arg, selected)`. We keep tuples
# (rather than a NamedTuple) so callsites stay unchanged; accessors below
# give the constructor named reads.
MenuItem = (
    tuple[Label, MenuAction | None, Any]
    | tuple[Label, MenuAction | None, Any, bool]
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
        super(Menu,self).__init__(width = 0, height = 0, **kwargs)

        # Create item widgets
        h = 0
        for i in self.items:
            t = _item_label(i)
            if _item_selected(i):
                t = '\u2714 ' + t
            b = Box.xywh(0, h, self.box.width, self.item_h)
            w = TextWidget(box = b, text_halign = self.text_halign, font = self.font,
                           text = t, parent = self, action = self._item_action)
            # Stash the source item on the widget for `_item_action` to recover.
            # TextWidget has no `data` field declared — set via setattr.
            setattr(w, 'data', i)
            self.add_sel_widget(w)
            if t == self.default_item:
                self.sel_widget(w)
            h = h + self.item_h

        self.refresh()

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
        h = 0
        h_margin = 10
        v_margin = 0
        for i in self.items:
            t = _item_label(i)
            tw, th = get_text_size(t, self.font)
            trace(self, "item <",t,"> tw=", tw, "th=", th)
            tw = tw + h_margin * 2
            th = th + v_margin * 2
            if h == 0:
                self.item_h = th
                h = th * len(self.items)
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
