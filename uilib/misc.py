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

    Width is the actual glyph width for the given text. Height is the font's
    line height (ascender + descender), so a widget sized for one string
    stays sized correctly when the text changes — matches the PIL behavior
    where `getmetrics()`-derived descent was added regardless of the text."""
    if not text_string:
        return (0, font.get_sized_height())
    width = font.get_rect(text_string).width
    return (width, font.get_sized_height())

        
