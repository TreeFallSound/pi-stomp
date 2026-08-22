"""Bind a footswitch to a plugin the way a pedalboard load does: record the
binding on the parameter, then build the board again."""

from common.parameter import BYPASS_SYMBOL
from modalapi.plugin import Plugin
from pistomp.footswitch import Footswitch
from tests.types import SystemFixture


def bind_bypass(v3_system: SystemFixture, plugin: Plugin, fs: Footswitch) -> None:
    assert fs.midi_CC is not None, "test needs a footswitch with a midi_CC"
    plugin.parameters[BYPASS_SYMBOL].binding = "%d:%d" % (fs.midi_channel, fs.midi_CC)
    v3_system.handler.current.pedalboard.plugins = [plugin]
    v3_system.handler._rebind_pedalboard()
