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
