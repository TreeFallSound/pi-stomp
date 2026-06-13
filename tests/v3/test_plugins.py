"""Controller binding, plugin bypass toggle, preset plugin update, parameter editing,
and instance_id normalization round-trips."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import pistomp.switchstate as switchstate
from pistomp.encodermidicontrol import EncoderMidiControl
from common.parameter import Parameter
from modalapi.plugin import Plugin
import common.token as Token
from tests.types import SystemFixture


# ---------------------------------------------------------------------------
# Controller binding
# ---------------------------------------------------------------------------


def test_v3_bind_footswitch_to_plugin(v3_system: SystemFixture, make_plugin):
    """bind_current_pedalboard() links a footswitch to a plugin's :bypass param."""
    handler = v3_system.handler
    hw = v3_system.hw

    fs0 = hw.footswitches[0]
    binding_key = next(k for k, v in hw.controllers.items() if v is fs0)

    plugin = make_plugin("fuzz")
    plugin.parameters[":bypass"].binding = binding_key

    assert handler.current
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    assert fs0.parameter is plugin.parameters[":bypass"]
    assert plugin.has_footswitch is True
    assert plugin in [p for p in handler.current.pedalboard.plugins if p.has_footswitch]


def test_v3_bind_encoder_midi_to_plugin(v3_system: SystemFixture, make_plugin):
    """bind_current_pedalboard() populates analog_controllers for EncoderMidiControl bindings."""
    handler = v3_system.handler
    hw = v3_system.hw

    enc = next((v for v in hw.controllers.values() if isinstance(v, EncoderMidiControl)), None)
    if enc is None:
        import pytest

        pytest.skip("No EncoderMidiControl in default config")

    binding_key = next(k for k, v in hw.controllers.items() if v is enc)

    plugin = make_plugin("wah")
    plugin.parameters[":bypass"].binding = binding_key

    assert handler.current
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    assert any("wah" in k for k in handler.current.analog_controllers)


def test_v3_bind_volume_encoder_populates_analog_controllers(v3_system: SystemFixture):
    """The VOLUME-type encoder always appears in analog_controllers after binding."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    handler.current.pedalboard.plugins = []

    handler.bind_current_pedalboard()

    assert Token.VOLUME in handler.current.analog_controllers


# ---------------------------------------------------------------------------
# Plugin bypass
# ---------------------------------------------------------------------------


def test_v3_toggle_plugin_bypass_via_footswitch_sends_midi_cc(v3_system: SystemFixture, make_plugin):
    """Footswitch-bound plugin: toggle_plugin_bypass() sends MIDI CC, not a WebSocket message.

    MOD-UI receives the bypass change via its MIDI input; ws_bridge is not involved.
    """
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current

    fs = hw.footswitches[0]
    assert fs.midi_CC is not None, "test requires a footswitch with a midi_CC binding"

    plugin = make_plugin("fuzz", has_footswitch=True)
    plugin.controllers = [fs]
    handler.current.pedalboard.plugins = [plugin]

    handler.toggle_plugin_bypass(None, plugin)

    fs.midiout.send_message.assert_called_once()
    sent_cc = fs.midiout.send_message.call_args[0][0]
    assert sent_cc[1] == fs.midi_CC
    assert ws_bridge.sent_values_for("fuzz", ":bypass") == []


def test_v3_toggle_plugin_bypass_no_footswitch_sends_websocket(v3_system: SystemFixture, make_plugin, snapshot):
    """Non-footswitch plugin: toggle_plugin_bypass() updates state+LCD immediately and sends :bypass via WS.

    No echo arrives for WS-initiated bypass (msg_callback_broadcast skips origin; mod-host
    doesn't generate param_set feedback for bypass commands). State and LCD must update locally.
    """
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    assert handler.lcd

    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("active")

    widget = next(w for w in handler.lcd.w_plugins if w.object is plugin)
    handler.toggle_plugin_bypass(widget, plugin)

    # State and LCD update immediately — no echo needed.
    assert ws_bridge.sent_values_for("fuzz", ":bypass") == [1.0]
    assert plugin.is_bypassed()
    snapshot("bypassed")


def test_v3_toggle_plugin_bypass_via_footswitch(v3_system: SystemFixture, make_plugin, get_urls):
    """Plugin with has_footswitch: toggle_plugin_bypass() routes through footswitch.pressed()."""
    handler = v3_system.handler
    hw = v3_system.hw
    mock_post = v3_system.mock_post

    assert handler.current

    plugin = make_plugin("fuzz", has_footswitch=True)
    plugin.controllers = [hw.footswitches[0]]
    handler.current.pedalboard.plugins = [plugin]

    handler.toggle_plugin_bypass(None, plugin)

    assert not any("pi_stomp_set" in u for u in get_urls(mock_post))
    assert hw.footswitches[0].toggled is True


def test_v3_bound_footswitch_emits_absolute_values_and_updates_display(v3_system: SystemFixture, make_plugin):
    """A bound :bypass footswitch sends alternating absolute CC values from local
    intent — so rapid presses that outrun the echo stay correct — and updates its
    indicators optimistically, while leaving the cached parameter for the echo."""
    hw = v3_system.hw
    fs = hw.footswitches[0]
    fs.refresh_callback = MagicMock()
    fs.midiout.send_message.reset_mock()

    plugin = make_plugin("fuzz")
    fs.parameter = plugin.parameters[":bypass"]

    bypass_before = fs.parameter.value
    for _ in range(3):
        fs.pressed(switchstate.Value.RELEASED)

    sent = [c.args[0][2] for c in fs.midiout.send_message.call_args_list]
    assert sent == [127, 0, 127]
    assert fs.refresh_callback.call_count == 3  # display updates on each press
    assert fs.parameter.value == bypass_before  # cached value still echo-authoritative


def test_v3_preset_change_leans_on_ws_drain_not_rest(v3_system: SystemFixture, make_plugin, get_urls):
    """Snapshot change no longer polls REST per plugin for bypass; the WS stream
    (mod-ui broadcasts param_set :bypass during snapshot_load) refreshes it."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge
    mock_get = v3_system.mock_get

    assert handler.current
    plugin = make_plugin("fuzz", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.current.presets = {0: "A", 1: "B"}
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    handler.preset_change(1)

    assert handler.current.preset_index == 1
    assert not any("pi_stomp_get" in u for u in get_urls(mock_get))  # no per-plugin REST poll

    # Bypass arrives via the drain, exactly as mod-ui emits during snapshot_load.
    ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_ws_messages()
    assert plugin.is_bypassed()


# ---------------------------------------------------------------------------
# Parameter editing
# ---------------------------------------------------------------------------


def test_v3_parameter_edit(v3_system: SystemFixture, make_parameter, snapshot):
    """Full parameter-edit flow: navigate to plugin, open dialog, tweak, close."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    assert handler.lcd

    gain_param = make_parameter("Gain", "delay", value=0.5)
    from tests.integration.conftest import PROJECT_ROOT  # noqa: F401 — ensure import path works
    from modalapi.plugin import Plugin
    from modalapi.parameter import Parameter

    bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
    bp = Parameter(bypass_info, False, None, "delay")
    plugin = Plugin("delay", {"gain": gain_param, ":bypass": bp}, {}, "Delay")

    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # wrench → pedalboard → preset → plugin
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)

    handler.universal_encoder_sw(switchstate.Value.LONGPRESSED)
    snapshot("param_menu")

    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot("param_dialog")

    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    snapshot("param_tweaked")

    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    handler.poll_lcd_updates()
    snapshot("param_closed")

    # parameter_value_commit fires on every encoder step, so 3 steps → 3 messages
    sent = ws_bridge.sent_values_for("delay", "gain")
    assert len(sent) == 3
    assert sent[-1] == gain_param.value


def test_v3_parameter_midi_change(v3_system: SystemFixture, make_parameter, snapshot):
    """parameter_midi_change() draws a parameter dialog and steps the value."""
    handler = v3_system.handler

    param = make_parameter("Gain", "delay", value=0.5)
    handler.parameter_midi_change(param, 1)
    snapshot()


# ---------------------------------------------------------------------------
# Plugin bypass sync (inbound websocket events from mod-ui)
# ---------------------------------------------------------------------------


def test_v3_poll_ws_messages_drains_without_file_watch(v3_system: SystemFixture, make_plugin):
    """The fast-cadence poll_ws_messages() dispatches inbound WS on its own."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_ws_messages()

    assert plugin.is_bypassed()


def test_v3_add_dump_reseeds_bypass_on_reconnect(v3_system: SystemFixture, make_plugin):
    """The connect/reconnect dump carries bypass only in the `add` line (field 4);
    draining it reseeds plugin bypass without any param_set :bypass."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject("add fuzz http://uri 0.0 0.0 1 1 1")
    handler.poll_ws_messages()

    assert plugin.is_bypassed()


def test_v3_add_dump_unknown_instance_is_ignored(v3_system: SystemFixture, make_plugin):
    """An add for an instance we don't have (stale/other board) is a safe no-op."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject("add other_board_plugin http://uri 0.0 0.0 1 1 1")
    handler.poll_ws_messages()

    assert not plugin.is_bypassed()


def test_v3_handle_bypass_event_updates_plugin(v3_system: SystemFixture, make_plugin, snapshot):
    """Inbound param_set :bypass from mod-ui updates plugin state and redraws LCD."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_modui_changes()

    assert plugin.is_bypassed()
    snapshot()


def test_v3_bypass_echo_is_idempotent(v3_system: SystemFixture, make_plugin, snapshot):
    """Inbound bypass echo (Path C: external change) is idempotent with local state."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("active")

    widget = next(w for w in handler.lcd.w_plugins if w.object is plugin)
    handler.toggle_plugin_bypass(widget, plugin)
    # State and LCD update immediately (Path B: no echo arrives for WS-initiated bypass).
    assert plugin.is_bypassed()
    snapshot("bypassed")

    # An inbound echo (e.g. from mod-ui browser) confirming the same state is idempotent.
    ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_ws_messages()
    assert plugin.is_bypassed()
    snapshot("bypassed")


def test_v3_bypass_event_unknown_plugin_is_ignored(v3_system: SystemFixture, make_plugin):
    """Bypass event for an unknown instance ID doesn't raise or corrupt state."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    plugin = make_plugin("fuzz", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject("param_set /graph/not_a_real_plugin :bypass 1.0")
    handler.poll_modui_changes()

    assert not plugin.is_bypassed()


def test_v3_inbound_transport_tracks_bpm_even_when_taptempo_disabled(v3_system: SystemFixture):
    """An inbound transport broadcast updates tempo whether or not tap-tempo mode is on."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    hw.taptempo.enable(False)
    hw.taptempo.set_bpm(120.0)

    ws_bridge.inject("transport 1 4.0 138.0 Internal")
    handler.poll_modui_changes()

    assert hw.taptempo.get_bpm() == 138.0


def test_v3_snapshot_sequence_applies_bypass_via_ws(v3_system: SystemFixture, make_plugin, snapshot):
    """mod-ui broadcasts pedal_snapshot + diff-gated param_set :bypass, and
    the snapshot's bypass states become the source of truth (no REST poll).
    The frame round-trips back to the baseline when the original snapshot is restored."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    drive = make_plugin("drive", category="Distortion", bypassed=False, has_footswitch=False)
    delay = make_plugin("delay", category="Delay", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [drive, delay]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("clean")  # snapshot 0: both active

    # mod-ui → "Lead" (snapshot 1): delay engaged
    ws_bridge.inject("pedal_snapshot 1 Lead")
    ws_bridge.inject("param_set /graph/delay :bypass 1.0")
    handler.poll_modui_changes()

    assert handler.current.preset_index == 1
    assert not drive.is_bypassed()
    assert delay.is_bypassed()
    snapshot("lead")

    # mod-ui → "Clean" (snapshot 0): delay disengaged; screen returns to baseline
    ws_bridge.inject("pedal_snapshot 0 Clean")
    ws_bridge.inject("param_set /graph/delay :bypass 0.0")
    handler.poll_modui_changes()

    assert handler.current.preset_index == 0
    assert not delay.is_bypassed()
    snapshot("clean")


def test_v3_reconnect_dump_reseeds_bypass_via_poll(v3_system: SystemFixture, make_plugin, snapshot):
    """A reconnect delivers the connect dump (loading_start / add … / loading_end).
    Bypass rides only in the add line (field 4); draining the dump through the real
    poll entry point reseeds plugin state — the gap branch 5 closes."""
    handler = v3_system.handler
    hw = v3_system.hw
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    drive = make_plugin("drive", category="Distortion", bypassed=False, has_footswitch=False)
    delay = make_plugin("delay", category="Delay", bypassed=False, has_footswitch=False)
    handler.current.pedalboard.plugins = [drive, delay]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("both_active")

    # Reconnect dump for the same board: delay reconnects bypassed (field 4 = 1)
    ws_bridge.inject("loading_start 0")
    ws_bridge.inject("add drive http://uri 0.0 0.0 0 1 1")
    ws_bridge.inject("add delay http://uri 0.0 0.0 1 1 1")
    ws_bridge.inject("loading_end 0")
    handler.poll_modui_changes()

    assert not drive.is_bypassed()
    assert delay.is_bypassed()
    snapshot("delay_bypassed")


@pytest.mark.skip(
    reason="""
    If the board changes during a WS disconnect onto a non-default snapshot AND the connect
    dump drains in the same poll tick as the last.json reload, the dump applies to the OLD
    board (per-instance no-op) and is then lost to the reloaded board's .ttl default.
    Display-only (audio stays correct — mod-ui is source of truth); recover live by reselecting
    the pedalboard (unconditional rebroadcast resyncs).
    """
)
def test_v3_reconnect_after_board_change_loses_nondefault_snapshot(v3_system: SystemFixture, make_plugin):
    """
    Same-tick reconnect race: board B reloads to its .ttl default while the
    connect dump (B's live snapshot — delay bypassed) is drained against the old board.
    The asserted behavior (delay bypassed) is what gets out-of-sync today
    """
    handler = v3_system.handler
    mock_get = v3_system.mock_get

    drive = make_plugin("drive", category="Distortion", bypassed=False)
    delay = make_plugin("delay", category="Delay", bypassed=False)
    new_pb = handler.pedalboards["/path/to/new.pedalboard"]
    new_pb.plugins = [drive, delay]
    handler.reload_pedalboard = lambda bundle: new_pb  # LILV is patched out in tests

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = (
            json.dumps({"0": "Default", "1": "Lead"})
            if "snapshot/list" in url
            else json.dumps({"name": "Lead"})
            if "snapshot/name" in url
            else "{}"
        )
        return resp

    mock_get.side_effect = get_side_effect

    # One tick: the dump for B at live snapshot 1 (delay bypassed) is queued AND last.json flipped.
    ws_bridge = v3_system.ws_bridge
    ws_bridge.inject("loading_start 0")
    ws_bridge.inject("add drive http://uri 0.0 0.0 0 1 1")
    ws_bridge.inject("add delay http://uri 0.0 0.0 1 1 1")
    ws_bridge.inject("loading_end 1")

    last_json = Path(handler.data_dir) / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
    os.utime(last_json, (9999, 9999))

    handler.poll_modui_changes()

    assert handler.current
    assert handler.current.pedalboard.bundle == "/path/to/new.pedalboard"
    assert delay.is_bypassed()  # the live snapshot; lost to .ttl default on clean core


def test_v3_inbound_param_set_refreshes_cached_value(v3_system: SystemFixture, make_plugin, make_parameter):
    """An external param_set updates the cached Parameter.value so a later edit opens current."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    gain = make_parameter("Gain", "fuzz", value=0.1)
    plugin = make_plugin("fuzz", parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject("param_set /graph/fuzz gain 0.75")
    handler.poll_ws_messages()

    assert gain.value == 0.75


def test_v3_inbound_param_set_unknown_target_is_ignored(v3_system: SystemFixture, make_plugin, make_parameter):
    """param_set for an unknown plugin or symbol doesn't raise or corrupt state."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert handler.current
    gain = make_parameter("Gain", "fuzz", value=0.1)
    plugin = make_plugin("fuzz", parameters={"gain": gain})
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge.inject("param_set /graph/fuzz unknown_symbol 0.9")
    ws_bridge.inject("param_set /graph/nope gain 0.9")
    handler.poll_ws_messages()

    assert gain.value == 0.1


# ---------------------------------------------------------------------------
# instance_id normalization and round-trip
# ---------------------------------------------------------------------------


def test_v3_plugin_instance_id_strips_leading_slash():
    plugin = Plugin("/fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"


def test_v3_plugin_instance_id_strips_multiple_slashes():
    plugin = Plugin("///fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"


def test_v3_parameter_instance_id_strips_leading_slash():
    param = Parameter({"shortName": "Gain", "symbol": "gain", "ranges": {}}, 0.5, None, "/fuzz")
    assert param.instance_id == "fuzz"


def test_v3_parameter_instance_id_none_preserved():
    param = Parameter({"shortName": "Gain", "symbol": "gain", "ranges": {}}, 0.5, None, None)
    assert param.instance_id is None


def test_v3_websocket_send_parameter_uses_canonical_id(v3_system):
    """send_parameter() formats messages as 'param_set /graph/{id}/{symbol} {value}'
    using canonical instance_id (no leading slash)."""
    ws_bridge = v3_system.ws_bridge

    ws_bridge.send_parameter("BigMuffPi", "Tone", 0.75)
    ws_bridge.send_parameter("Cabinet", ":bypass", 1.0)

    assert ws_bridge.sent[-2] == "param_set /graph/BigMuffPi/Tone 0.75"
    assert ws_bridge.sent[-1] == "param_set /graph/Cabinet/:bypass 1.0"


def test_v3_websocket_bypass_event_matches_canonical_id(v3_system):
    """Inbound param_set /graph/{id}/:bypass messages are parsed to extract
    the canonical instance_id and must match Plugin.instance_id."""
    handler = v3_system.handler

    plugin = Plugin("fuzz", {}, None, "Distortion")
    bypass_param = Parameter(
        {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}},
        False,
        None,
        "fuzz",
    )
    plugin.parameters[":bypass"] = bypass_param
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge = v3_system.ws_bridge
    ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_modui_changes()

    assert plugin.is_bypassed()


def test_v3_websocket_bypass_event_with_multiword_id(v3_system):
    """WS parser correctly strips /graph/ prefix from multi-word instance IDs."""
    handler = v3_system.handler

    plugin = Plugin("Cabinet", {}, None, "Cabinet")
    bypass_param = Parameter(
        {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}},
        False,
        None,
        "Cabinet",
    )
    plugin.parameters[":bypass"] = bypass_param
    handler.current.pedalboard.plugins = [plugin]

    ws_bridge = v3_system.ws_bridge
    ws_bridge.inject("param_set /graph/Cabinet :bypass 1.0")
    handler.poll_modui_changes()

    assert plugin.is_bypassed()
