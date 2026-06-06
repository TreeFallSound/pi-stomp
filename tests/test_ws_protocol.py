"""Unit tests for ws_protocol.parse_message."""

from modalapi.ws_protocol import (
    AddHwPortMessage,
    AddPluginMessage,
    LoadingEndMessage,
    LoadingStartMessage,
    PedalSnapshotMessage,
    ParamSetMessage,
    PluginBypassMessage,
    RemoveHwPortMessage,
    SizeMessage,
    TrueBypassMessage,
    UnknownMessage,
    parse_message,
)


# ---------------------------------------------------------------------------
# loading_start
# ---------------------------------------------------------------------------


def test_loading_start_true():
    assert parse_message("loading_start 1") == LoadingStartMessage(is_default=True)


def test_loading_start_false():
    assert parse_message("loading_start 0") == LoadingStartMessage(is_default=False)


def test_loading_start_no_flag():
    assert parse_message("loading_start") == LoadingStartMessage(is_default=False)


# ---------------------------------------------------------------------------
# loading_end
# ---------------------------------------------------------------------------


def test_loading_end_with_id():
    assert parse_message("loading_end 3") == LoadingEndMessage(snapshot_id=3)


def test_loading_end_no_id():
    assert parse_message("loading_end") == LoadingEndMessage(snapshot_id=0)


def test_loading_end_negative_id():
    assert parse_message("loading_end -1") == LoadingEndMessage(snapshot_id=-1)


# ---------------------------------------------------------------------------
# pedal_snapshot
# ---------------------------------------------------------------------------


def test_pedal_snapshot_with_name():
    assert parse_message("pedal_snapshot 1 Lead") == PedalSnapshotMessage(snapshot_id=1, snapshot_name="Lead")


def test_pedal_snapshot_name_with_spaces():
    # split(" ", 2) means the name part is everything after the second token
    assert parse_message("pedal_snapshot 2 Clean Boost") == PedalSnapshotMessage(
        snapshot_id=2, snapshot_name="Clean Boost"
    )


def test_pedal_snapshot_no_name():
    assert parse_message("pedal_snapshot 0") == PedalSnapshotMessage(snapshot_id=0, snapshot_name="")


def test_pedal_snapshot_bare():
    assert parse_message("pedal_snapshot") == PedalSnapshotMessage(snapshot_id=0, snapshot_name="")


# ---------------------------------------------------------------------------
# size
# ---------------------------------------------------------------------------


def test_size_full():
    assert parse_message("size 1920 1080") == SizeMessage(width=1920, height=1080)


def test_size_width_only():
    assert parse_message("size 800") == SizeMessage(width=800, height=0)


def test_size_bare():
    assert parse_message("size") == SizeMessage(width=0, height=0)


# ---------------------------------------------------------------------------
# add_hw_port
# ---------------------------------------------------------------------------


def test_add_hw_port_full():
    msg = parse_message("add_hw_port /graph/capture_1 audio 0 Capture 1")
    assert msg == AddHwPortMessage(
        port_name="/graph/capture_1",
        port_type="audio",
        is_output=False,
        title="Capture",
        index=1,
    )


def test_add_hw_port_no_index():
    msg = parse_message("add_hw_port /graph/capture_1 audio 1 Playback")
    assert msg == AddHwPortMessage(
        port_name="/graph/capture_1",
        port_type="audio",
        is_output=True,
        title="Playback",
        index=0,
    )


def test_add_hw_port_type_and_direction_only():
    msg = parse_message("add_hw_port /graph/midi_in midi 0")
    assert msg == AddHwPortMessage(
        port_name="/graph/midi_in",
        port_type="midi",
        is_output=False,
        title="",
        index=0,
    )


def test_add_hw_port_name_only():
    msg = parse_message("add_hw_port /graph/capture_1")
    assert msg == AddHwPortMessage(
        port_name="/graph/capture_1",
        port_type="",
        is_output=False,
        title="",
        index=0,
    )


# ---------------------------------------------------------------------------
# remove_hw_port
# ---------------------------------------------------------------------------


def test_remove_hw_port():
    assert parse_message("remove_hw_port /graph/capture_1") == RemoveHwPortMessage(port_name="/graph/capture_1")


def test_remove_hw_port_bare():
    assert parse_message("remove_hw_port") == RemoveHwPortMessage(port_name="")


# ---------------------------------------------------------------------------
# truebypass
# ---------------------------------------------------------------------------


def test_truebypass_both():
    assert parse_message("truebypass 1 0") == TrueBypassMessage(left=1, right=0)


def test_truebypass_left_only():
    assert parse_message("truebypass 1") == TrueBypassMessage(left=1, right=0)


def test_truebypass_bare():
    assert parse_message("truebypass") == TrueBypassMessage(left=0, right=0)


# ---------------------------------------------------------------------------
# plugin bypass (param_set ... :bypass ...)
# ---------------------------------------------------------------------------


def test_plugin_bypass_on():
    msg = parse_message("param_set /graph/CollisionDrive :bypass 1.0")
    assert msg == PluginBypassMessage(instance="CollisionDrive", bypassed=True)


def test_plugin_bypass_off():
    msg = parse_message("param_set /graph/CollisionDrive :bypass 0.0")
    assert msg == PluginBypassMessage(instance="CollisionDrive", bypassed=False)


def test_plugin_bypass_nested_instance():
    msg = parse_message("param_set /graph/xfade :bypass 1.0")
    assert msg == PluginBypassMessage(instance="xfade", bypassed=True)


def test_plugin_bypass_nonzero_is_true():
    msg = parse_message("param_set /graph/Reverb :bypass 0.5")
    assert msg == PluginBypassMessage(instance="Reverb", bypassed=True)


def test_param_set_generic_control_port():
    # Inbound (space) form for a non-bypass control port.
    msg = parse_message("param_set /graph/Delay gain 0.75")
    assert msg == ParamSetMessage(instance="Delay", symbol="gain", value=0.75)


def test_param_set_bypass_precedes_generic_arm():
    # The :bypass arm must match before the generic param_set arm.
    msg = parse_message("param_set /graph/Delay :bypass 1.0")
    assert msg == PluginBypassMessage(instance="Delay", bypassed=True)


def test_param_set_missing_value_is_unknown():
    msg = parse_message("param_set /graph/Delay gain")
    assert isinstance(msg, UnknownMessage)


# ---------------------------------------------------------------------------
# add (connect/load dump) — bypass rides in field 4, the only place it appears
# ---------------------------------------------------------------------------


def test_add_plugin_bypassed():
    # add {instance} {uri} {x} {y} {bypassed} {sversion} {buildEnv}
    msg = parse_message("add CollisionDrive http://moddevices.com/caps 419.0 198.0 1 2 1")
    assert msg == AddPluginMessage(instance="CollisionDrive", bypassed=True)


def test_add_plugin_active():
    msg = parse_message("add fuzz http://uri 0.0 0.0 0 1 1")
    assert msg == AddPluginMessage(instance="fuzz", bypassed=False)


def test_add_plugin_strips_graph_prefix():
    msg = parse_message("add /graph/fuzz http://uri 0.0 0.0 1 1 1")
    assert msg == AddPluginMessage(instance="fuzz", bypassed=True)


def test_add_plugin_nonzero_bypass_is_true():
    msg = parse_message("add Reverb http://uri 0.0 0.0 2 1 1")
    assert msg == AddPluginMessage(instance="Reverb", bypassed=True)


def test_add_plugin_missing_bypass_field_is_unknown():
    # Fewer than 4 trailing fields → cannot locate bypass → unknown, not a crash.
    msg = parse_message("add fuzz http://uri 0.0")
    assert isinstance(msg, UnknownMessage)


def test_add_plugin_non_int_bypass_is_unknown():
    msg = parse_message("add fuzz http://uri 0.0 0.0 notanint 1 1")
    assert isinstance(msg, UnknownMessage)


# ---------------------------------------------------------------------------
# Unknown / malformed
# ---------------------------------------------------------------------------


def test_completely_unknown_message():
    msg = parse_message("some_future_message 1 2 3")
    assert isinstance(msg, UnknownMessage)
    assert msg.raw == "some_future_message 1 2 3"


def test_malformed_loading_end_non_int():
    msg = parse_message("loading_end notanint")
    assert isinstance(msg, UnknownMessage)


def test_malformed_pedal_snapshot_non_int():
    msg = parse_message("pedal_snapshot notanint Name")
    assert isinstance(msg, UnknownMessage)


def test_empty_string():
    msg = parse_message("")
    assert isinstance(msg, UnknownMessage)
