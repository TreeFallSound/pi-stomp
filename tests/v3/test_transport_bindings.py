"""Pedalboard-level MIDI bindings (tempo, beats-per-bar, transport play/stop)
are addressed by mod-ui through a /pedalboard pseudo-instance with virtual
ports :bpm/:bpb/:rolling. We mirror them as a synthetic transport plugin so
the same binding/label machinery effect params use applies — w_controls knob
labels, footswitch labels, parameter dialog, value echo."""

from modalapi.pedalboard import (
    BPM_SYMBOL,
    BPB_SYMBOL,
    ROLLING_SYMBOL,
    TRANSPORT_INSTANCE_ID,
)
from tests.types import SystemFixture


def _binding_for(hw, controller) -> str:
    return next(k for k, v in hw.controllers.items() if v is controller)


def _attach_transport_plugin(handler, *, bpm_cc=None, bpb_cc=None, rolling_cc=None):
    """Build the transport pseudo-plugin from a timeInfo-shaped dict and attach
    it to the current pedalboard, then rebind so controllers pick it up."""
    time_info = {
        "available": 0x7,
        "bpb": 4.0,
        "bpbCC": bpb_cc or {"channel": -1, "control": 0},
        "bpm": 120.0,
        "bpmCC": bpm_cc or {"channel": -1, "control": 0},
        "rolling": False,
        "rollingCC": rolling_cc or {"channel": -1, "control": 0},
    }
    assert handler.current is not None
    handler.current.pedalboard.transport_plugin = handler.current.pedalboard._build_transport_plugin(time_info)
    handler.bind_current_pedalboard()
    return handler.current.pedalboard.transport_plugin


def test_transport_plugin_built_from_timeinfo(v3_system: SystemFixture):
    """hydrate() builds the transport pseudo-plugin from timeInfo; its three
    parameters carry the right symbols, names, and ranges."""
    handler = v3_system.handler
    assert handler.current is not None

    tp = _attach_transport_plugin(handler)
    assert tp is not None
    assert tp.instance_id == TRANSPORT_INSTANCE_ID
    assert tp.category == "Utility"
    # Not in self.plugins — the effect-graph render must not paint it.
    assert tp not in handler.current.pedalboard.plugins

    bpm = tp.parameters[BPM_SYMBOL]
    assert bpm.name == "Tempo"
    assert bpm.minimum == 20.0 and bpm.maximum == 280.0
    assert bpm.value == 120.0

    bpb = tp.parameters[BPB_SYMBOL]
    assert bpb.name == "BPB"
    assert bpb.value == 4.0

    rolling = tp.parameters[ROLLING_SYMBOL]
    assert rolling.name == "Transport"
    labels = {v["label"] for v in rolling.enum_values}
    assert labels == {"Playing", "Stopped"}
    assert rolling.value == 0.0


def test_find_plugin_resolves_transport(v3_system: SystemFixture):
    """find_plugin returns the transport pseudo-plugin for the /pedalboard id,
    where the old `next(p for p in plugins)` lookup returned None."""
    handler = v3_system.handler
    assert handler.current is not None
    _attach_transport_plugin(handler)

    found = handler.current.pedalboard.find_plugin(TRANSPORT_INSTANCE_ID)
    assert found is handler.current.pedalboard.transport_plugin
    # And real-plugin lookup still works.
    assert handler.current.pedalboard.find_plugin("nonexistent") is None


def test_midi_learn_bpm_labels_knob(v3_system: SystemFixture, make_plugin, snapshot):
    """A midi_map for /pedalboard :bpm bound to an encoder's CC wires the
    controller and surfaces a labeled 'Tempo' knob in w_controls."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None and handler.lcd is not None

    # A real plugin must be present so draw_main_panel has a tile to render.
    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("unbound")

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    ws_bridge.inject(f"midi_map /pedalboard :bpm {channel} {cc} 20.0 280.0")
    handler.poll_ws_messages()

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    assert tp.parameters[BPM_SYMBOL].binding == f"{channel}:{cc}"
    assert enc1.parameter is tp.parameters[BPM_SYMBOL]
    snapshot("bound")


def test_midi_learn_rolling_labels_footswitch(v3_system: SystemFixture, make_plugin, snapshot):
    """A midi_map for /pedalboard :rolling bound to a footswitch CC wires the
    footswitch to the transport toggle and reflects its label as
    Playing/Stopped."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None and handler.lcd is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    fs0 = hw.footswitches[0]
    channel, cc = _binding_for(hw, fs0).split(":")

    ws_bridge.inject(f"midi_map /pedalboard :rolling {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    rolling = tp.parameters[ROLLING_SYMBOL]
    assert rolling.binding == f"{channel}:{cc}"
    assert fs0.parameter is rolling
    assert tp.has_footswitch is True
    snapshot("rolling_bound")


def test_param_set_pedalboard_bpm_reaches_pseudo_plugin(v3_system: SystemFixture):
    """A param_set /pedalboard :bpm echo updates the transport plugin's Tempo
    parameter, where the old per-plugin loop silently dropped it."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None
    _attach_transport_plugin(handler)

    ws_bridge.inject("param_set /pedalboard :bpm 142.0")
    handler.poll_ws_messages()

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    assert tp.parameters[BPM_SYMBOL].value == 142.0


def test_transport_message_updates_pseudo_plugin(v3_system: SystemFixture):
    """A transport WS echo writes all three values onto the pseudo-plugin so
    labels track even when the change originates elsewhere (Link, MIDI slave)."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None
    _attach_transport_plugin(handler)

    ws_bridge.inject("transport 1 7.0 130.0 Internal")
    handler.poll_ws_messages()

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    assert tp.parameters[ROLLING_SYMBOL].value == 1.0
    assert tp.parameters[BPM_SYMBOL].value == 130.0
    assert tp.parameters[BPB_SYMBOL].value == 7.0


def test_load_time_binding_labels_on_load(v3_system: SystemFixture, make_plugin, snapshot):
    """A board whose timeInfo carries pre-existing *CC bindings labels them on
    load — no midi_map needed. The transport plugin is built with the binding
    already set, and ControllerManager.bind surfaces it in analog_controllers."""
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current is not None and handler.lcd is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    _attach_transport_plugin(
        handler,
        bpm_cc={"channel": int(channel), "control": int(cc), "hasRanges": True, "minimum": 20.0, "maximum": 280.0},
    )
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    assert tp.parameters[BPM_SYMBOL].binding == f"{channel}:{cc}"
    # The encoder is bound to the Tempo parameter through the load-time row.
    assert enc1.parameter is tp.parameters[BPM_SYMBOL]
    snapshot("loaded")
