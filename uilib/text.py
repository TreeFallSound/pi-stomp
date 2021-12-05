from math import log
from PIL import ImageFont

from uilib.panel import *
from uilib.misc import *
from uilib.config import *

class LetterSelector(Widget):
    ctrl_BKSP, ctrl_CANCEL, ctrl_OK = 0, 1, 2
    controls = '\u232b\u2718\u2713'
    numbers = '0123456789'
    lo_chars = controls + 'abcdefghijklmnopqrstuvwxyz' + numbers
    hi_chars = controls + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' + numbers
    specials = controls + '`~!@#$%^&*()-_=+[]{}\\|;:\'",<>./?'
    MODE_LO, MODE_HI, MODE_SP = 0,1,2
    charsets = [ lo_chars, hi_chars, specials ]

    def __init__(self, box, font, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(LetterSelector,self).__init__(box, **kwargs)
        self.font = font
        self.l_idx = self.ctrl_CANCEL
        self.__set_mode(self.MODE_LO)

    def __set_mode(self, mode):
        self.mode = mode
        cs = self.charsets[mode]
        mw, mh = 0, 0
        for c in cs:
            w, h = self.font.getsize(c)
            mw = max(mw,w)
            mh = max(mh,h)
        self.l_w = mw
        self.l_h = mh
        self.l_idx %= len(cs)
        self.l_count = self.box.width // self.l_w
        if self.l_count % 1 == 0:
            self.l_count -= 1
        self.l_half = self.l_count // 2

    def _draw(self, image, draw, real_box):
        loc = (real_box.x0 + self.l_w // 2, real_box.y0 + self.l_h // 2)
        cs = self.charsets[self.mode]
        for i in range(self.l_idx - self.l_half, self.l_idx + self.l_half):
            ci = i % len(cs)
            if ci == self.ctrl_OK:
                color = (0,255,0)
            elif ci == self.ctrl_CANCEL:
                color = (255,0,0)
            else:
                color = self.fgnd_color
            if i != self.l_idx:
                a = log(abs(self.l_idx - i) + 1) + 1
                color = (int(color[0]/a),int(color[1]/a),int(color[2]/a))
            draw.text(loc, cs[ci], fill = color, font = self.font, anchor = 'mm')
            loc = (loc[0] + self.l_w, loc[1])

    def _draw_selection(self, image, draw, real_box):
        l = real_box.x0 + self.l_w * self.l_half
        b = Box(l, real_box.y0, l + self.l_w, real_box.y1)
        draw.rounded_rectangle(b.PIL_rect, self.l_w//4, None, self.sel_color, 1)


    def input_event(self, event):
        cs = self.charsets[self.mode]
        if event == InputEvent.RIGHT:
            self.l_idx += 1
            if self.l_idx >= len(cs):
                self.l_idx = 0
            self.refresh()
            return True
        elif event == InputEvent.LEFT:
            self.l_idx -= 1
            if self.l_idx < 0:
                self.l_idx = len(cs) - 1
            self.refresh()
            return True
        elif event == InputEvent.CLICK or event == InputEvent.LONG_CLICK:
            if self.l_idx == self.ctrl_CANCEL:
                self.action(InputEvent.CANCEL, None)
            elif self.l_idx == self.ctrl_OK:
                self.action(InputEvent.OK, None)
            elif self.l_idx == self.ctrl_BKSP:
                if event == InputEvent.LONG_CLICK:
                    self.action(InputEvent.CLEAR, None)
                else:
                    self.action(InputEvent.BACKSPACE, None)
            else:
                if event == InputEvent.LONG_CLICK:
                    self.__set_mode((self.mode + 1) % 3)
                    self.refresh()
                else:
                    self.action(InputEvent.LETTER, self.charsets[self.mode][self.l_idx])
        return False
        
class TextEditor(RoundedPanel):
    def __init__(self, widget):
        self.editable = widget
        stack = widget._get_stack()
        # Better way to do that ?
        #
        # XXX FIXME: Too many hard coded numbers, need some better smarts
        # at calculating text dimensions etc...
        #
        # XXX FIXME: No attributes passed in, figure out what to do there
        #
        # XXX FIXME: Try to use the font passed as argument
        #
        box = Box(0,0,300,80)
        box = box.centre(stack.box)
        super(TextEditor,self).__init__(box = box, parent = stack, auto_destroy = True)
        self.set_outline(2, (255,255,255))
        self.outline = 2
        self.curline = widget.text
        self.font = ImageFont.truetype("DejaVuSans.ttf", 18)
        msg_w, msg_h = self.font.getsize(widget.edit_message)
        msg_box = Box.xywh(10, 10, msg_w, msg_h)
        self.msg = TextWidget(box = msg_box, text = widget.edit_message, font = self.font, parent = self)
        edit_box = Box.xywh(10,30,280,20)
        self.edit = TextWidget(box = edit_box, text = self.curline + '\u2588', font = self.font, parent = self)
        self.edit.set_background((64,64,64))
        sel_box = Box.xywh(10, 50, 280, 22)
        selector = LetterSelector(box = sel_box, font = self.font, parent = self, action = self.__input_action)
        self.add_sel_widget(selector)
        stack.push_panel(self)
        self.refresh()

    def __update(self):
        self.edit.set_text(self.curline + '\u2588')

    def __done(self):
        stack = self._get_stack()
        stack.pop_panel(self)

    def __input_action(self, event, data):
        if event == InputEvent.CANCEL:
            self.__done()
        elif event == InputEvent.BACKSPACE:
            if len(self.curline) > 0:
                self.curline = self.curline[:-1]
        elif event == InputEvent.LETTER:
            self.curline += str(data)
        elif event == InputEvent.CLEAR:
            self.curline = ''
        elif event == InputEvent.OK:
            self.editable.set_text(self.curline)
            if self.editable.action is not None:
                self.editable.action(InputEvent.EDITED, self)
            self.__done()
        self.__update()

# XXX TODO: Add alignment features
class TextWidget(Widget):
    """A simple widget with a text string"""
    def __init__(self, box, text = '', font = None, edit_message = None, h_margin = None, v_margin = None,
                 text_halign = None, **kwargs):
        self.text = text
        if font == None:
            font = Config().get_font('default')
        self.font = font
        self.edit_message = edit_message
        self.h_margin = h_margin
        self.v_margin = v_margin
        self.text_halign = text_halign
        self.font_metrics = font.getmetrics()
        self.text_size_valid = False
        super(TextWidget,self).__init__(box, **kwargs)

    def _get_text_size(self):
        if not self.text_size_valid:
            self.text_w, self.text_h = get_text_size(self.text, self.font, self.font_metrics)
            self.text_size_valid = True
        return (self.text_w, self.text_h)

    def _get_margins(self):
        # If no left margin is specified, use the max of sel_width and outline
        # size ie, the biggest of the selection rectangle and outline
        h_margin = self.h_margin
        v_margin = self.v_margin
        if self.selectable and self.sel_width > self.outline:
            def_margin = self.sel_width
        else:
            def_margin = self.outline
        if h_margin == None:
            h_margin = def_margin
        if v_margin == None:
            v_margin = def_margin

        return (h_margin, v_margin)

    def _adjust_box(self):
        # Auto-sizing feature
        trace(self, "text adjust box, width=", self.box.width, "height=", self.box.height)
        if self.box.width != 0 and self.box.height != 0:
            return
        h_margin, v_margin = self._get_margins()
        tw, th = self._get_text_size()
        # Add outline to account for PIL rectangles being "inset"
        extra = self.outline
        trace(self, "margins=", h_margin, v_margin, "text_size=", tw, th)
        if self.box.width == 0:
            self.box.width = 1.2 * tw + h_margin * 2 + extra
        if self.box.height == 0:
            self.box.height = 1.2 * th + v_margin * 2 + extra
        trace(self, "resulting box=", self.box)
        super(TextWidget,self)._adjust_box()

    def set_text(self, text):
        self.text = text
        self.text_size_valid = False
        self.refresh()

    def set_edit_message(self, message):
        self.edit_message = message

    def set_font(self, font):
        self.font = font
        self.font_metrics = font.getmetrics()
        self.text_size_valid = False
        self.refresh()

    def _draw(self, image, draw, real_box):
        # Draw text
        #
        # XXX TODO: Handle cropping etc... (using continuation characters ?)
        # Should we use a local image & support scroll ? basically make this a
        # ContainerWidget subclass ? For now assume it fits ...
        #
        h_margin, v_margin = self._get_margins()
        tw, th = self._get_text_size()
        extra = self.outline
        hroom = real_box.width - h_margin - extra
        vroom = real_box.height - v_margin - extra
        if hroom < 0 or vroom < 0:
            return
        if tw > hroom:
            tw = hroom
        if th > vroom:
            th = vroom
        if self.text_halign == TextHAlign.LEFT:
            hoffset = 0
        elif self.text_halign == TextHAlign.RIGHT:
            hoffset = hroom - tw
        else:
            hoffset = int((hroom - tw) / 2)
        loc = (real_box.x0 + h_margin + hoffset, real_box.y0 + v_margin)
        draw.text(loc, self.text, fill = self.fgnd_color, font = self.font)

    def input_event(self, event):
        if self.edit_message is not None:
            if event == InputEvent.CLICK or event == InputEvent.LONG_CLICK:
                TextEditor(self)
                return True
        super(TextWidget,self).input_event(event)
        
class Button(TextWidget):
    def __init__(self, **kwargs):
        self.outline_radius = self._get_arg(kwargs, 'outline_radius', 5)
        self.outline = self._get_arg(kwargs, 'outline', 1)
        self.sel_width = self._get_arg(kwargs, 'sel_width', 2)
        super(Button,self).__init__(**kwargs)
