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
import logging


class Controller:

    def __init__(self, midi_channel, midi_CC):
        self.midi_channel = midi_channel
        self.midi_CC = midi_CC
        self.minimum = None
        self.maximum = None
        self.parameter = None
        self.hardware_name = None
        self.type = None

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)

    def set_value(self, value):
        logging.error("Controller subclass hasn't overriden the set_value method")


