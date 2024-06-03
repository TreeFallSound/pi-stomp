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

import logging
from PIL import ImageColor
import common.util as util


category_color_map = {
    'Delay': "MediumVioletRed",
    'Distortion': (0, 176, 0),
    'Dynamics': (200, 80, 0),
    'Filter': (170, 140, 0),
    'Generator': "Indigo",
    'Midiutility': "Gray",
    'Modulator': (50, 50, 255),
    'Reverb': (20, 140, 180),
    'Simulator': "SaddleBrown",
    'Spacial': "Gray",
    'Spectral': (230, 0, 0),
    'Utility': "Gray"
}


# Try to map color to a valid displayable color, otherwise return None
def valid_color(color):
    if color is None:
        return None
    try:
        return ImageColor.getrgb(color)
    except ValueError:
        logging.error("Cannot convert color name: %s" % color)
        return None


# Get the color assigned to the plugin category
def get_category_color(category, default_color=(80, 80, 80)):
    if category:
        c = util.DICT_GET(category_color_map, category)
        if c and isinstance(c, tuple):
            return c
        converted = valid_color(c)
        if converted:
            return converted
    return default_color
