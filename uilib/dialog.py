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

import functools
import textwrap
from typing_extensions import override

import pygame

from uilib.box import Box
from uilib.radius import Radius
from uilib.config import Config
from uilib.panel import PanelDecorator, RoundedPanel
from uilib.text import TextWidget
from uilib.misc import WidgetAlign, TextHAlign, get_text_size, trace


class DialogDecorator(PanelDecorator):
    def __init__(self, panel, title, title_font, **kwargs):
        # Dialog comes with standard defaults
        kwargs["outline"] = self._get_arg(kwargs, "outline", 2)
        kwargs["outline_radius"] = self._get_arg(kwargs, "outline_radius", 10)
        kwargs["outline_color"] = self._get_arg(kwargs, "outline_color", (255, 255, 255))
        kwargs["bkgnd_color"] = self._get_arg(kwargs, "bkgnd_color", Config().get_color("default_title_bkgnd"))
        title_color = self._get_arg(kwargs, "title_color", Config().get_color("default_title_fgnd"))
        super(DialogDecorator, self).__init__(panel, **kwargs)
        self.title = TextWidget(
            box=None, text_halign=TextHAlign.CENTRE, text=title, font=title_font, parent=self, fgnd_color=title_color
        )

    def _adjust_box(self):
        trace(self, "DialogDecorator adjusting box ! pb=", self.panel.box)
        pb = self.panel.box

        # Outline width
        o = self.outline
        # Extra margin due to rounded corners (adjust with outline width ?)
        m = o
        # Extra margin around text
        tmargin = 2

        self.tw, self.th = get_text_size(self.title.text, self.title.font, self.title.font_metrics)
        self.box = Box(pb.x0 - m, pb.y0 - self.th - m - tmargin, pb.x1 + m, pb.y1 + m)
        trace(self, "new box=", self.box)
        tbox = Box(o, o, self.box.width - o, self.th + o)
        self.title.set_box(tbox, refresh=False)
        self.title.show(refresh=False)

    @override
    def _draw_erase(self, ctx):
        # Paint only the titlebar strip — the panel body owns its own pixels,
        # and filling under it would leak through any transparent areas.
        titlebar_h = self.panel.box.y0 - self.box.y0  # decorator-local
        strip = Box(0, 0, self.box.width, titlebar_h)
        ctx.draw_rectangle(strip, fill=self.bkgnd_color, radius=Radius.top(self.outline_radius))

    def _draw(self, ctx):
        trace(self, "DialogDecorator draw, self.box=", self.box)
        y = self.th + 1
        # The +2 here is magic ... need to figure out what's up, otherwise we get only 1 pixel
        ctx.draw_line(((0, y), (ctx.width - self.outline, y)), fill=self.fgnd_color, width=self.outline + 2)


class Dialog(RoundedPanel):
    """A pop-up dialog with a title decorator.

    Only the BOTTOM corners are rounded on the panel itself — the titlebar
    decorator sits above with its own rounded top, so the panel's top corners
    must stay square (otherwise we'd clip the top of the first content widget).
    """

    # nudge the whole dialog down if it's close to full height
    _TRUE_CENTER_MIN_HEIGHT = 190

    def __init__(self, width, height, title, title_font=None, **kwargs):
        box = Box.xywh(0, 0, width, height)
        radius = 10
        if title_font is None:
            title_font = Config().get_font("default_title")
        self._title_strip_h = get_text_size(title, title_font)[1] + 2
        deco = functools.partial(DialogDecorator, title=title, title_font=title_font, outline_radius=radius)
        super(Dialog, self).__init__(box=box, align=WidgetAlign.CENTRE, radius=radius, decorator=deco, **kwargs)

    def _adjust_box(self):
        super()._adjust_box()
        if (
            self.align & WidgetAlign.CENTRE_V
            and self.box is not None
            and self.box.height >= self._TRUE_CENTER_MIN_HEIGHT
        ):
            offset = self._title_strip_h / 2
            self.box.y0 += offset
            self.box.y1 += offset

    @override
    def _build_shape_mask(self) -> pygame.Surface:
        # Only the bottom corners round — the titlebar decorator owns the top
        # corners and the panel's top edge must stay square to meet it
        # seamlessly.
        size = (int(self.box.width), int(self.box.height))
        mask = pygame.Surface(size, pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        pygame.draw.rect(
            mask,
            (255, 255, 255, 255),
            pygame.Rect(0, 0, size[0], size[1]),
            0,
            **Radius.bottom(self.radius).as_pygame_kwargs(),
        )
        return mask

    def tick(self) -> None:
        pass


class MessageDialog(Dialog):
    def __init__(self, panelstack, message, title="Error", width=200, height=90):
        super(MessageDialog, self).__init__(width=width, height=height, title=title, auto_destroy=True)

        char_w = Config().get_font("default_title").get_rect("a").width
        chars_per_line = width // max(1, int(char_w))
        chunks = textwrap.wrap(message, width=chars_per_line)
        wrapped = "\n".join(chunks)

        t = TextWidget(
            box=Box.xywh(5, 0, width - 10, 50),
            text=wrapped,
            parent=self,
            outline=0,
            sel_width=0,
            align=WidgetAlign.NONE,
        )
        self.add_widget(t)
        b = TextWidget(
            box=Box.xywh(int((width / 2) - 20), height - 30, 0, 0),
            text="Ok",
            parent=self,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=lambda x, y: panelstack.pop_panel(self),
            align=WidgetAlign.NONE,
            name="ok_btn",
        )
        self.add_sel_widget(b)
        self.sel_widget(b)


class ConfirmDialog(Dialog):
    """Two-button confirmation dialog: Cancel (left, default focus) and a confirm action (right)."""

    def __init__(
        self,
        panelstack,
        message,
        title="Confirm",
        on_confirm=None,
        width=220,
        height=88,
        confirm_text="Confirm",
        cancel_text="Cancel",
    ):
        super(ConfirmDialog, self).__init__(width=width, height=height, title=title, auto_destroy=True)

        t = TextWidget(
            box=Box.xywh(5, 2, width - 10, height - 42),
            text=message,
            parent=self,
            outline=0,
            sel_width=0,
            align=WidgetAlign.NONE,
        )
        self.add_widget(t)

        btn_w = (width - 15) // 2

        cancel = TextWidget(
            box=Box.xywh(5, height - 32, btn_w, 0),
            text=cancel_text,
            parent=self,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=lambda x, y: panelstack.pop_panel(self),
            align=WidgetAlign.NONE,
            name="cancel_btn",
        )
        self.add_sel_widget(cancel)

        def _confirm(x, y):
            panelstack.pop_panel(self)
            if on_confirm:
                on_confirm()

        confirm_btn = TextWidget(
            box=Box.xywh(10 + btn_w, height - 32, btn_w, 0),
            text=confirm_text,
            parent=self,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=_confirm,
            align=WidgetAlign.NONE,
            name="confirm_btn",
        )
        self.add_sel_widget(confirm_btn)
        self.sel_widget(cancel)  # default focus on Cancel
