from uilib.dialog import *
from uilib.text import *
import common.util as util

import numpy as np
import threading
import traceback

class Parameterdialog(Dialog):
    def __init__(self, stack, param_name, param_value, param_min, param_max,
                 width, height, title, title_font=None, timeout=None, taper=1, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(Parameterdialog,self).__init__(width, height, title, title_font, **kwargs)
        self.stack = stack  # TODO very LAME to require the stack to be passed, ideally panel would be able to pop itself
        self.param_name = param_name
        self.param_value = param_value
        self.param_min = param_min
        self.param_max = param_max

        # adjustment amount per click
        self.parameter_tweak_amount = 8
        self.tweak = util.renormalize_float(self.parameter_tweak_amount, 0, 127, self.param_min, self.param_max)

        self.timeout = timeout
        self.timer = None

        # "graph" are the y-scaled values, "actual" are the actual non-scaled values
        self.taper = taper  # 1 linear, 2 or 3 good for logarithmic
        self.points_per_actual = 4
        self.num_points = 60  # Must be a multiple of points_per_actual
        self.num_actual = int(self.num_points / self.points_per_actual)
        self.actual_abscissa = np.linspace(0, self.num_actual, self.num_actual)
        self.graph_abscissa = np.linspace(1, self.num_points, self.num_points)
        self.actual_points = self._calc_graph_points(self.actual_abscissa, self.param_min, self.param_max)
        self.graph_points  = self._calc_graph_points(self.graph_abscissa, 0, self.num_points)  # TODO

        self.w_value = None
        self._draw_contents()

    def _calc_graph_points(self, x, min, max):
        # Calculate the y-values using a logarithmic function
        points = min + (max - min) * ((x / len(x)) ** self.taper)
        return points

    def _draw_contents(self):
        if self.timeout is None:
            # Only draw close button if not using timeout autoclose
            b = TextWidget(box=Box.xywh(108, 100, 0, 0), text='Close', parent=self, outline=1, sel_width=3,
                           outline_radius=5, align=WidgetAlign.NONE, name='ok_btn')
            b.set_selected(True)
        self._draw_graph()

    def _draw_graph(self):
        # TODO detailed dimensions, colors, etc. should not be defined in uilib
        y0 = 80
        x_offset = 10
        val_text = util.format_float(self.param_value)
        if self.w_value is None:
            self.w_value = TextWidget(box=Box.xywh(118, 20, 0, 0), text=val_text, parent=self,
                       align=WidgetAlign.NONE, name='value')
            self.w_value.set_foreground('yellow')
            TextWidget(box=Box.xywh(0, y0, 0, 0), text=util.format_float(self.param_min), parent=self, outline=0,
                       align=WidgetAlign.NONE, name='value')
            TextWidget(box=Box.xywh(220, y0, 0, 0), text=util.format_float(self.param_max), parent=self, outline=0,
                       align=WidgetAlign.NONE, name='value')
        else:
            self.w_value.set_text(val_text)

        # TODO would be nice to only redraw the lines that need changing
        x = 0
        for i in self.graph_abscissa:
            i = int(i) - 1  # abscissa start at 1, arrays start at 0
            a = int(np.ceil(i) / self.points_per_actual)
            p = self.actual_points[a]
            g = self.graph_points[i]
            line_box = Box.xywh(x + x_offset, y0 - g, 1, g)
            w = Widget(box=line_box, parent=self, outline=1, sel_width=0, outline_radius=0,
                       align=WidgetAlign.NONE)
            if p <= self.param_value:
                w.set_foreground('yellow')
            else:
                w.set_foreground((100, 100, 240))
            x = x + self.points_per_actual

        self.refresh()

    def parameter_value_change(self, direction):
        if self.timeout is not None:
            # For autoclose, add a timer which eventually pops the dialog.
            # If timer exists, reset via cancel and recreate
            if self.timer is not None:
                self.timer.cancel()
            # The timeout callback (eg. self.pop) will be executed in a separate thread.
            # that thread should not refresh the LCD or else it could cause SPI conflicts between LCD and the MCP ADC
            self.timer = threading.Timer(self.timeout, self.pop)
            self.timer.start()

        # Find the point on the graph for the current param_value, then get the previous or next value
        value = float(self.param_value)
        i = self._find_nearest_element_index(self.actual_points, value)
        new = i-1 if (direction != 1) else i+1
        new_value = self.actual_points[new] if (0 <= new < self.num_actual) else value

        if new_value > self.param_max:
            new_value = self.param_max
        if new_value < self.param_min:
            new_value = self.param_min
        if new_value is value:
            return
        self.param_value = new_value
        if self.action is not None:
            self.action(self.object, new_value)  # This assumes the method signature
        self._draw_graph()  # TODO XXX redrawing with every tweak produces a shit-load of line widgets

    def input_event(self, event):
        if event == InputEvent.CLICK:
            self.pop()
        elif event == InputEvent.LEFT:
            self.parameter_value_change(-1)
        elif event == InputEvent.RIGHT:
            self.parameter_value_change(1)

    def pop(self):
        self.stack.pop_panel(self)
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def _find_nearest_element_index(self, arr, target):
        # binary search of closest value to target within the sorted array
        left = 0
        right = len(arr) - 1
        nearest_index = None
        min_diff = float('inf')

        while left <= right:
            mid = (left + right) // 2
            diff = abs(arr[mid] - target)

            if diff < min_diff:
                min_diff = diff
                nearest_index = mid

            if arr[mid] == target:
                return mid
            elif arr[mid] < target:
                left = mid + 1
            else:
                right = mid - 1

        return nearest_index
