#!/usr/bin/env python3

from enum import Enum
import json
import modalapi.util as util


class Type(Enum):
    ANALOG = 1
    FOOTSWITCH = 2
    MIDI = 3


class Controller:

    def __init__(self, channel, controllerNumber, type):
        self.channel = channel
        self.controllerNumber = controllerNumber
        self.type = type
        self.minimum = None
        self.maximum = None
        self.parameter = None
        self.hardware_name = None


    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


