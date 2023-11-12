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

from enum import Enum
import json
import common.token as Token
import common.util as util

# strings as they appear in TTL files
TTL_ENUMERATION = 'enumeration'
TTL_INTEGER     = 'integer'
TTL_LOGARITHMIC = 'logarithmic'
TTL_PROPERTIES  = 'properties'
TTL_SCALEPOINTS = 'scalePoints'
TTL_TAPTEMPO    = 'tapTempo'
TTL_TOGGLED     = 'toggled'

class Type(Enum):
    DEFAULT = 0      # No explicitly defined type (eg. linear float)
    ENUMERATION = 1
    INTEGER = 2
    LOGARITHMIC = 3
    TAPTEMPO = 4
    TOGGLED = 5

class Parameter:

    def __init__(self, plugin_info, value, binding, instance_id=None):
        self.name = util.DICT_GET(plugin_info, Token.SHORTNAME)  # possibly use name if shortName is None
        if self.name is None:
            self.name = util.DICT_GET(plugin_info, Token.NAME)
        self.symbol = util.DICT_GET(plugin_info, Token.SYMBOL)
        self.minimum = util.DICT_GET(util.DICT_GET(plugin_info, Token.RANGES), Token.MINIMUM)
        self.maximum = util.DICT_GET(util.DICT_GET(plugin_info, Token.RANGES), Token.MAXIMUM)
        self.value = value
        self.binding = binding
        self.instance_id = instance_id
        self.type = Type.DEFAULT
        self.enum_values = []

        properties = util.DICT_GET(plugin_info, TTL_PROPERTIES)
        if properties is not None and len(properties) > 0:
            if TTL_ENUMERATION in properties:
                self.enum_values = util.DICT_GET(plugin_info, TTL_SCALEPOINTS)
                self.type = Type.ENUMERATION
            elif TTL_INTEGER in properties:
                self.type = Type.INTEGER
            elif TTL_LOGARITHMIC in properties:
                self.type = Type.LOGARITHMIC
            elif TTL_TAPTEMPO in properties:
                self.type = Type.TAPTEMPO
            elif TTL_TOGGLED in properties:
                self.type = Type.TOGGLED

    def get_enum_value_list(self):
        ret = []
        for v in self.enum_values:
            ret.append((util.DICT_GET(v,'label'), util.DICT_GET(v,'value')))
        return ret

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


