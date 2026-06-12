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

from uilib.dialog import *
from uilib.text import *
import common.util as util
import common.parameter as Parameter

import numpy as np
import time

class Parameterdialog(Dialog):
    def __init__(self, stack, parameter,
                 width, height, title, title_font=None, timeout=None, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(Parameterdialog,self).__init__(width, height, title, title_font, **kwargs)
        self.stack = stack  # TODO very LAME to require the stack to be passed, ideally panel would be able to pop itself
        self.parameter: Parameter = parameter
        
        # adjustment amount per click
        if self.parameter.type in (Parameter.Type.INTEGER, Parameter.Type.ENUMERATION, Parameter.Type.TOGGLED):
            self.parameter_tweak_amount = 1
        else:
            self.parameter_tweak_amount = 8

        self.tweak = util.renormalize_float(self.parameter_tweak_amount, 0, 127, self.parameter.minimum, self.parameter.maximum)

        self.timeout = timeout
        self.expiry_time = None
        if self.timeout:
            self.reset_timeout()

        # "graph" are the y-scaled values, "actual" are the actual non-scaled values
        self.taper = self.parameter.get_taper()  # Derive from parameter type
        self.num_actual = 256  # High resolution for better stepping
        self.num_points = 60
        self.bar_width = 4
        self.actual_abscissa = np.linspace(0, self.num_actual, self.num_actual)
        self.graph_abscissa = np.linspace(1, self.num_points, self.num_points)
        self.actual_points = self._calc_graph_points(self.actual_abscissa, self.parameter.minimum, self.parameter.maximum)
        self.graph_points  = self._calc_graph_points(self.graph_abscissa, 0, self.num_points)  # TODO

        self.w_value = None
        self.w_bars = []  # Reusable bar widgets
        self.last_param_value = None  # Track previous value for incremental bar updates
        self._draw_contents()

    def _calc_graph_points(self, x, min, max):
        # Calculate the y-values using a logarithmic function
        points = min + (max - min) * ((x / len(x)) ** self.taper)
        return points

    def _draw_contents(self):
        # Always draw close button, even if using timeout autoclose
        b = TextWidget(box=Box.xywh(108, 100, 0, 0), text='Close', parent=self, outline=1, sel_width=3,
                       outline_radius=5, align=WidgetAlign.NONE, name='ok_btn')
        b.set_selected(True)
        self._draw_graph()

    def _update_text_widget(self):
        y0 = 80
        val_text = self.parameter.format(self.parameter.value)
        min_text = self.parameter.format(self.parameter.minimum)
        max_text = self.parameter.format(self.parameter.maximum)

        # Calculate centered position
        font = Config().get_font('default')
        text_width, text_height = get_text_size(val_text, font)
        x_centered = (self.box.width - text_width) // 2

        if self.w_value is None:
            self.w_value = TextWidget(box=Box.xywh(x_centered, 23, text_width, text_height), text=val_text, parent=self,
                       align=WidgetAlign.NONE, name='value')
            self.w_value.set_foreground('yellow')
            TextWidget(box=Box.xywh(0, y0, 0, 0), text=min_text, parent=self, outline=0,
                       align=WidgetAlign.NONE, name='value')
            TextWidget(box=Box.xywh(220, y0, 0, 0), text=max_text, parent=self, outline=0,
                       align=WidgetAlign.NONE, name='value')
        else:
            # Update text (refreshes old box area)
            self.w_value.set_text(val_text)
            # Update box position and width (realign=True) without triggering full parent refresh
            self.w_value.set_box(Box.xywh(x_centered, 23, text_width, text_height), realign=True, refresh=False)
            # Refresh new box area
            self.w_value.refresh()

    def _draw_graph(self):
        # TODO detailed dimensions, colors, etc. should not be defined in uilib
        y0 = 80
        x_offset = 10

        self._update_text_widget()

        # Create bar widgets on first call, reuse them afterward
        if not self.w_bars:
            x = 0
            for i in self.graph_abscissa:
                i = int(i) - 1  # abscissa start at 1, arrays start at 0
                g = int(self.graph_points[i])  # PIL requires integer coordinates
                line_box = Box.xywh(x + x_offset, y0 - g, self.bar_width, g)
                w = Widget(box=line_box, parent=self, outline=1, sel_width=0, outline_radius=0,
                           align=WidgetAlign.NONE)
                self.w_bars.append(w)
                x = x + self.bar_width

            # First render: set all bar colors and do full refresh
            for idx, i in enumerate(self.graph_abscissa):
                i = int(i) - 1
                a = int(i * self.num_actual / self.num_points)
                p = float(self.actual_points[a])
                if p <= self.parameter.value:
                    self.w_bars[idx].set_foreground('yellow')
                else:
                    self.w_bars[idx].set_foreground((100, 100, 240))
            self.refresh()  # Full dialog refresh on first render
            self.last_param_value = self.parameter.value
        else:
            # Incremental update: only refresh bars that changed state
            items = list(enumerate(self.graph_abscissa))
            if self.parameter.value < self.last_param_value:
                items = reversed(items)

            for idx, i in items:
                i = int(i) - 1
                a = int(i * self.num_actual / self.num_points)
                p = float(self.actual_points[a])

                # Determine if this bar should be filled
                old_filled = p <= self.last_param_value
                new_filled = p <= self.parameter.value

                # Only update and refresh if state changed
                if old_filled != new_filled:
                    if new_filled:
                        self.w_bars[idx].set_foreground('yellow')
                    else:
                        self.w_bars[idx].set_foreground((100, 100, 240))
                    self.w_bars[idx].refresh()

            self.last_param_value = self.parameter.value

    def reset_timeout(self):
        if self.timeout is not None:
            self.expiry_time = time.time() + self.timeout

    def tick(self):
        if self.expiry_time and time.time() > self.expiry_time:
            self.pop()

    def update_value(self, new_value: float) -> None:
        """Update display with new value (controller already calculated it)."""
        self.reset_timeout()
        self.parameter.value = new_value
        self._update_text_widget()
        self._draw_graph()

    def parameter_value_change(self, direction):
        self.reset_timeout()

        # Calculate new value
        new_value = self.parameter.value + (direction * self.tweak)

        # Clamp
        if new_value > self.parameter.maximum:
            new_value = self.parameter.maximum
        if new_value < self.parameter.minimum:
            new_value = self.parameter.minimum

        # Integer rounding
        if self.parameter.type in (Parameter.Type.INTEGER, Parameter.Type.ENUMERATION, Parameter.Type.TOGGLED):
            new_value = round(new_value)

        if new_value == self.parameter.value:
            return

        self.parameter.value = new_value
        if self.action is not None:
            self.action(self.object, new_value)
        self._draw_graph()

    def input_event(self, event):
        if event == InputEvent.CLICK:
            self.pop()
        elif event == InputEvent.LEFT:
            self.parameter_value_change(-1)
        elif event == InputEvent.RIGHT:
            self.parameter_value_change(1)

    def pop(self):
        if self.parent:
            self.stack.pop_panel(self)
        self.expiry_time = None
