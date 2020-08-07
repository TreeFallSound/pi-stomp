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

import json
import common.token as Token
import common.util as util


class Parameter:

    def __init__(self, plugin_info, value, binding):
        self.name = util.DICT_GET(plugin_info, Token.SHORTNAME)  # possibly use name if shortName is None
        if self.name is None:
            self.name = util.DICT_GET(plugin_info, Token.NAME)
        self.symbol = util.DICT_GET(plugin_info, Token.SYMBOL)
        self.minimum = util.DICT_GET(util.DICT_GET(plugin_info, Token.RANGES), Token.MINIMUM)
        self.maximum = util.DICT_GET(util.DICT_GET(plugin_info, Token.RANGES), Token.MAXIMUM)
        self.value = value
        self.binding = binding

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


