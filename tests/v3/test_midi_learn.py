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


def _make_loopjefe_plugin_with_advance(make_parameter, instance_id="loopjefe"):
    """Build a loopjefe plugin with an `advance` trigger parameter, using the
    real registered loopjefe customization (plugins/__init__.py imports
    plugins.loopjefe, which registers its LedSpec)."""
    from common.parameter import Type
    from modalapi.plugin import Plugin
    from plugins import lookup
    from plugins.loopjefe import LOOPJEFE_URIS

    advance = make_parameter("advance", instance_id, value=0.0)
    advance.type = Type.TRIGGER  # pprops:trigger in loopjefe.ttl
    uri = LOOPJEFE_URIS[0]
    return Plugin(instance_id, {"advance": advance}, {}, "Looper",
                  uri=uri, customization=lookup(uri))


class TestMidiLearnBindsMomentaryAndOutputs:
    """Regression: the live MIDI-learn path (Handler._apply_midi_binding →
    _bind_controller_to_param) must not need any plugin-specific input code —
    momentary semantics come for free from the bound parameter's port type
    (pprops:trigger → Type.TRIGGER), and the LED driver reads the plugin's own
    generically-mirrored output_values (from its LedSpec), not anything cached
    on the footswitch."""

    def test_midi_learn_binds_trigger_parameter_as_momentary(self, v3_system: SystemFixture, make_parameter):
        handler = v3_system.handler
        hw = v3_system.hw
        ws_bridge = v3_system.ws_bridge
        assert handler.current

        fs0 = hw.footswitches[0]
        channel, cc = _binding_for(hw, fs0).split(":")

        plugin = _make_loopjefe_plugin_with_advance(make_parameter)
        handler.current.pedalboard.plugins = [plugin]

        ws_bridge.inject(f"midi_map /graph/loopjefe advance {channel} {cc} 0.0 1.0")
        handler.poll_ws_messages()

        assert fs0.parameter is plugin.parameters["advance"]
        assert fs0.parameter is not None
        assert fs0.parameter.is_momentary is True, (
            "advance is pprops:trigger — momentary must be derived from the "
            "port type, with zero loopjefe-specific input code"
        )

    def test_update_interesting_outputs_derives_from_plugin_led_spec(
        self, v3_system: SystemFixture, make_parameter
    ):
        """Monitored outputs are owned by the plugin (its LedSpec), not by
        whichever footswitch happens to be bound to it."""
        handler = v3_system.handler
        assert handler.current

        plugin = _make_loopjefe_plugin_with_advance(make_parameter)
        handler.current.pedalboard.plugins = [plugin]

        handler._update_interesting_outputs()

        last = v3_system.ws_bridge.interesting_calls[-1]
        assert "loopjefe/state" in last
        assert "loopjefe/measure_number" in last

    def test_output_set_updates_plugin_output_values_for_led_spec(
        self, v3_system: SystemFixture, make_parameter
    ):
        """End-to-end: an output_set for loopjefe/state and measure_number
        updates plugin.output_values generically, and the plugin's LedSpec
        renders the right color/style from them — no footswitch involved."""
        from modalapi.led_render import LedDisplayStyle, render_led_spec

        handler = v3_system.handler
        ws_bridge = v3_system.ws_bridge
        assert handler.current

        plugin = _make_loopjefe_plugin_with_advance(make_parameter)
        handler.current.pedalboard.plugins = [plugin]

        ws_bridge.inject("output_set /graph/loopjefe state 2.0")
        ws_bridge.inject("output_set /graph/loopjefe measure_number 1.0")
        handler.poll_ws_messages()

        assert plugin.output_values["state"] == 2.0
        assert plugin.output_values["measure_number"] == 1.0

        assert plugin.customization.led_spec is not None
        color, style = render_led_spec(plugin.customization.led_spec, plugin.output_values)
        assert color == (255, 0, 0)  # Recording → red
        assert style == LedDisplayStyle.METRONOME
