"""MIDI learn in mod-ui (midi_map WS broadcast) binds a hardware control to a
plugin parameter live, so the LCD reflects it without a pedalboard reload."""

from common.contexts import ControlClass, EventKind, ParamEffect
from common.parameter import BYPASS_SYMBOL, Symbol
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
    from common.parameter import Parameter, PortInfo

    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current and handler.lcd

    info: PortInfo = {"shortName": "HP", "symbol": "hpfreq",
                      "ranges": {"minimum": 30.0, "maximum": 800.0}, "properties": ["logarithmic"]}
    freq = Parameter(info, 155.0, None, "eq")  # geometric midpoint: half the bars fill
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
    import common.util as util
    from common.parameter import Parameter, PortInfo

    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    info: PortInfo = {"shortName": "HP", "symbol": "hpfreq",
                      "ranges": {"minimum": 30.0, "maximum": 800.0}, "properties": ["logarithmic"]}
    freq = Parameter(info, 400.0, None, "eq")
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


def test_v3_midi_unlearn_encoder_clears_binding_and_updates_lcd(
    v3_system: SystemFixture, make_plugin, make_parameter, snapshot
):
    """Removing a MIDI mapping in MOD-UI (channel=-1, controller=-1) unbinds the encoder,
    removes the analog controller assignment, drops the binding row, and reverts LCD displays."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current and handler.lcd

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
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
    assert plugin.has_footswitch is False
    snapshot("unbound")

