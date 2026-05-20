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

from enum import Enum, Flag

# Input events.
class InputEvent(Enum):
    LEFT = 0          # Encoder left
    RIGHT = 1         # Encoder right
    CLICK = 2         # Encoder click
    LONG_CLICK = 3    # Encoder long click
    EDITED = 4        # Editable text modified (data = string)
    LETTER = 5        # A letter input (internal to TextEditor for now)
    OK = 6            # Ok button
    CANCEL = 7        # Cancel button
    BACKSPACE = 8     # Backspace (text editor)
    CLEAR = 9         # Clear (text editor)

# Alignments. These can be specified at widget creation and will override the
# topleft location of the widget.
class WidgetAlign(Flag):
    NONE = 0
    CENTRE_H = 1
    CENTRE_V = 2
    CENTRE   = 3 # This must be CENTRE_H | CENTRE_V

# Text Alignments. Limited to horizontal text for now
class TextHAlign(Enum):
    LEFT = 1
    RIGHT = 2
    CENTRE = 3

# Debug helpers
debug = False
#debug = True

def trace(obj, *args):
    if debug:
        n = None
        if hasattr(obj, 'name'):
            n = obj.name
        if n is None:
            n = '<>'
        print(str(type(obj)), n, args)

# Utility function (from stack overflow). TODO: Move to a TextUtils
def get_text_size(text_string, font, metrics=None):
    """Return (width, height) of `text_string` rendered with `font`.

    Matches PIL's `(bbox[2]-bbox[0], bbox[3]+descent)`:
        height = ascender + max_glyph_descender_in_text + font_descender
    For text with no descender glyphs this collapses to the font line height
    (ascender + descender). For text containing 'g'/'p'/'y'/etc. we add the
    extra glyph-descent so widgets sized to the text don't clip the descender.
    """
    asc = int(font.get_sized_ascender())
    desc = abs(int(font.get_sized_descender()))
    line_height = asc + desc
    if not text_string:
        return (0, line_height)
    # PIL's getbbox width = rect.x + rect.width (includes first glyph's left-side
    # bearing). pygame.freetype's rect.width is the tight ink width. Match PIL so
    # widgets sized from this don't clip text on the right at non-zero x.
    _r = font.get_rect(text_string)
    width = _r.x + _r.width
    # pygame.freetype.Font.get_metrics returns per-glyph
    # (min_x, max_x, min_y, max_y, advance_x, advance_y); min_y < 0 means
    # the glyph dips below the baseline. pygame surfaces these as Python ints
    # but the negative values come back as 32-bit unsigned, so wrap them.
    glyph_desc = 0
    for m in font.get_metrics(text_string):
        if m is None:
            continue
        min_y = m[2]
        if min_y >= 0x80000000:
            min_y -= 0x100000000
        if min_y < 0 and -min_y > glyph_desc:
            glyph_desc = -min_y
    return (width, line_height + glyph_desc)

        
