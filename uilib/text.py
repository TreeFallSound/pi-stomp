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

from math import log
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

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
            bbox = self.font.getbbox(c)
            w, h = bbox[2] - bbox[0], bbox[3]
            mw = max(mw,w)
            mh = max(mh,h)
        self.l_w = mw
        self.l_h = mh
        self.l_idx %= len(cs)
        self.l_count = self.box.width // self.l_w
        if self.l_count % 1 == 0:
            self.l_count -= 1
        self.l_half = self.l_count // 2

    def _draw(self, ctx, frame):
        loc = (frame.x0 + self.l_w // 2, frame.y0 + self.l_h // 2)
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
            ctx.draw.text(loc, cs[ci], fill=color, font=self.font, anchor='mm')
            loc = (loc[0] + self.l_w, loc[1])

    def _draw_selection(self, ctx, frame):
        l = frame.x0 + self.l_w * self.l_half
        b = Box(l, frame.y0, l + self.l_w, frame.y1)
        ctx.draw.rounded_rectangle(b.PIL_rect, self.l_w//4, None, self.sel_color, 1)


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
        bbox = self.font.getbbox(widget.edit_message)
        msg_w, msg_h = bbox[2] - bbox[0], bbox[3]
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
    def __init__(self, box, text='', prompt=None, font = None, edit_message = None, h_margin = None, v_margin = None,
                 text_halign = None, **kwargs):
        self.text = text
        self.prompt = prompt
        if font == None:
            font = Config().get_font('default')
        self.font = font
        self.edit_message = edit_message
        self.h_margin = h_margin
        self.v_margin = v_margin
        self.text_halign = text_halign
        self.font_metrics = font.getmetrics()
        self.text_size_valid = False
        # TODO Kindof a hack
        self.prompt_offset = 0
        if self.prompt is not None:
            w, h = get_text_size(self.prompt, self.font, self.font_metrics)
            box.x0 += w
            box.x1 += w
            self.prompt_offset = w
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
        # For height, always use at least a full line height so empty-text
        # widgets don't collapse to near-zero.
        ascent, descent = self.font_metrics
        th = max(th, ascent + descent)
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
        if self.text == text:
            return
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

    SPLIT_SEP = '\u001F'  # if present in text exactly once, render as left + right halves

    def _draw(self, ctx, frame):
        h_margin, v_margin = self._get_margins()
        extra = self.outline
        hroom = frame.width - h_margin - extra
        vroom = frame.height - v_margin - extra
        if hroom < 0 or vroom < 0:
            return

        if self.SPLIT_SEP in self.text:
            parts = self.text.split(self.SPLIT_SEP)
            if len(parts) != 2:
                raise ValueError("TextWidget split text must contain exactly one separator")
            left, right = parts
            lw, lh = get_text_size(left, self.font, self.font_metrics)
            rw, rh = get_text_size(right, self.font, self.font_metrics)
            th = max(lh, rh)
            if th > vroom:
                th = vroom
            y = frame.y0 + v_margin
            # Extra padding for split rows so the right half doesn't hug the edge.
            split_pad = 3
            ctx.draw.text((frame.x0 + h_margin + split_pad, y), left, fill=self.fgnd_color, font=self.font)
            ctx.draw.text((frame.x0 + frame.width - h_margin - extra - split_pad - rw, y),
                          right, fill=self.fgnd_color, font=self.font)
            return

        tw, th = self._get_text_size()
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
        loc = (frame.x0 + h_margin + hoffset, frame.y0 + v_margin)
        if self.prompt is not None:
            ctx.draw.text((0, loc[1]), self.prompt, fill=self.fgnd_color, font=self.font)
        ctx.draw.text(loc, self.text, fill=self.fgnd_color, font=self.font)

    def tick(self):
        """Override in subclasses for animation."""
        pass

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


class ScrollingText(TextWidget):
    """TextWidget with horizontal ping-pong scrolling for overflow text."""

    def __init__(self, pixels_per_second: float = 50.0, pause_start_sec: float = 2.0, pause_end_sec: float = 1.0, lcd_poll_divisor: int = 8, **kwargs):
        super().__init__(**kwargs)
        self.pixels_per_second: float = pixels_per_second
        self.pause_start_sec: float = pause_start_sec
        self.pause_end_sec: float = pause_end_sec

        # Calculate duration of one tick in seconds (base loop sleep is 10ms = 0.01s)
        self.tick_duration_sec: float = (10 * lcd_poll_divisor) / 1000.0

        # Scrolling state
        self.scroll_offset: int = 0
        self._float_scroll_offset: float = 0.0
        self.scroll_direction: int = 1  # 1 = scroll left, -1 = scroll right
        self.pause_counter_sec: float = pause_start_sec

        # Cached rendering
        self.cached_text_image: Optional[Image.Image] = None
        self.cached_text_width: int = 0

    def _render_text_to_cache(self) -> None:
        """Pre-render full text to a PIL Image for efficient scrolling."""
        if self.text is None or len(self.text) == 0:
            self.cached_text_image = None
            self.cached_text_width = 0
            return

        tw, th = self._get_text_size()
        self.cached_text_width = tw

        self.cached_text_image = Image.new('RGB', (tw, th), self.bkgnd_color)
        draw = ImageDraw.Draw(self.cached_text_image)
        draw.text((0, 0), self.text, fill=self.fgnd_color, font=self.font)

    def _should_scroll(self) -> bool:
        if self.cached_text_image is None:
            return False
        h_margin, _ = self._get_margins()
        available_width = self.box.width - h_margin - self.outline
        return self.cached_text_width > available_width

    def tick(self) -> None:
        if self.cached_text_image is None:
            self._render_text_to_cache()

        if not self._should_scroll():
            if self.scroll_offset != 0:
                self.scroll_offset = 0
                self._float_scroll_offset = 0.0
                self.scroll_direction = 1
                self.pause_counter_sec = self.pause_start_sec
                self.refresh()
            return

        if self.pause_counter_sec > 0:
            self.pause_counter_sec -= self.tick_duration_sec
            return

        h_margin, _ = self._get_margins()
        available_width = self.box.width - 2 * h_margin - self.outline
        max_offset = self.cached_text_width - available_width

        old_offset = self.scroll_offset
        move_amount = self.pixels_per_second * self.tick_duration_sec
        self._float_scroll_offset += self.scroll_direction * move_amount
        self.scroll_offset = int(self._float_scroll_offset)

        if self.scroll_offset >= max_offset:
            self.scroll_offset = max_offset
            self._float_scroll_offset = float(max_offset)
            self.scroll_direction = -1
            self.pause_counter_sec = self.pause_end_sec
        elif self.scroll_offset <= 0:
            self.scroll_offset = 0
            self._float_scroll_offset = 0.0
            self.scroll_direction = 1
            self.pause_counter_sec = self.pause_start_sec

        if self.scroll_offset != old_offset:
            self.refresh()

    def _clear_cache_and_restart(self) -> None:
        self.cached_text_image = None
        self.scroll_offset = 0
        self._float_scroll_offset = 0.0
        self.scroll_direction = 1
        self.pause_counter_sec = self.pause_start_sec

    def set_text(self, text: str) -> None:
        super().set_text(text)
        self._clear_cache_and_restart()

    def set_font(self, font: ImageFont.FreeTypeFont) -> None:
        super().set_font(font)
        self._clear_cache_and_restart()

    def _draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, real_box) -> None:
        if self.cached_text_image is None:
            self._render_text_to_cache()
        if self.cached_text_image is None:
            return

        h_margin, v_margin = self._get_margins()
        tw, th = self._get_text_size()
        extra = self.outline
        hroom = real_box.width - h_margin - extra
        vroom = real_box.height - v_margin - extra

        if hroom <= 0 or vroom <= 0:
            return

        if not self._should_scroll():
            if self.text_halign == TextHAlign.LEFT:
                hoffset = 0
            elif self.text_halign == TextHAlign.RIGHT:
                hoffset = hroom - tw
            else:
                hoffset = int((hroom - tw) / 2)
            x_pos = real_box.x0 + h_margin + hoffset
            y_pos = real_box.y0 + v_margin
            crop_box = (0, 0, tw, th)
            image.paste(self.cached_text_image.crop(crop_box), (x_pos, y_pos))
        else:
            x_pos = real_box.x0 + h_margin
            y_pos = real_box.y0 + v_margin
            crop_width = min(hroom, self.cached_text_width - self.scroll_offset)
            crop_box = (self.scroll_offset, 0, self.scroll_offset + crop_width, th)
            image.paste(self.cached_text_image.crop(crop_box), (x_pos, y_pos))
