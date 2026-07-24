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


def test_transport_plugin_unconditional_fallback(v3_system: SystemFixture):
    """When timeInfo is empty, None, or available=0, transport_plugin is unconditionally
    created with default unbound parameters for :bpm, :bpb, and :rolling."""
    handler = v3_system.handler
    assert handler.current is not None

    # Test empty dict/None
    tp = handler.current.pedalboard._build_transport_plugin(None)
    assert tp is not None
    assert tp.instance_id == TRANSPORT_INSTANCE_ID
    assert BPM_SYMBOL in tp.parameters
    assert BPB_SYMBOL in tp.parameters
    assert ROLLING_SYMBOL in tp.parameters
    assert tp.parameters[BPM_SYMBOL].binding is None
    assert tp.parameters[BPM_SYMBOL].value == 120.0
    assert tp.parameters[BPB_SYMBOL].value == 4.0
    assert tp.parameters[ROLLING_SYMBOL].value == 0.0

    # Test available=0
    tp_zero = handler.current.pedalboard._build_transport_plugin({"available": 0})
    assert tp_zero is not None
    assert BPM_SYMBOL in tp_zero.parameters
    assert BPB_SYMBOL in tp_zero.parameters
    assert ROLLING_SYMBOL in tp_zero.parameters


def test_reactive_bpm_parameter_change_triggers_set_mod_tap_tempo(v3_system: SystemFixture):
    """Writing to transport_plugin.parameters[BPM_SYMBOL].value reactively notifies
    subscribers and triggers set_mod_tap_tempo."""
    from unittest.mock import MagicMock

    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None

    _attach_transport_plugin(handler)
    ws_bridge.send_bpm = MagicMock(return_value=True)

    # Change BPM parameter value directly (e.g. via encoder or set_param_value)
    tp = handler.current.pedalboard.transport_plugin
    tp.set_param_value(BPM_SYMBOL, 148.0)

    # Verify reactive subscriber triggered send_bpm
    ws_bridge.send_bpm.assert_called_once_with(148.0)


def test_transport_message_ws_suppresses_bpm_echo(v3_system: SystemFixture):
    """An incoming WebSocket TransportMessage updates transport parameters without
    echo-calling send_bpm back to mod-ui."""
    from unittest.mock import MagicMock

    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None

    _attach_transport_plugin(handler)
    ws_bridge.send_bpm = MagicMock(return_value=True)

    # Inject incoming WS TransportMessage from mod-ui: transport {rolling} {bpb} {bpm} {syncMode}
    ws_bridge.inject("transport 1 4.0 155.0 Internal")
    handler.poll_ws_messages()

    tp = handler.current.pedalboard.transport_plugin
    assert tp.parameters[BPM_SYMBOL].value == 155.0
    assert tp.parameters[ROLLING_SYMBOL].value == 1.0
    assert tp.parameters[BPB_SYMBOL].value == 4.0

    # Ensure send_bpm was NOT called because update originated from WS
    ws_bridge.send_bpm.assert_not_called()


def test_partial_timeinfo_bitmask_creates_all_parameters(v3_system: SystemFixture):
    """When timeInfo has a partial bitmask (e.g. only BPM), all 3 parameters
    are still created, with missing ones remaining unbound."""
    handler = v3_system.handler
    assert handler.current is not None

    # Available bitmask 0x2 = BPM only
    tp = handler.current.pedalboard._build_transport_plugin({
        "available": 0x2,
        "bpm": 130.0,
        "bpmCC": {"channel": 0, "control": 10},
    })
    assert tp is not None
    assert BPM_SYMBOL in tp.parameters
    assert BPB_SYMBOL in tp.parameters
    assert ROLLING_SYMBOL in tp.parameters

    assert tp.parameters[BPM_SYMBOL].binding == "0:10"
    assert tp.parameters[BPB_SYMBOL].binding is None
    assert tp.parameters[ROLLING_SYMBOL].binding is None


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


def test_encoder_bpm_turn_sends_websocket(v3_system: SystemFixture, make_plugin):
    """MIDI Learning /pedalboard :bpm to an encoder and turning it updates local tempo,
    shows the dismissible parameter dialog, and dispatches a high-precision WebSocket packet."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None and handler.lcd is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    # 1. Live MIDI Learn message from MOD-UI
    ws_bridge.inject(f"midi_map /pedalboard :bpm {channel} {cc} 20.0 280.0")
    handler.poll_ws_messages()

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    assert tp.parameters[BPM_SYMBOL].binding == f"{channel}:{cc}"
    assert enc1.parameter is tp.parameters[BPM_SYMBOL]

    # 2. Turn encoder clockwise by 1 step (1.0 BPM per detent)
    from pistomp.input.event import EncoderEvent

    event = EncoderEvent(controller=enc1, rotations=1, multiplier=1.0)
    handler._handle_encoder(event)

    # 3. Tempo parameter updated (1 step clockwise from 120.0 -> 121.0 BPM)
    assert tp.parameters[BPM_SYMBOL].value == 121.0

    # 4. High-precision WebSocket transport-bpm packet queued for MOD-UI
    sent_msgs = list(ws_bridge.sent)
    assert any("transport-bpm 121.0" in m for m in sent_msgs)


def test_encoder_bpm_clamping_at_boundaries(v3_system: SystemFixture, make_plugin):
    """BPM parameter edits clamp strictly at minimum (20.0) and maximum (280.0) limits."""
    from pistomp.input.event import EncoderEvent

    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")
    _attach_transport_plugin(
        handler,
        bpm_cc={"channel": int(channel), "control": int(cc), "hasRanges": True, "minimum": 20.0, "maximum": 280.0},
    )

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    bpm_param = tp.parameters[BPM_SYMBOL]

    # Spin clockwise aggressively (+200 steps)
    event_up = EncoderEvent(controller=enc1, rotations=200, multiplier=1.0)
    handler._handle_encoder(event_up)
    assert bpm_param.value == 280.0

    # Spin counter-clockwise aggressively (-300 steps)
    event_down = EncoderEvent(controller=enc1, rotations=-300, multiplier=1.0)
    handler._handle_encoder(event_down)
    assert bpm_param.value == 20.0


def test_unbound_encoder_emits_midi_cc_for_learning(v3_system: SystemFixture, make_plugin):
    """An unbound encoder emits fallback MIDI CC so MOD-UI can learn it, but once bound
    to /pedalboard :bpm, turns bypass MIDI CC and send WebSocket messages instead."""
    from unittest.mock import MagicMock
    from pistomp.input.event import EncoderEvent

    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    # Mock _emit_midi to observe MIDI CC output
    handler._emit_midi = MagicMock()

    # 1. Turn unbound encoder -> emits MIDI CC for MOD-UI MIDI Learn
    assert enc1.parameter is None
    handler._handle_encoder(EncoderEvent(controller=enc1, rotations=1, multiplier=1.0))
    handler._emit_midi.assert_called_once()
    handler._emit_midi.reset_mock()

    # 2. Bind encoder to /pedalboard :bpm via MIDI Learn
    ws_bridge.inject(f"midi_map /pedalboard :bpm {channel} {cc} 20.0 280.0")
    handler.poll_ws_messages()
    assert enc1.parameter is not None

    # 3. Turn bound encoder -> bypasses _emit_midi and sends WebSocket transport-bpm
    ws_bridge.sent.clear()
    handler._handle_encoder(EncoderEvent(controller=enc1, rotations=1, multiplier=1.0))
    handler._emit_midi.assert_not_called()
    assert any("transport-bpm" in msg for msg in ws_bridge.sent)


def test_parameter_value_commit_for_transport_bpm(v3_system: SystemFixture, make_plugin):
    """parameter_value_commit for /pedalboard :bpm routes via set_mod_tap_tempo (WebSocket)."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    bpm_param = tp.parameters[BPM_SYMBOL]

    ws_bridge.sent.clear()
    handler.parameter_value_commit(bpm_param, 135.0)

    assert bpm_param.value == 135.0
    assert any("transport-bpm 135.0" in m for m in ws_bridge.sent)


def test_encoder_bpm_fast_spin_acceleration(v3_system: SystemFixture, make_plugin):
    """Slow encoder turn moves 1.0 BPM per detent; fast spin accelerates edit proportionally."""
    from pistomp.input.event import EncoderEvent

    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")
    _attach_transport_plugin(
        handler,
        bpm_cc={"channel": int(channel), "control": int(cc), "hasRanges": True, "minimum": 20.0, "maximum": 280.0},
    )

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    bpm_param = tp.parameters[BPM_SYMBOL]

    # 1. Slow turn (multiplier=1.0) -> moves exactly 1.0 BPM (120.0 -> 121.0)
    handler._handle_encoder(EncoderEvent(controller=enc1, rotations=1, multiplier=1.0))
    assert bpm_param.value == 121.0

    # 2. Fast spin (multiplier=4.0) -> accelerates edit (>1.0 BPM)
    handler._handle_encoder(EncoderEvent(controller=enc1, rotations=1, multiplier=4.0))
    assert bpm_param.value > 122.0  # Accelerated step (>1 BPM)


def test_incoming_transport_decimal_bpm_sync(v3_system: SystemFixture, make_plugin):
    """External transport updates (e.g. Ableton Link) preserve decimal BPM values."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None

    # Inject external transport frame with decimal BPM (120.5)
    ws_bridge.inject("transport 1 4.0 120.5 link")
    handler.poll_ws_messages()

    assert tp.parameters[BPM_SYMBOL].value == 120.5


def test_encoder_bpm_turn_without_websocket_bridge_falls_back_to_rest_post(
    v3_system: SystemFixture, make_plugin
):
    """If ws_bridge is None, encoder tempo turns execute REST POST fallback."""
    from unittest.mock import MagicMock
    from pistomp.input.event import EncoderEvent

    handler = v3_system.handler
    hw = v3_system.hw
    mock_post = v3_system.mock_post
    assert handler.current is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")
    _attach_transport_plugin(
        handler,
        bpm_cc={"channel": int(channel), "control": int(cc), "hasRanges": True, "minimum": 20.0, "maximum": 280.0},
    )

    # Set _ws_bridge to None to simulate missing WebSocket bridge
    handler._ws_bridge = None
    mock_post.reset_mock()

    # Turn encoder
    handler._handle_encoder(EncoderEvent(controller=enc1, rotations=1, multiplier=1.0))

    # Assert REST POST fallback was executed
    mock_post.assert_called_once()
    assert "set_bpm" in mock_post.call_args[0][0]
    assert mock_post.call_args[1]["json"] == {"value": 121.0}


def test_encoder_bpm_turn_parameter_dialog_snapshot(v3_system: SystemFixture, make_plugin, snapshot):
    """Turning a BPM-bound encoder 1 detent notch displays the parameter dialog on the LCD at 121 BPM."""
    from pistomp.input.event import EncoderEvent

    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None and handler.lcd is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)

    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    ws_bridge.inject(f"midi_map /pedalboard :bpm {channel} {cc} 20.0 280.0")
    handler.poll_ws_messages()

    # Turn encoder 1 detent (120.0 -> 121.0 BPM)
    handler._handle_encoder(EncoderEvent(controller=enc1, rotations=1, multiplier=1.0))

    # Capture LCD snapshot of 121 BPM parameter dialog badge
    snapshot("bpm_dialog_121")


def test_encoder_rolling_or_bpb_emits_midi_cc(v3_system: SystemFixture, make_plugin):
    """Transport parameters other than :bpm (e.g., :rolling, :bpb) still emit MIDI CC when turned."""
    from unittest.mock import MagicMock
    from modalapi.pedalboard import ROLLING_SYMBOL
    from pistomp.input.event import EncoderEvent

    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None

    plugin = make_plugin("noise", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    _attach_transport_plugin(handler)

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1)
    channel, cc = _binding_for(hw, enc1).split(":")

    ws_bridge.inject(f"midi_map /pedalboard :rolling {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()

    tp = handler.current.pedalboard.transport_plugin
    assert tp is not None
    assert enc1.parameter is tp.parameters[ROLLING_SYMBOL]

    handler._emit_midi = MagicMock()
    handler._handle_encoder(EncoderEvent(controller=enc1, rotations=1, multiplier=1.0))

    # Assert _emit_midi was called for :rolling (unlike :bpm)
    handler._emit_midi.assert_called_once()


def test_audio_parameter_commit_early_return(v3_system: SystemFixture):
    """Audio parameters (instance_id is None) commit locally and return early without sending WS or MIDI CC."""
    from unittest.mock import MagicMock

    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    assert handler.current is not None

    param = handler._create_audio_parameter("Input Gain", "capture_volume", -19.75, 12)
    assert param.instance_id is None

    ws_bridge.send_parameter = MagicMock()
    handler._emit_midi = MagicMock()

    handler.parameter_value_commit(param, 0.0)

    # Audio param handled locally, no remote parameter set or MIDI CC emitted
    ws_bridge.send_parameter.assert_not_called()
    handler._emit_midi.assert_not_called()



