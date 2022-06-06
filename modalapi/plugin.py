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
from pistomp.footswitch import Footswitch


class Plugin:

    def __init__(self, instance_id, parameters, info, category=None):

        self.instance_id = instance_id
        self.parameters = parameters
        self.bypass_indicator_xy = ((0,0), (0,0))
        self.lcd_xyz = None
        self.controllers = []
        self.has_footswitch = False
        self.category = category
        #self.info_dict = info   # TODO could store this but not sure we need to

    def is_bypassed(self):
        param = self.parameters.get(":bypass")  # TODO tokenize
        if param is not None:
            return param.value
        return True

    def toggle_bypass(self):
        param = self.parameters.get(":bypass")
        if param is None:
            return 0
        if param is not None:
            param.value = not param.value
        return param.value  # return the new value

    def set_bypass(self, bypass):
        param = self.parameters.get(":bypass")
        param.value = 1.0 if bypass else 0.0
        if self.has_footswitch:
            for c in self.controllers:
                if isinstance(c, Footswitch):
                    c.set_value(param.value)

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


