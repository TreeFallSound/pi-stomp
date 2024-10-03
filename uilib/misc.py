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
def get_text_size(text_string, font, metrics = None):
    # https://stackoverflow.com/a/46220683/9263761
    if metrics is not None:
        ascent, descent = metrics
    else:
        ascent, descent = font.getgmetrics()

#    text_width = font.getmask(text_string).getbbox()[2]
#    text_height = font.getmask(text_string).getbbox()[3] + descent
    bbox = font.getbbox(text_string)
    text_width = bbox[2]
    text_height = bbox[3] + descent

    return (text_width, text_height)

        
