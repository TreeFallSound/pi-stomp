#!/usr/bin/env python3

from enum import Enum
import json
import modalapi.util as util


class Type(Enum):
    ANALOG = 0
    FOOTSWITCH = 1
    MIDI = 2


class Controller:

    def __init__(self, midi_channel, midi_CC, type):
        self.midi_channel = midi_channel
        self.midi_CC = midi_CC
        self.type = type
        self.minimum = None
        self.maximum = None
        self.parameter = None
        self.hardware_name = None

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)

    def set_value(self, value):
        print("Controller subclass hasn't overriden the set_value method")


