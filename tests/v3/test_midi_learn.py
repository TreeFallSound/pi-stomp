"""MIDI learn in mod-ui (midi_map WS broadcast) binds a hardware control to a
plugin parameter live, so the LCD reflects it without a pedalboard reload."""

import common.util as util
from common.contexts import ControlClass, EventKind, ParamEffect
from common.parameter import BYPASS_SYMBOL, Parameter, PortInfo, Symbol
from tests.types import SystemFixture

LOG_PORT: PortInfo = {
    "shortName": "HP",
    "symbol": "hpfreq",
    "ranges": {"minimum": 30.0, "maximum": 800.0},
    "properties": ["logarithmic"],
}


def test_trigger_uri_property_is_momentary():
    """Raw LV2 property URIs still identify LoopJefe trigger ports."""
    parameter = Parameter(
        {
            "symbol": "advance",
            "shortName": "Advance",
            "ranges": {"minimum": 0.0, "maximum": 1.0},
            "properties": [
                "http://lv2plug.in/ns/lv2core#integer",
                "http://lv2plug.in/ns/ext/port-props#trigger",
            ],
        },
        0.0,
        "0:60",
        "loopjefe_1",
    )

    assert parameter.is_momentary is True


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

    assert fs0.parameter is plugin.parameters[BYPASS_SYMBOL]
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
    plugin = make_plugin("mixer", bypassed=False, has_footswitch=False, parameters={"solo": solo})
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


def test_v3_midi_learn_applies_custom_sub_range(v3_system: SystemFixture, make_plugin, make_parameter):
    """A midi_map carrying a custom sub-range narrows the parameter's encoder
    sweep and displayed endpoints live, without a pedalboard reload."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    gain = make_parameter("Gain", "noise", value=0.25)
    assert (gain.minimum, gain.maximum) == (0.0, 1.0)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.0 0.5")
    handler.poll_ws_messages()

    assert (gain.minimum, gain.maximum) == (0.0, 0.5)


def test_v3_midi_learn_sub_range_saga(v3_system: SystemFixture, make_plugin, make_parameter, snapshot):
    """End-to-end: MIDI-learn a plugin param to a tweak encoder with a custom
    sub-range, then reach both extents by spinning. The parameter saturates at
    the sub-range endpoints (0.1..0.2) — never the plugin's declared 0..1 — and
    the emitted CC spans the full 7-bit range across that sub-range. The open
    parameter dialog paints the sub-range endpoints, not 0.0..1.0."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    gain = make_parameter("Gain", "noise", value=0.15)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.1 0.2")
    handler.poll_ws_messages()
    assert enc1.parameter is gain
    assert (gain.minimum, gain.maximum) == (0.1, 0.2)

    # The dialog draws param.format(minimum)/param.format(maximum) as its axis
    # endpoints — the visual proof the sub-range replaced the declared 0.0..1.0.
    handler.lcd.draw_parameter_dialog(gain)
    snapshot("bound_0p15")

    # Spin up hard — enough detents to saturate the 128-step grid at the top.
    # The parameter stops at the sub-range max (0.2), never the declared 1.0,
    # and the CC pi-stomp would emit (bar_midi_value) reaches the 7-bit ceiling.
    for _ in range(200):
        enc1.refresh(1)
    assert gain.value == 0.2
    assert enc1.bar_midi_value() == 127
    snapshot("max_0p20")

    # Spin down hard — saturate at the sub-range min (0.1), never 0.0, CC → 0.
    for _ in range(200):
        enc1.refresh(-1)
    assert gain.value == 0.1
    assert enc1.bar_midi_value() == 0
    snapshot("min_0p10")


def test_v3_log_parameter_dialog_paints_geometric_curve(v3_system: SystemFixture, make_plugin, snapshot):
    """The dial for a log port paints the geometric envelope — the same curve
    the step grid and mod-host's CC lattice use — with the current value's fill
    matching where a detent puts it."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current and handler.lcd

    freq = Parameter(LOG_PORT, 155.0, None, "eq")  # geometric midpoint: half the bars fill
    plugin = make_plugin("eq", bypassed=False, has_footswitch=False, parameters={"hpfreq": freq})
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    handler.lcd.draw_parameter_dialog(freq)
    snapshot("log_dialog_midpoint")


def test_v3_midi_learn_logarithmic_cc_round_trips(v3_system: SystemFixture, make_plugin):
    """A logarithmic port (x42-eq highpass, 30..800 Hz) bound to a tweak must emit
    a CC that inverts mod-host's *geometric* CC->value map, so MOD-UI lands on the
    dialed value — not a much smaller one. bar_midi_value used to map linearly,
    which for a log taper collapses toward the bottom of the range."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if e.id == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    freq = Parameter(LOG_PORT, 400.0, None, "eq")
    plugin = make_plugin("eq", bypassed=False, has_footswitch=False, parameters={"hpfreq": freq})
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    ws_bridge.inject(f"midi_map /graph/eq hpfreq {channel} {cc} 30.0 800.0")
    handler.poll_ws_messages()
    assert enc1.parameter is freq

    # mod-host decodes the CC we emit geometrically over [30, 800]. Feeding our CC
    # back through that map must return ~400 Hz (within one CC step), the value the
    # user set — a linear emit would decode to ~145 Hz.
    emitted_cc = enc1.bar_midi_value()
    mod_host_value = util.from_normalized(emitted_cc / 127.0, 30.0, 800.0, logarithmic=True)
    assert abs(mod_host_value - 400.0) < 12.0
    # Guard the regression explicitly: the old linear CC would land far too low.
    assert emitted_cc > 90


def test_v3_log_parameter_commit_emits_tapered_cc(v3_system: SystemFixture, make_plugin):
    """A committed edit of a mapped log port rides its encoder's CC sink, and that
    sink applies the same geometric inverse the bar does — the wire value, not just
    the display, has to invert mod-host's taper."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if e.id == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    freq = Parameter(LOG_PORT, 30.0, None, "eq")
    plugin = make_plugin("eq", bypassed=False, has_footswitch=False, parameters={"hpfreq": freq})
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    ws_bridge.inject(f"midi_map /graph/eq hpfreq {channel} {cc} 30.0 800.0")
    handler.poll_ws_messages()

    hw.midiout.send_message.reset_mock()
    handler.parameter_value_commit(freq, 400.0)

    sent_cc = hw.midiout.send_message.call_args[0][0][2]
    assert sent_cc == enc1.to_midi(400.0)
    assert abs(util.from_normalized(sent_cc / 127.0, 30.0, 800.0, logarithmic=True) - 400.0) < 12.0


def test_v3_midi_learn_external_controller_is_refused(v3_system: SystemFixture, make_plugin, make_parameter):
    """A midi_map whose channel:CC collides with an externally-routed control is
    ignored, matching the board-load guard (_bind_plugin_parameters). Accepting it
    would clobber the control's synthetic external parameter and leave its
    MidiCcEffect row shadowing the learned ParamEffect row, so the dialog commit
    would emit the raw param value out the external port instead of updating
    mod-host."""
    from pistomp.controller import RoutingInfo

    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    key = _binding_for(hw, enc1)
    channel, cc = key.split(":")
    hw.external_routing[enc1] = RoutingInfo.external("My MIDI Device")
    parameter_before = enc1.parameter

    gain = make_parameter("Gain", "noise", value=0.5)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    assert gain.binding is None
    assert enc1.parameter is parameter_before
    assert enc1 not in plugin.controllers
    rows = handler.effective_table.layers[0].rows.get((ControlClass.ANALOG, EventKind.ROTATE), [])
    assert not any(r.control.id == key and isinstance(r.effects[0], ParamEffect) for r in rows)


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


def _make_loopjefe_plugin_with_advance(_make_parameter, instance_id="loopjefe"):
    """Build LoopJefe from the same LV2 trigger metadata mod-ui returns."""
    from modalapi.plugin import Plugin
    from plugins import lookup
    from plugins.loopjefe import LOOPJEFE_URIS

    advance = Parameter(
        {
            "symbol": "advance",
            "shortName": "Advance",
            "ranges": {"minimum": 0.0, "maximum": 1.0},
            "properties": [
                "http://lv2plug.in/ns/lv2core#integer",
                "http://lv2plug.in/ns/ext/port-props#trigger",
            ],
        },
        0.0,
        None,
        instance_id,
    )
    uri = LOOPJEFE_URIS[0]
    return Plugin(instance_id, {Symbol("advance"): advance}, {}, "Looper", uri=uri, customization=lookup(uri))


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

        assert fs0.parameter is plugin.parameters[Symbol("advance")]
        assert fs0.parameter is not None
        assert fs0.parameter.is_momentary is True, (
            "advance is pprops:trigger — momentary must be derived from the "
            "port type, with zero loopjefe-specific input code"
        )

    def test_momentary_press_emits_one_shot_127_every_press(
        self, v3_system: SystemFixture, make_parameter
    ):
        """A pprops:trigger port fires on a rising edge only (loopjefe self-
        clears the port). So every short-press must emit a fresh 127 — never
        the 127/0 alternation a latching toggle produces, which would make the
        looper advance on only every other press."""
        from rtmidi.midiconstants import CONTROL_CHANGE
        from pistomp.input.event import SwitchEvent, SwitchEventKind

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

        hw.midiout.send_message.reset_mock()
        for _ in range(3):
            handler.handle(SwitchEvent(controller=fs0, kind=SwitchEventKind.PRESS, timestamp=1.0))

        sent = [c.args[0][2] for c in hw.midiout.send_message.call_args_list]
        assert sent == [127, 127, 127], "momentary trigger must one-shot 127, not toggle 127/0"
        assert all(c.args[0][1] == int(cc) for c in hw.midiout.send_message.call_args_list)
        assert fs0.toggled is False, "a trigger has no on/off state to latch"

    def test_momentary_longpress_reset_emits_one_shot_127(
        self, v3_system: SystemFixture, make_parameter
    ):
        """A longpress raw-CC mapped to a pprops:trigger port (loopjefe reset)
        is a one-shot too: every longpress emits 127, not the 127/0 toggle the
        raw-CC path uses for ordinary (non-trigger) targets."""
        from rtmidi.midiconstants import CONTROL_CHANGE
        from common.parameter import Type
        from pistomp.input.event import SwitchEvent, SwitchEventKind

        handler = v3_system.handler
        hw = v3_system.hw
        assert handler.current

        fs0 = hw.footswitches[0]
        reset_cc = 64
        plugin = _make_loopjefe_plugin_with_advance(make_parameter)
        reset = make_parameter("reset", "loopjefe", value=0.0)
        reset.type = Type.TRIGGER  # pprops:trigger in loopjefe.ttl
        reset.binding = f"{fs0.midi_channel}:{reset_cc}"  # pedalboard-learned CC
        plugin.parameters[Symbol("reset")] = reset
        handler.current.pedalboard.plugins = [plugin]

        fs0.longpress_action = {"midi_CC": reset_cc}
        handler.bind_current_pedalboard()

        hw.midiout.send_message.reset_mock()
        event = SwitchEvent(controller=fs0, kind=SwitchEventKind.LONGPRESS, timestamp=1.0)
        for _ in range(3):
            handler.handle(event)

        expected = [fs0.midi_channel | CONTROL_CHANGE, reset_cc, 127]
        assert all(c.args[0] == expected for c in hw.midiout.send_message.call_args_list), (
            "reset is pprops:trigger — every longpress must emit 127, not toggle 127/0"
        )

    def test_longpress_toggle_target_flips_through_reactive_layer(
        self, v3_system: SystemFixture, make_parameter
    ):
        """A longpress raw-CC resolving to a loaded *non*-trigger param toggles
        it through the reactive layer: each longpress flips the param and emits
        its bound CC as an alternating 127/0 edge — no local _longpress_cc_state,
        so the toggle tracks the param's real value."""
        from rtmidi.midiconstants import CONTROL_CHANGE
        from pistomp.input.event import SwitchEvent, SwitchEventKind

        handler = v3_system.handler
        hw = v3_system.hw
        assert handler.current

        fs0 = hw.footswitches[0]
        toggle_cc = 64
        plugin = _make_loopjefe_plugin_with_advance(make_parameter)
        solo = make_parameter("solo", "loopjefe", value=0.0)  # non-trigger toggle
        solo.binding = f"{fs0.midi_channel}:{toggle_cc}"
        plugin.parameters[Symbol("solo")] = solo
        handler.current.pedalboard.plugins = [plugin]

        fs0.longpress_action = {"midi_CC": toggle_cc}
        handler.bind_current_pedalboard()

        hw.midiout.send_message.reset_mock()
        event = SwitchEvent(controller=fs0, kind=SwitchEventKind.LONGPRESS, timestamp=1.0)
        for _ in range(2):
            handler.handle(event)

        sent = [c.args[0][2] for c in hw.midiout.send_message.call_args_list]
        assert sent == [127, 0], "a loaded toggle target alternates 127/0 on its bound CC"
        assert all(
            c.args[0][:2] == [fs0.midi_channel | CONTROL_CHANGE, toggle_cc]
            for c in hw.midiout.send_message.call_args_list
        )
        assert solo.value == 0.0, "two flips return the param to rest"

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


def test_v3_midi_learn_adds_table_row_for_encoder(v3_system: SystemFixture, make_plugin, make_parameter):
    """A midi_map for an encoder's CC adds a ParamEffect ROTATE row to the
    pedalboard layer so _handle_encoder dispatch and badges reflect the
    live-learned binding without a pedalboard reload."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    gain = make_parameter("Gain", "noise", value=0.5)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    rows = handler.effective_table.layers[0].rows.get((ControlClass.ANALOG, EventKind.ROTATE), [])
    matched = [r for r in rows if r.control.id == _binding_for(hw, enc1)]
    assert len(matched) == 1
    effect = matched[0].effects[0]
    assert isinstance(effect, ParamEffect)
    assert effect.plugin is plugin
    assert effect.symbol == Symbol("gain")


def test_v3_midi_learn_reroutes_an_already_bound_pedalboard(v3_system: SystemFixture, make_plugin, make_parameter):
    """A param that was WebSocket-routed at bind time switches to its encoder's CC
    once mod-ui learns the mapping. The route is derived per commit, so a binding
    learned after bind can't leave a stale one behind."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if e.id == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    gain = make_parameter("Gain", "noise", value=0.5)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    # Unmapped: the WebSocket is the only way out.
    handler.parameter_value_commit(gain, 0.6)
    assert ws_bridge.sent_values_for("noise", Symbol("gain")) == [0.6]
    hw.midiout.send_message.reset_mock()

    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    # Mapped: the CC is the whole send, and param_set must not double it up.
    handler.parameter_value_commit(gain, 0.8)
    assert ws_bridge.sent_values_for("noise", Symbol("gain")) == [0.6]
    hw.midiout.send_message.assert_called_once()


def test_v3_midi_unlearn_encoder_clears_binding_and_updates_lcd(
    v3_system: SystemFixture, make_plugin, make_parameter, snapshot
):
    """Removing a MIDI mapping in MOD-UI (channel=-1, controller=-1) unbinds the encoder,
    removes the analog controller assignment, drops the binding row, and reverts LCD displays."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current and handler.lcd

    enc1 = next(e for e in hw.encoders if e.id == 1)
    binding_id = _binding_for(hw, enc1)
    channel, cc = binding_id.split(":")

    gain = make_parameter("Gain", "noise", value=0.5)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # Learn binding to Tweak1
    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    assert gain.binding == binding_id
    assert enc1.parameter is gain
    assert f"noise:{gain.name}" in handler.current.analog_controllers
    snapshot("bound")

    # Unmap binding in MOD-UI
    ws_bridge.inject("midi_map /graph/noise gain -1 -1 0.0 1.0")
    handler.poll_ws_messages()

    assert gain.binding is None
    assert enc1.parameter is None
    assert f"noise:{gain.name}" not in handler.current.analog_controllers

    rows = handler.effective_table.layers[0].rows.get((ControlClass.ANALOG, EventKind.ROTATE), [])
    matched = [r for r in rows if r.control.id == binding_id]
    assert len(matched) == 0
    snapshot("unbound")


def test_v3_midi_unlearn_footswitch_clears_binding(v3_system: SystemFixture, make_plugin, snapshot):
    """Removing a footswitch MIDI mapping in MOD-UI clears footswitch state and has_footswitch flag."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current and handler.lcd

    fs0 = hw.footswitches[0]
    binding_id = _binding_for(hw, fs0)
    channel, cc = binding_id.split(":")

    plugin = make_plugin("noise", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    ws_bridge.inject(f"midi_map /graph/noise :bypass {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()
    assert fs0.parameter is plugin.parameters[BYPASS_SYMBOL]
    assert plugin.has_footswitch is True
    snapshot("bound")

    # Unmap in MOD-UI
    ws_bridge.inject("midi_map /graph/noise :bypass -1 -1 0.0 1.0")
    handler.poll_ws_messages()
    assert fs0.parameter is None
    assert fs0.display_label is None
    assert fs0.category is None
    assert plugin.has_footswitch is False
    snapshot("unbound")


def test_v3_midi_learn_updated_binding_range_on_same_parameter(v3_system: SystemFixture, make_plugin, make_parameter):
    """Re-addressing an already bound parameter to a different sub-range on the same CC
    updates the parameter's binding range and endpoints without bailing early."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if e.id == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    gain = make_parameter("Gain", "noise", value=0.5)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    # Initial mapping: sub-range 0.0 .. 0.5
    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.0 0.5")
    handler.poll_ws_messages()

    assert gain.binding == f"{channel}:{cc}"
    assert (gain.minimum, gain.maximum) == (0.0, 0.5)
    assert enc1.parameter is gain
    assert plugin.controllers.count(enc1) == 1

    # Updated mapping on SAME binding: sub-range 0.2 .. 0.8
    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.2 0.8")
    handler.poll_ws_messages()

    assert gain.binding == f"{channel}:{cc}"
    assert (gain.minimum, gain.maximum) == (0.2, 0.8)
    assert enc1.parameter is gain
    assert plugin.controllers.count(enc1) == 1


def test_v3_midi_unlearn_restores_declared_range(v3_system: SystemFixture, make_plugin, make_parameter):
    """Unmapping (-1:-1) restores the parameter's declared LV2 range rather than
    keeping the narrowed sub-range or applying the 0..1 unmap frame default."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if e.id == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    gain = make_parameter("Gain", "noise", value=0.5)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.1 0.9")
    handler.poll_ws_messages()
    assert (gain.minimum, gain.maximum) == (0.1, 0.9)

    ws_bridge.inject("midi_map /graph/noise gain -1 -1 0.0 1.0")
    handler.poll_ws_messages()
    assert gain.binding is None
    assert (gain.minimum, gain.maximum) == (gain.declared_minimum, gain.declared_maximum)


def test_v3_midi_learn_free_cc_preserves_sub_range(v3_system: SystemFixture, make_plugin, make_parameter):
    """A midi_map naming a CC with no physical pi-stomp control (an external/free
    MIDI CC) must still apply its sub-range — the guard keys off the -1:-1 unmap
    sentinel, not controller presence, so a real external device's extents are shown."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    used = set(hw.controllers)
    binding = next(
        "%d:%d" % (ch, cc)
        for ch in range(1, 16)
        for cc in range(0, 127)
        if "%d:%d" % (ch, cc) not in used
    )
    channel, cc = binding.split(":")

    gain = make_parameter("Gain", "noise", value=0.5)
    plugin = make_plugin("noise", bypassed=False, has_footswitch=False, parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject(f"midi_map /graph/noise gain {channel} {cc} 0.0 0.5")
    handler.poll_ws_messages()

    # No physical control to wire, so the binding is not adopted...
    assert gain.binding is None
    # ...but the external sub-range is preserved, not clobbered by 0..1 or dropped.
    assert (gain.minimum, gain.maximum) == (0.0, 0.5)


def test_v3_midi_learn_moving_footswitch_binding_clears_old_lcd_display(v3_system: SystemFixture, make_plugin):
    """A live move of a footswitch :bypass binding (FS0 -> FS1) repaints FS0 as
    unmapped grey on the LCD -- not just in memory. update_footswitch repaints a
    single widget, so without redrawing the displaced controller FS0 would keep a
    stale green badge until the next pedalboard load."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    lcd = handler.lcd

    assert handler.current and lcd

    fs0, fs1 = hw.footswitches[0], hw.footswitches[1]
    ch0, cc0 = _binding_for(hw, fs0).split(":")
    ch1, cc1 = _binding_for(hw, fs1).split(":")

    plugin = make_plugin("noise", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    lcd.draw_main_panel()

    # Bind :bypass to FS0 -> its widget lights with the category accent
    ws_bridge.inject(f"midi_map /graph/noise :bypass {ch0} {cc0} 0.0 1.0")
    handler.poll_ws_messages()
    assert fs0.parameter is plugin.parameters[BYPASS_SYMBOL]
    assert plugin.controllers.count(fs0) == 1
    w0 = next(w for w in lcd.w_footswitches if w.object is fs0)
    assert w0.color is not None

    # Move the binding live to FS1
    ws_bridge.inject(f"midi_map /graph/noise :bypass {ch1} {cc1} 0.0 1.0")
    handler.poll_ws_messages()

    # Model state fully transferred to FS1
    assert fs1.parameter is plugin.parameters[BYPASS_SYMBOL]
    assert fs0.parameter is None
    assert fs0.display_label is None
    assert fs0.category is None
    assert plugin.has_footswitch is True
    assert plugin.controllers.count(fs0) == 0
    assert plugin.controllers.count(fs1) == 1

    # LCD: FS0 reverted to unbound grey; FS1 active
    assert w0.color is None
    assert w0.action is None
    w1 = next(w for w in lcd.w_footswitches if w.object is fs1)
    assert w1.color is not None
