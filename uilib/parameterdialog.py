from uilib.dialog import *
from uilib.text import *
import common.util as util


class Parameterdialog(Dialog):
    def __init__(self, stack, param_name, param_value, param_min, param_max,
                 width, height, title, title_font=None, **kwargs):
        super(Parameterdialog,self).__init__(width, height, title, title_font, **kwargs)
        self.stack = stack  # TODO very LAME to require the stack to be passed, ideally panel would be able to pop itself
        self.param_name = param_name
        self.param_value = param_value
        self.param_min = param_min
        self.param_max = param_max

        # adjustment amount per click
        self.parameter_tweak_amount = 8
        self.tweak = util.renormalize_float(self.parameter_tweak_amount, 0, 127, self.param_min, self.param_max)

        self._draw_contents()

    def _draw_contents(self):
        b = TextWidget(box=Box.xywh(108, 100, 0, 0), text='Close', parent=self, outline=1, sel_width=3, outline_radius=5,
                       align=WidgetAlign.NONE, name='ok_btn')
        b.set_selected(True)
        self._draw_graph()

    def _draw_graph(self):
        # TODO detailed dimensions, colors, etc. should not be defined in uilib
        y0 = 80
        graph_width = 220
        x_offset = 22
        xpitch = 4
        x = 0
        h = 0
        val = util.renormalize(self.param_value, self.param_min, self.param_max, 0, graph_width)
        v = TextWidget(box=Box.xywh(118, 26, 0, 0), text=util.format_float(self.param_value), parent=self,
                       align=WidgetAlign.NONE, name='value')
        v.set_foreground('yellow')
        TextWidget(box=Box.xywh(0, y0, 0, 0), text=util.format_float(self.param_min), parent=self, outline=0,
                   align=WidgetAlign.NONE, name='value')
        TextWidget(box=Box.xywh(220, y0, 0, 0), text=util.format_float(self.param_max), parent=self, outline=0,
                   align=WidgetAlign.NONE, name='value')

        # TODO draw line/rect directly instead of widget
        while x < graph_width:
            line_box = Box.xywh(x + x_offset, y0 - h, 1, h)
            w = Widget(box=line_box, parent=self, outline=1, sel_width=0, outline_radius=0,
                       align=WidgetAlign.NONE)
            if (x <= val) and (x % xpitch) == 0:
                w.set_foreground('yellow')
            else:
                w.set_foreground((100, 100, 240))
            x = x + xpitch
            h = h + 1

        self.refresh()

    def parameter_value_change(self, direction):
        value = float(self.param_value)
        new_value = round(((value - self.tweak) if (direction != 1) else (value + self.tweak)), 2)
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
            self.stack.pop_panel(self)
        elif event == InputEvent.LEFT:
            self.parameter_value_change(-1)
        elif event == InputEvent.RIGHT:
            self.parameter_value_change(1)



