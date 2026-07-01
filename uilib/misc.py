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

from __future__ import annotations

from enum import Enum, Flag

from common.parameter import Parameter, Type


# Input events.
class InputEvent(Enum):
    LEFT = 0  # Encoder left
    RIGHT = 1  # Encoder right
    CLICK = 2  # Encoder click
    LONG_CLICK = 3  # Encoder long click
    EDITED = 4  # Editable text modified (data = string)
    LETTER = 5  # A letter input (internal to TextEditor for now)
    OK = 6  # Ok button
    CANCEL = 7  # Cancel button
    BACKSPACE = 8  # Backspace (text editor)
    CLEAR = 9  # Clear (text editor)


# Alignments. These can be specified at widget creation and will override the
# topleft location of the widget.
class WidgetAlign(Flag):
    NONE = 0
    CENTRE_H = 1
    CENTRE_V = 2
    CENTRE = 3  # This must be CENTRE_H | CENTRE_V


# Text Alignments. Limited to horizontal text for now
class TextHAlign(Enum):
    LEFT = 1
    RIGHT = 2
    CENTRE = 3


# Debug helpers
debug = False
# debug = True


def trace(obj, *args):
    if debug:
        n = None
        if hasattr(obj, "name"):
            n = obj.name
        if n is None:
            n = "<>"
        print(str(type(obj)), n, args)


# Utility function (from stack overflow). TODO: Move to a TextUtils
def get_text_size(text_string, font, metrics=None):
    """Return (width, height) of `text_string` rendered with `font`.

    Width matches PIL's `font.getbbox(text)[2] - getbbox(text)[0]` exactly:
        bbox_left  = min(0, min_glyph_ink_left_in_pen_coords)
        bbox_right = max(pen_after_last_glyph, max_glyph_ink_right_in_pen_coords)
        width      = bbox_right - bbox_left
    Neither pygame's `rect.x + rect.width` nor `sum(advance_x)` alone matches
    PIL — the former undercounts when ink overhangs past the advance (e.g. 'j'
    LSB<0, '█' max_x>advance), the latter overcounts in the same cases.

    Height = font ascender + font descender + per-text glyph descent overflow
    (for descender glyphs like g/p/y), matching PIL's `bbox[3] + descent`.
    """
    asc = int(font.get_sized_ascender())
    desc = abs(int(font.get_sized_descender()))
    line_height = asc + desc
    if not text_string:
        return (0, line_height)

    # pygame.freetype.Font.get_metrics returns per-glyph
    # (min_x, max_x, min_y, max_y, advance_x, advance_y). Negative values come
    # back as 32-bit unsigned ints — wrap them.
    def _signed(v):
        return v - 0x100000000 if v >= 0x80000000 else v

    pen = 0.0
    ink_left = 0.0
    ink_right = 0.0
    has_any = False
    glyph_desc = 0
    for m in font.get_metrics(text_string):
        if m is None:
            continue
        min_x = _signed(m[0])
        max_x = _signed(m[1])
        min_y = _signed(m[2])
        adv_x = m[4]
        l = pen + min_x
        r = pen + max_x
        if not has_any:
            ink_left, ink_right, has_any = l, r, True
        else:
            if l < ink_left:
                ink_left = l
            if r > ink_right:
                ink_right = r
        pen += adv_x
        if min_y < 0 and -min_y > glyph_desc:
            glyph_desc = -min_y
    if not has_any:
        return (0, line_height)
    right_edge = max(ink_right, pen)
    left_edge = min(0.0, ink_left)
    width = int(round(right_edge - left_edge))
    return (width, line_height + glyph_desc)


# ── common UI utilities ─────────────────────────────────────────────────────

INACTIVE_SHADE = 0.45


def shade_color(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def step_for_param(param: Parameter) -> float:
    t = param.type
    if t in (Type.ENUMERATION, Type.INTEGER, Type.TOGGLED):
        return 1.0
    if t == Type.LOGARITHMIC:
        ratio = 2.0 ** (1.0 / 12.0)
        return max(0.01, (param.value or param.minimum) * (ratio - 1.0))
    return max(0.01, (param.maximum - param.minimum) / 100.0)


def fmt_hz(value: float) -> str:
    if value >= 1000.0:
        return f"{value / 1000.0:.1f}k"
    return f"{value:.0f}"


def fmt_db(value: float) -> str:
    return f"{value:+.0f}dB"


def get_text_bbox(text_string, font):
    """Return (x0, y0, x1, y1) of `text_string`'s ink, matching PIL's
    `ImageFont.getbbox(text)` with the default 'la' anchor.

    Coordinates are relative to the text-draw origin (top-left of the ascender
    line). PIL clamps the bottom edge to the baseline, so glyphs that sit
    entirely above the baseline ('--', '^') still report bottom == ascender.
    """
    asc = int(font.get_sized_ascender())

    def _signed(v):
        return v - 0x100000000 if v >= 0x80000000 else v

    pen = 0.0
    ink_left = ink_right = 0.0
    max_y = min_y = 0
    has_any = False
    for m in font.get_metrics(text_string):
        if m is None:
            continue
        g_min_x, g_max_x, g_min_y, g_max_y = (_signed(m[0]), _signed(m[1]), _signed(m[2]), _signed(m[3]))
        l = pen + g_min_x
        r = pen + g_max_x
        if not has_any:
            ink_left, ink_right, has_any = l, r, True
            max_y, min_y = g_max_y, g_min_y
        else:
            ink_left = min(ink_left, l)
            ink_right = max(ink_right, r)
            max_y = max(max_y, g_max_y)
            min_y = min(min_y, g_min_y)
        pen += m[4]
    if not has_any:
        return (0, 0, 0, 0)
    x0 = int(round(min(0.0, ink_left)))
    x1 = int(round(max(ink_right, pen)))
    y0 = asc - max_y
    y1 = asc - min(0, min_y)
    return (x0, y0, x1, y1)
