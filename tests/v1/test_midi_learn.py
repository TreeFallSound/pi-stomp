"""MIDI learn in mod-ui (midi_map WS broadcast) binds a hardware control to a
plugin parameter live on v1, so the mono LCD reflects it without a reload."""

from pistomp.footswitch import Footswitch
from tests.types import SystemFixtureLegacy


def test_v1_midi_learn_binds_footswitch_live(v1_system: SystemFixtureLegacy, make_plugin, snapshot):
    """A midi_map for a footswitch's CC binds it to the plugin :bypass and redraws
    the board — the plugin moves to the footswitch row without a reload."""
    handler = v1_system.handler
    hw = v1_system.hw
    ws_bridge = v1_system.ws_bridge

    assert handler.current

    binding, fs0 = next((k, v) for k, v in hw.controllers.items() if isinstance(v, Footswitch))
    channel, cc = binding.split(":")

    plugin = make_plugin("noise", category="Utility", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.update_lcd()
    snapshot("unbound")

    ws_bridge.inject(f"midi_map /graph/noise :bypass {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    assert fs0.parameter is plugin.parameters[":bypass"]
    assert plugin.has_footswitch is True
    snapshot("bound")


def test_v1_param_set_syncs_bound_footswitch(v1_system: SystemFixtureLegacy, make_plugin, make_parameter):
    """A non-:bypass param_set syncs the footswitch bound to that param — its
    toggled state mirrors mod-ui's value (no :bypass inversion)."""
    handler = v1_system.handler
    hw = v1_system.hw
    ws_bridge = v1_system.ws_bridge

    assert handler.current

    binding, fs0 = next((k, v) for k, v in hw.controllers.items() if isinstance(v, Footswitch))
    channel, cc = binding.split(":")

    solo = make_parameter("Solo", "mixer", value=0.0)
    plugin = make_plugin("mixer", bypassed=False, has_footswitch=False,
                         parameters={"solo": solo})
    handler.current.pedalboard.plugins = [plugin]
    handler.update_lcd()

    ws_bridge.inject(f"midi_map /graph/mixer solo {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()
    assert fs0.parameter is solo
    assert fs0.toggled is False  # value 0.0 → off

    ws_bridge.inject("param_set /graph/mixer solo 1.0")
    handler.poll_ws_messages()
    assert solo.value == 1.0
    assert fs0.toggled is True  # synced on


def test_v1_midi_learn_replay_is_idempotent(v1_system: SystemFixtureLegacy, make_plugin):
    """A replayed midi_map matching the current binding is a no-op (no duplicate controllers)."""
    handler = v1_system.handler
    hw = v1_system.hw
    ws_bridge = v1_system.ws_bridge

    assert handler.current

    binding, fs0 = next((k, v) for k, v in hw.controllers.items() if isinstance(v, Footswitch))
    channel, cc = binding.split(":")

    plugin = make_plugin("noise", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.update_lcd()

    msg = f"midi_map /graph/noise :bypass {channel} {cc} 0.0 1.0"
    ws_bridge.inject(msg)
    ws_bridge.inject(msg)
    handler.poll_ws_messages()

    assert plugin.controllers.count(fs0) == 1
