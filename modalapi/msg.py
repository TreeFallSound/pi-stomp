#!/usr/bin/env python3

from enum import Enum


class MsgMode(Enum):
    DEFAULT = 0  # Print only Error level msgs
    VERBOSE = 1  # Print
    DEBUG = 2    # Print all level


class Msg:
    FOO = 'foo'

    def __init__(self):
        self.mode = MsgMode.DEFAULT

    def set_mode(self, mode):
        self.mode = mode

    def msg(self, level, format):  # TODO separate format and args ?
        if level <= self.mode:
            print(format)
