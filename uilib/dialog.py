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

from uilib.panel import *
from uilib.text import *

class DialogDecorator(PanelDecorator):
    def __init__(self, panel, title, title_font, **kwargs):
        # Dialog comes with standard defaults
        kwargs['outline'] = self._get_arg(kwargs, 'outline', 2)
        kwargs['outline_radius'] = self._get_arg(kwargs, 'outline_radius', 10)
        kwargs['outline_color'] = self._get_arg(kwargs, 'outline_color', (255,255,255))
        kwargs['bkgnd_color'] = self._get_arg(kwargs, 'bkgnd_color', Config().get_color('default_title_bkgnd'))
        title_color = self._get_arg(kwargs, 'title_color', Config().get_color('default_title_fgnd'))
        super(DialogDecorator,self).__init__(panel, **kwargs)
        self.title = TextWidget(box = None, text_halign = TextHAlign.CENTRE,
                                text = title, font = title_font, parent = self,
                                fgnd_color = title_color)

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
        self.box = Box(pb.x0 - m, pb.y0 - self.th - m - tmargin,
                       pb.x1 + m, pb.y1 + m)
        trace(self, "new box=", self.box)
        tbox = Box(o, o, 16 + self.box.width - o, self.th + o)
        self.title.set_box(tbox, refresh = False)
        self.title.show(refresh = False)

    def _draw(self, image, draw, real_box):
        trace(self, "DialogDecorator draw, real_box=", real_box, "self.box=", self.box)
        line_xy = (real_box.x0, real_box.y0 + self.th + 1,
                   real_box.x1 - self.outline, real_box.y0 + self.th + 1)
        # The +2 here is magic ... need to figure out what's up, otherwise we get only 1 pixel
        draw.line(line_xy, fill=self.fgnd_color, width=self.outline + 2)

class Dialog(Panel):
    def __init__(self, width, height, title, title_font = None, **kwargs):
        box = Box.xywh(0, 0, width, height)
        # Fixed radius for now
        radius = 10
        if title_font == None:
            title_font = Config().get_font('default_title')
        deco = functools.partial(DialogDecorator, title = title, title_font = title_font, outline_radius = radius)
        if 'mask_format' not in kwargs:
            kwargs['mask_format'] = '1'
        super(Dialog,self).__init__(box = box, align = WidgetAlign.CENTRE, radius = radius,
                                    decorator = deco, **kwargs)
        # Setup mask
        mdraw = ImageDraw.Draw(self.mask)
        # Base is a rounded rectangle
        b = self.box.norm()
        mdraw.rounded_rectangle(b.PIL_rect, radius, 1, None, 0)
        # Fill up the top corners
        b.height = int(b.height / 2)
        mdraw.rectangle(b.PIL_rect, 1, None, 0)

class MessageDialog(Dialog):
    def __init__(self, panelstack, message, title="Error", width=200, height=90):
        super(MessageDialog, self).__init__(width=width, height=height, title=title, auto_destroy=True)

        chars_per_line = width // int(Config().get_font('default_title').getsize("a")[0])
        chunks = textwrap.wrap(message, width=chars_per_line)
        wrapped = '\n'.join(chunks)

        t = TextWidget(box=Box.xywh(5, 0, width-10, 50), text=wrapped, parent=self, outline=0, sel_width=0,
                       align=WidgetAlign.NONE)
        self.add_widget(t)
        b = TextWidget(box=Box.xywh(int((width/2)-20), height-30, 0, 0), text='Ok', parent=self, outline=1,
                       sel_width=3, outline_radius=5, action=lambda x, y: panelstack.pop_panel(self),
                       align=WidgetAlign.NONE, name='ok_btn')
        self.add_sel_widget(b)
        self.sel_widget(b)