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

import time
from math import log

from typing import Optional, TYPE_CHECKING
from typing_extensions import override
import pygame

from uilib.pygame_init import font as _make_font
from uilib.box import Box
from uilib.widget import Widget
from uilib.panel import RoundedPanel
from uilib.misc import InputEvent, TextHAlign, get_text_size, trace
from uilib.config import Config
from common.color import RectBorder
from uilib.glyphs import RoundedRectGlyph

from common.fonts import font_path

if TYPE_CHECKING:
    import pygame._freetype

CHAR_TO_DISPLAY = {" ": "\u2423"}


class LetterSelector(Widget):
    ctrl_BKSP, ctrl_CANCEL, ctrl_OK = 0, 1, 2
    controls = "\u232b\u2718\u2713"
    numbers = "0123456789"
    lo_chars = controls + "abcdefghijklmnopqrstuvwxyz" + numbers
    hi_chars = controls + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + numbers
    specials = controls + " `~!@#$%^&*()-_=+[]{}\\|;:'\",<>./?"
    MODE_LO, MODE_HI, MODE_SP = 0, 1, 2
    charsets: list[str] = [lo_chars, hi_chars, specials]

    def __init__(self, box, font, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(LetterSelector, self).__init__(box, **kwargs)
        self.font = font
        self.l_idx = self.ctrl_CANCEL
        self.__set_mode(self.MODE_LO)

    def __set_mode(self, mode: int):
        self.mode = mode
        cs = self.charsets[mode]
        mw, mh = 0, 0
        # PIL bbox[3] = asc + max(0, -glyph_min_y). PIL's original code used
        # `font.getbbox(c)[3]` as the per-char height, which equals this.
        # pygame's rect.height alone is 3px too short for non-descender glyphs
        # at 18pt — it would put loc.y 1-2px above where PIL placed it.
        asc = int(self.font.get_sized_ascender())
        for c in cs:
            dc = CHAR_TO_DISPLAY.get(c, c)
            cw, _ = get_text_size(dc, self.font)
            mw = max(mw, cw)
            m = self.font.get_metrics(dc)[0]
            min_y = m[2]
            if min_y >= 0x80000000:
                min_y -= 0x100000000
            ch = asc + max(0, -min_y)
            mh = max(mh, ch)
        self.l_w = mw
        self.l_h = mh
        self.l_idx %= len(cs)
        assert self.box is not None
        self.l_count = self.box.width // self.l_w
        if self.l_count % 1 == 0:
            self.l_count -= 1
        self.l_half = self.l_count // 2

    @override
    def _draw(self, ctx):
        loc = (self.l_w // 2, self.l_h // 2)
        cs = self.charsets[self.mode]
        for i in range(self.l_idx - self.l_half, self.l_idx + self.l_half):
            ci = i % len(cs)
            if ci == self.ctrl_OK:
                color = (0, 255, 0)
            elif ci == self.ctrl_CANCEL:
                color = (255, 0, 0)
            else:
                color = self.fgnd_color
            if i != self.l_idx:
                a = log(abs(self.l_idx - i) + 1) + 1
                color = (int(color[0] / a), int(color[1] / a), int(color[2] / a))
            ch = CHAR_TO_DISPLAY.get(cs[ci], cs[ci])
            ctx.draw_text(loc, ch, fill=color, font=self.font, anchor="mm")
            loc = (loc[0] + self.l_w, loc[1])

    @override
    def _draw_selection(self, ctx):
        l = self.l_w * self.l_half  # noqa: E741
        b = Box(l, 0, l + self.l_w, ctx.height)
        ctx.draw_rectangle(b, None, self.sel_color, 1, radius=self.l_w // 4)

    @override
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
            assert self.action is not None  # always constructed with an action
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
        box = Box(0, 0, 300, 80)
        box = box.centre(stack.box)
        super(TextEditor, self).__init__(box=box, parent=stack, auto_destroy=True)
        self.set_outline(2, (255, 255, 255))
        self.outline = 2
        self.curline = widget.text
        self.font = _make_font(font_path("DejaVuSans.ttf"), 18)
        msg_w, msg_h = get_text_size(widget.edit_message, self.font)
        msg_box = Box.xywh(10, 10, msg_w, msg_h)
        self.msg = TextWidget(box=msg_box, text=widget.edit_message, font=self.font, parent=self)
        edit_box = Box.xywh(10, 30, 280, 20)
        self.edit = TextWidget(box=edit_box, text=self.curline + "\u2588", font=self.font, parent=self)
        self.edit.set_background((64, 64, 64))
        sel_box = Box.xywh(10, 50, 280, 22)
        selector = LetterSelector(box=sel_box, font=self.font, parent=self, action=self.__input_action)
        self.add_sel_widget(selector)
        stack.push_panel(self)
        self.refresh()

    def __update(self):
        self.edit.set_text(self.curline + "\u2588")

    def __done(self):
        stack = self._get_stack()
        assert stack is not None
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
            self.curline = ""
        elif event == InputEvent.OK:
            self.editable.set_text(self.curline)
            if self.editable.action is not None:
                self.editable.action(InputEvent.EDITED, self)
            self.__done()
        self.__update()


# XXX TODO: Add alignment features
class TextWidget(Widget):
    """A simple widget with a text string"""

    SPLIT_SEP = ""  # if present in text exactly once, renders as left + right halves

    font: "pygame._freetype.Font"

    def __init__(
        self, box, text="", font=None, edit_message=None, h_margin=None, v_margin=None, text_halign=None, **kwargs
    ):
        self.text = text
        if font is None:
            font = Config().get_font("default")
        assert font is not None  # the 'default' font is always registered
        self.font = font
        self.edit_message = edit_message
        self.h_margin = h_margin
        self.v_margin = v_margin
        self.text_halign = text_halign
        self.font_metrics = None  # legacy field, pygame.freetype encodes size in get_rect
        self.text_size_valid = False
        super(TextWidget, self).__init__(box, **kwargs)

    def _get_text_size(self):
        if not self.text_size_valid:
            lines = self.text.split("\n")
            if len(lines) == 1:
                self.text_w, self.text_h = get_text_size(self.text, self.font, self.font_metrics)
            else:
                _, line_h = get_text_size("", self.font)
                self.text_w = max(get_text_size(line, self.font, self.font_metrics)[0] for line in lines)
                self.text_h = line_h * len(lines)
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
        if h_margin is None:
            h_margin = def_margin
        if v_margin is None:
            v_margin = def_margin

        return (h_margin, v_margin)

    @override
    def _adjust_box(self):
        # Auto-sizing feature
        assert self.box is not None  # only called once a box is established
        trace(self, "text adjust box, width=", self.box.width, "height=", self.box.height)
        if self.box.width != 0 and self.box.height != 0:
            return
        h_margin, v_margin = self._get_margins()
        tw, th = self._get_text_size()
        # Always use at least a full line height so short / empty text doesn't
        # collapse the widget. pygame's get_text_size('', font) returns
        # (0, asc+desc) — reuse it instead of PIL-style font.getmetrics().
        _, line_h = get_text_size("", self.font)
        th = max(th, line_h)
        # Add outline to account for PIL rectangles being "inset"
        extra = self.outline
        trace(self, "margins=", h_margin, v_margin, "text_size=", tw, th)
        if self.box.width == 0:
            self.box.width = 1.2 * tw + h_margin * 2 + extra
        if self.box.height == 0:
            self.box.height = 1.2 * th + v_margin * 2 + extra
        trace(self, "resulting box=", self.box)
        super(TextWidget, self)._adjust_box()

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
        self.font_metrics = None
        self.text_size_valid = False
        self.refresh()

    @override
    def _draw(self, ctx):
        h_margin, v_margin = self._get_margins()
        extra = self.outline
        hroom = ctx.width - h_margin - extra
        vroom = ctx.height - v_margin - extra
        if hroom < 0 or vroom < 0:
            return

        if self.SPLIT_SEP in self.text:
            parts = self.text.split(self.SPLIT_SEP)
            if len(parts) == 2:
                left, right = parts
                lw, _ = get_text_size(left, self.font)
                rw, _ = get_text_size(right, self.font)
                ctx.draw_text((h_margin, v_margin), left, fill=self.fgnd_color, font=self.font)
                ctx.draw_text((ctx.width - h_margin - rw, v_margin), right, fill=self.fgnd_color, font=self.font)
                return

        lines = self.text.split("\n")
        _, line_h = get_text_size("", self.font)
        y = v_margin
        for line in lines:
            tw, _ = get_text_size(line, self.font)
            if tw > hroom:
                tw = hroom
            if self.text_halign == TextHAlign.LEFT:
                hoffset = 0
            elif self.text_halign == TextHAlign.RIGHT:
                hoffset = hroom - tw
            else:
                hoffset = int((hroom - tw) / 2)
            ctx.draw_text((h_margin + hoffset, y), line, fill=self.fgnd_color, font=self.font)
            y += line_h
            if y >= v_margin + vroom:
                break

    def tick(self):
        """Override in subclasses for animation."""
        pass

    @override
    def input_event(self, event):
        if self.edit_message is not None:
            if event == InputEvent.CLICK or event == InputEvent.LONG_CLICK:
                TextEditor(self)
                return True
        return super(TextWidget, self).input_event(event)


class Button(TextWidget):
    def __init__(self, **kwargs):
        self.outline_radius = self._get_arg(kwargs, "outline_radius", 5)
        self.outline = self._get_arg(kwargs, "outline", 1)
        self.sel_width = self._get_arg(kwargs, "sel_width", 2)
        super(Button, self).__init__(**kwargs)


class PluginTile(TextWidget):
    """TextWidget for plugin grid tiles.

    Renders fill + border through a single RoundedRectGlyph so the body
    and outline share the same analytic-AA pass (and the same LRU
    cache) as every other rounded rect in the UI. The whole tile is
    drawn in ``_draw_erase`` (below the text) — fill and border
    together, not composited — so there is no gap or overlap at the
    corners and the AA is continuous across both.

    A custom ``border`` can be passed to override the per-side colors
    (e.g. for NAM's tri-color palette).  When ``None``, the border
    uses ``outline_color`` for all four sides, or is omitted entirely
    when ``outline_color`` is ``None`` (the active-tile case where the
    body fill is the only visual element).

    ``backdrop`` is the color the tile floats on (the host panel's
    background). The glyph's rounded corners are anti-aliased and thus
    partially transparent, so to honor the leaf-paint contract — a
    widget must fully, opaquely cover its own rect.
    """

    def __init__(self, *, border: RectBorder | None = None, backdrop: tuple[int, int, int] = (0, 0, 0), **kwargs):
        self._custom_border = border
        self._backdrop = backdrop
        super().__init__(**kwargs)

    def _get_border(self) -> RectBorder:
        if self._custom_border is not None:
            return self._custom_border
        c = self.outline_color
        if c is None:
            return RectBorder()
        return RectBorder(top=c, right=c, bottom=c, left=c)

    def _make_glyph(self) -> RoundedRectGlyph:
        assert self.box is not None
        return RoundedRectGlyph(
            width=self.box.width,
            height=self.box.height,
            radius=self.outline_radius or 0,
            fill=self.bkgnd_color,
            border=self._get_border(),
        )

    @override
    def _draw_erase(self, ctx):
        # Lay the backdrop down first so the glyph's AA corners always
        # composite against a known, opaque color, making redraws idempotent
        erase = ctx.dirty_bounds
        if not erase.is_empty():
            ctx.draw_rectangle(erase, fill=self._backdrop)
        ctx.paste(self._make_glyph().render(), (0, 0))

    @override
    def _draw_outline(self, ctx):
        # Border was already painted as part of the glyph in _draw_erase.
        return


class ScrollingText(TextWidget):
    """TextWidget with horizontal ping-pong scrolling for overflow text."""

    def __init__(
        self,
        pixels_per_second: float = 50.0,
        pause_start_sec: float = 2.0,
        pause_end_sec: float = 1.0,
        lcd_poll_divisor: int = 8,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.pixels_per_second: float = pixels_per_second
        self.pause_start_sec: float = pause_start_sec
        self.pause_end_sec: float = pause_end_sec

        # Scrolling state — position is a deterministic f(now - anchor).
        self.scroll_offset: int = 0
        self._anchor_time: Optional[float] = None
        self._last_tick_time: Optional[float] = None

        # Cached rendering
        self.cached_text_image: Optional[pygame.Surface] = None
        self.cached_text_width: int = 0

    def _render_text_to_cache(self) -> None:
        """Pre-render full text to a pygame Surface for efficient scrolling."""
        if not self.text:
            self.cached_text_image = None
            self.cached_text_width = 0
            return

        tw, th = self._get_text_size()
        self.cached_text_width = tw

        surf = pygame.Surface((max(1, tw), max(1, th)), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        color = self.fgnd_color
        if isinstance(color, (list, tuple)) and len(color) == 3:
            color = tuple(color) + (255,)
        asc = int(self.font.get_sized_ascender())
        prev = self.font.origin
        self.font.origin = True
        try:
            self.font.render_to(surf, (0, asc), self.text, fgcolor=color)
        finally:
            self.font.origin = prev
        self.cached_text_image = surf

    def _should_scroll(self) -> bool:
        if self.cached_text_image is None:
            return False
        assert self.box is not None
        h_margin, _ = self._get_margins()
        available_width = self.box.width - h_margin - self.outline
        return self.cached_text_width > available_width

    @override
    def tick(self) -> None:
        if self.cached_text_image is None:
            self._render_text_to_cache()

        if not self._should_scroll():
            if self.scroll_offset != 0:
                self.scroll_offset = 0
                self._anchor_time = None
                self._last_tick_time = None
                self.refresh()
            return

        assert self.box is not None
        h_margin, _ = self._get_margins()
        available_width = self.box.width - 2 * h_margin - self.outline
        max_offset = self.cached_text_width - available_width
        if max_offset <= 0:
            return

        scroll_duration = max_offset / self.pixels_per_second
        period = self.pause_start_sec + scroll_duration + self.pause_end_sec + scroll_duration

        now = time.monotonic()
        # On first tick, or after a wild gap (process paused, panel hidden),
        # re-anchor so we start a fresh cycle at the initial pause.
        if self._anchor_time is None or (self._last_tick_time is not None and now - self._last_tick_time > 0.25):
            self._anchor_time = now
        self._last_tick_time = now

        t = (now - self._anchor_time) % period

        if t < self.pause_start_sec:
            offset = 0.0
        elif t < self.pause_start_sec + scroll_duration:
            offset = (t - self.pause_start_sec) * self.pixels_per_second
        elif t < self.pause_start_sec + scroll_duration + self.pause_end_sec:
            offset = float(max_offset)
        else:
            back = t - self.pause_start_sec - scroll_duration - self.pause_end_sec
            offset = max_offset - back * self.pixels_per_second

        new_offset = max(0, min(max_offset, int(offset)))
        if new_offset != self.scroll_offset:
            self.scroll_offset = new_offset
            self.refresh()

    def _clear_cache_and_restart(self) -> None:
        self.cached_text_image = None
        self.scroll_offset = 0
        self._anchor_time = None
        self._last_tick_time = None

    @override
    def set_text(self, text: str) -> None:
        super().set_text(text)
        self._clear_cache_and_restart()

    @override
    def set_font(self, font) -> None:
        super().set_font(font)
        self._clear_cache_and_restart()

    @override
    def _draw(self, ctx) -> None:
        if self.cached_text_image is None:
            self._render_text_to_cache()
        if self.cached_text_image is None:
            return

        h_margin, v_margin = self._get_margins()
        tw, th = self._get_text_size()
        extra = self.outline
        hroom = ctx.width - h_margin - extra
        vroom = ctx.height - v_margin - extra

        if hroom <= 0 or vroom <= 0:
            return

        th = min(th, vroom)
        ox, oy = ctx._f().topleft

        if not self._should_scroll():
            if self.text_halign == TextHAlign.LEFT:
                hoffset = 0
            elif self.text_halign == TextHAlign.RIGHT:
                hoffset = hroom - tw
            else:
                hoffset = int((hroom - tw) / 2)
            src_rect = pygame.Rect(0, 0, min(tw, hroom), th)
            ctx.surface.blit(self.cached_text_image, (h_margin + hoffset + ox, v_margin + oy), src_rect)
        else:
            crop_width = min(hroom, self.cached_text_width - self.scroll_offset)
            src_rect = pygame.Rect(self.scroll_offset, 0, crop_width, th)
            ctx.surface.blit(self.cached_text_image, (h_margin + ox, v_margin + oy), src_rect)
