#!/usr/bin/env python3

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


