"""MIDI learn in mod-ui (midi_map WS broadcast) binds a hardware control to a
plugin parameter live, so the LCD reflects it without a pedalboard reload."""

from tests.types import SystemFixture


def _binding_for(hw, controller):
    """The 'channel:cc' key under which a controller is registered."""
    return next(k for k, v in hw.controllers.items() if v is controller)


def test_v3_midi_learn_binds_footswitch_live(v3_system: SystemFixture, make_plugin, snapshot):
    """A midi_map for a footswitch's CC binds it to the plugin :bypass and updates
    just that footswitch on the LCD — no reload, plugin tiles untouched."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current and handler.lcd

    fs0 = hw.footswitches[0]
    channel, cc = _binding_for(hw, fs0).split(":")

    plugin = make_plugin("noise", category="Utility", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("unbound")

    ws_bridge.inject(f"midi_map /graph/noise :bypass {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    assert fs0.parameter is plugin.parameters[":bypass"]
    assert plugin.has_footswitch is True
    snapshot("bound")


def test_v3_midi_learn_replay_is_idempotent(v3_system: SystemFixture, make_plugin):
    """The connect-dump rebroadcasts midi_map for existing mappings; a replay that
    matches the current binding is a no-op (no duplicate controllers)."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    fs0 = hw.footswitches[0]
    channel, cc = _binding_for(hw, fs0).split(":")

    plugin = make_plugin("noise", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    msg = f"midi_map /graph/noise :bypass {channel} {cc} 0.0 1.0"
    ws_bridge.inject(msg)
    ws_bridge.inject(msg)
    handler.poll_ws_messages()

    assert plugin.controllers.count(fs0) == 1


def test_v3_param_set_syncs_bound_footswitch(v3_system: SystemFixture, make_plugin, make_parameter):
    """A non-:bypass param_set (e.g. connect-dump or external change) syncs the
    footswitch bound to that param — its toggled state mirrors mod-ui's value."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    fs0 = hw.footswitches[0]
    channel, cc = _binding_for(hw, fs0).split(":")

    solo = make_parameter("Solo", "mixer", value=0.0)
    plugin = make_plugin("mixer", bypassed=False, has_footswitch=False,
                         parameters={"solo": solo})
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    ws_bridge.inject(f"midi_map /graph/mixer solo {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()
    assert fs0.parameter is solo
    assert fs0.toggled is False  # value 0.0 → off

    ws_bridge.inject("param_set /graph/mixer solo 1.0")
    handler.poll_ws_messages()
    assert solo.value == 1.0
    assert fs0.toggled is True  # synced on → LED/keycap on


def test_v3_midi_learn_unknown_instance_is_ignored(v3_system: SystemFixture, make_plugin):
    """A midi_map for an instance we don't have is a safe no-op."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    fs0 = hw.footswitches[0]
    channel, cc = _binding_for(hw, fs0).split(":")

    plugin = make_plugin("noise", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject(f"midi_map /graph/other :bypass {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    assert fs0.parameter is None
    assert plugin.has_footswitch is False
