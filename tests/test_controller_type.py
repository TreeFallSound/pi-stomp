"""Controller.type is a class-level default so the volume guard is type-safe.

Controller deliberately doesn't set ``type`` in __init__ (MRO clash with
encoder.Encoder.type in EncoderController). A class-level default lets
``controller.type`` resolve on every Controller — Footswitch included —
without hasattr/getattr.
"""

from unittest.mock import MagicMock

import common.token as Token
from modalapi.mod import Mod
from pistomp.controller import Controller, RoutingInfo


class _Ctl:
    """Stand-in controller — v1 config supplies no VOLUME control to use directly."""

    def __init__(self, type):
        self.type = type
        self.parameter = "bound"
        self.midi_CC = None

    def get_routing_info(self):
        return RoutingInfo.virtual()


def test_controller_type_defaults_to_none():
    c = Controller(midi_channel=0, midi_CC=7)
    assert c.type is None


def test_bind_preserves_volume_binding_clears_others():
    h = object.__new__(Mod)
    h.wifi_manager = None
    vol = _Ctl(Token.VOLUME)
    knob = _Ctl(Token.KNOB)
    h.hardware = MagicMock()
    h.hardware.controllers = {"0:7": vol, "0:8": knob}
    h.current = MagicMock()
    h.current.pedalboard.plugins = []

    h.bind_current_pedalboard()

    assert vol.parameter == "bound"
    assert knob.parameter is None
