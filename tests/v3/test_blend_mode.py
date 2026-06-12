"""Integration tests for blend mode — v3 only (requires Encoder)."""

import json
import os
from typing import cast
from unittest.mock import MagicMock

import yaml

import common.token as Token
from pistomp.input.event import EncoderEvent
from tests.conftest import FakeWebSocketBridge
from tests.types import SystemFixture


def _blend_encoder(hw):
    """Return the EncoderController with id=1 used by the blend fixture."""
    from pistomp.encoder_controller import EncoderController

    return next(e for e in hw.encoders if isinstance(e, EncoderController) and getattr(e, "id", None) == 1)


# ---------------------------------------------------------------------------
# Preparation
# ---------------------------------------------------------------------------


def test_blend_prepare_creates_segment_diff_map(blend_system: SystemFixture):
    handler = blend_system.handler

    assert "Blend" in handler.blend_modes
    blend_mode = handler.blend_modes["Blend"]

    # Two stops → one segment → one diff map
    assert len(blend_mode.stops) == 2
    assert len(blend_mode.segment_diff_maps) == 1

    diff = blend_mode.segment_diff_maps[0]
    assert "BigMuff" in diff
    assert "Tone" in diff["BigMuff"]
    assert "Level" in diff["BigMuff"]
    # :bypass is identical across stops, so it must NOT be in the diff map
    assert ":bypass" not in diff.get("BigMuff", {})


def test_blend_auto_activates_on_blend_snapshot(blend_system: SystemFixture):
    handler = blend_system.handler
    hw = blend_system.hw

    assert handler.active_blend_mode is not None
    assert handler.active_blend_mode.config.get("name") == "Blend"

    enc = _blend_encoder(hw)
    assert handler.active_blend_mode.input_controller.controlled_input is enc


# ---------------------------------------------------------------------------
# Parameter sending
# ---------------------------------------------------------------------------


def test_blend_activate_sends_initial_params(blend_system: SystemFixture):
    """Re-activate after a manual deactivate to check what sync_current_position sends."""
    handler = blend_system.handler
    hw = blend_system.hw
    assert handler.active_blend_mode
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)
    blend_mode = handler.active_blend_mode

    # Deactivate, reset tracking, and re-activate from position 0
    enc = _blend_encoder(hw)
    enc.current_step = 0
    blend_mode.deactivate()
    test_ws.sent.clear()
    blend_mode.activate()

    # At position 0 all differing params should equal the Clean stop values
    tone_values = test_ws.sent_values_for("BigMuff", "Tone")
    level_values = test_ws.sent_values_for("BigMuff", "Level")
    assert tone_values and abs(tone_values[-1] - 0.2) < 1e-6
    assert level_values and abs(level_values[-1] - 0.5) < 1e-6

    # :bypass is constant (0.0) — sent via the constant path in sync_current_position
    bypass_values = test_ws.sent_values_for("BigMuff", ":bypass")
    assert bypass_values and abs(bypass_values[-1] - 0.0) < 1e-6


def test_blend_full_sweep_reaches_lead_stop(blend_system: SystemFixture):
    """handle_event at midi_value=127 (100%) should send Lead stop values."""
    handler = blend_system.handler
    hw = blend_system.hw
    assert handler.active_blend_mode
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)

    enc = _blend_encoder(hw)
    enc.current_step = 127

    handler.active_blend_mode.input_controller.handle_event(
        EncoderEvent(controller=enc, rotations=0, new_value=enc.midi_value, new_midi_value=enc.midi_value)
    )

    tone_values = test_ws.sent_values_for("BigMuff", "Tone")
    level_values = test_ws.sent_values_for("BigMuff", "Level")
    assert tone_values and abs(tone_values[-1] - 0.8) < 1e-6
    assert level_values and abs(level_values[-1] - 0.9) < 1e-6


def test_blend_dedup_suppresses_redundant_messages(blend_system: SystemFixture):
    """Two consecutive identical positions should produce only one WS message per param."""
    handler = blend_system.handler
    hw = blend_system.hw
    assert handler.active_blend_mode
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)

    enc = _blend_encoder(hw)
    enc.current_step = 64

    ic = handler.active_blend_mode.input_controller
    event = EncoderEvent(controller=enc, rotations=0, new_value=enc.midi_value, new_midi_value=enc.midi_value)
    ic.handle_event(event)
    sent_after_first = len(test_ws.sent)
    assert sent_after_first > 0

    # Second call at the same position — nothing new should be queued
    ic.handle_event(event)
    assert len(test_ws.sent) == sent_after_first


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_blend_deactivate_detaches_encoder(blend_system: SystemFixture):
    handler = blend_system.handler
    hw = blend_system.hw
    assert handler.active_blend_mode

    enc = _blend_encoder(hw)
    blend_mode = handler.active_blend_mode

    blend_mode.deactivate()

    assert blend_mode.input_controller.controlled_input is None


def test_pedalboard_switch_clears_blend_modes(blend_system: SystemFixture):
    handler = blend_system.handler
    hw = blend_system.hw

    other_pb = handler.pedalboards["/path/to/new.pedalboard"]
    other_pb.plugins = []

    # Switching to a pedalboard with no blend config should wipe all blend state
    handler.set_current_pedalboard(other_pb)

    assert handler.blend_modes == {}
    assert handler.active_blend_mode is None


# ---------------------------------------------------------------------------
# WebSocket-driven snapshot changes
# ---------------------------------------------------------------------------


def test_ws_pedal_snapshot_deactivates_blend(blend_system: SystemFixture):
    handler = blend_system.handler
    hw = blend_system.hw
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)

    enc = _blend_encoder(hw)

    # Inject a switch to a non-blend snapshot
    test_ws.inject("pedal_snapshot 0 Clean")
    handler.poll_modui_changes()

    assert handler.active_blend_mode is None


def test_ws_pedal_snapshot_activates_blend(blend_system: SystemFixture):
    handler = blend_system.handler
    hw = blend_system.hw
    assert handler.active_blend_mode

    # Manually deactivate so we can re-activate via WebSocket
    handler.active_blend_mode.deactivate()
    handler.active_blend_mode = None

    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)
    test_ws.inject("pedal_snapshot 2 Blend")
    handler.poll_modui_changes()

    assert handler.active_blend_mode is not None
    assert handler.active_blend_mode.config.get("name") == "Blend"
    enc = _blend_encoder(hw)
    assert handler.active_blend_mode.input_controller.controlled_input is enc


# ---------------------------------------------------------------------------
# File watching
# ---------------------------------------------------------------------------


def test_snapshots_file_change_triggers_reprepare(blend_system: SystemFixture):
    handler = blend_system.handler
    assert handler.active_blend_mode
    blend_mode = handler.active_blend_mode
    snapshots_path = blend_mode.snapshots_monitor.path

    # Write updated stop values and advance mtime so the monitor detects a change
    updated = json.loads(open(snapshots_path).read())
    updated["snapshots"][1]["data"]["BigMuff"]["ports"]["Tone"] = 0.95
    open(snapshots_path, "w").write(json.dumps(updated))
    future = os.path.getmtime(snapshots_path) + 1
    os.utime(snapshots_path, (future, future))

    handler.poll_modui_changes()

    # blend mode re-prepares in-place — same object, updated diff maps
    assert "Blend" in handler.blend_modes
    diff = handler.blend_modes["Blend"].segment_diff_maps[0]
    assert abs(diff["BigMuff"]["Tone"].val_b - 0.95) < 1e-6


# ---------------------------------------------------------------------------
# User stories
# ---------------------------------------------------------------------------


def test_lcd_reflects_blend_activation(blend_system: SystemFixture, snapshot):
    """When the user switches to the Blend preset, the LCD updates without errors."""
    snapshot("blend_active")


def test_lcd_reflects_blend_deactivation(blend_system: SystemFixture, snapshot):
    """Switching away from the Blend preset causes the LCD to update without errors."""
    handler = blend_system.handler
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)

    test_ws.inject("pedal_snapshot 0 Clean")
    handler.poll_modui_changes()

    assert handler.active_blend_mode is None
    snapshot("blend_inactive")


def test_blend_halfway_produces_interpolated_values(blend_system: SystemFixture):
    """
    At 50% blend, the user hears a tone halfway between Clean and Lead.
    Stops: Clean (Tone=0.2, Level=0.5) and Lead (Tone=0.8, Level=0.9).
    At midi_value=64 (≈50%): Tone ≈ 0.502, Level ≈ 0.702.
    """
    handler = blend_system.handler
    hw = blend_system.hw
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)
    enc = _blend_encoder(hw)
    enc.current_step = 64

    assert handler.active_blend_mode
    event = EncoderEvent(controller=enc, rotations=0, new_value=enc.midi_value, new_midi_value=enc.midi_value)
    handler.active_blend_mode.input_controller.handle_event(event)

    tone_values = test_ws.sent_values_for("BigMuff", "Tone")
    level_values = test_ws.sent_values_for("BigMuff", "Level")

    # linear: val_a + (val_b - val_a) * (64/127)
    expected_tone = 0.2 + (0.8 - 0.2) * (64 / 127)
    expected_level = 0.5 + (0.9 - 0.5) * (64 / 127)
    assert tone_values and abs(tone_values[-1] - expected_tone) < 1e-5
    assert level_values and abs(level_values[-1] - expected_level) < 1e-5


def test_blend_resumes_at_encoder_position_on_activate(blend_system: SystemFixture):
    """
    If the encoder is at 50% when the user switches to the Blend preset,
    they immediately hear the blended tone at that position — not the start stop.
    """
    handler = blend_system.handler
    hw = blend_system.hw
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)
    enc = _blend_encoder(hw)

    assert handler.active_blend_mode
    handler.active_blend_mode.deactivate()
    handler.active_blend_mode = None
    enc.current_step = 64

    test_ws.sent.clear()

    test_ws.inject("pedal_snapshot 2 Blend")
    handler.poll_modui_changes()

    tone_values = test_ws.sent_values_for("BigMuff", "Tone")
    expected_tone = 0.2 + (0.8 - 0.2) * (64 / 127)
    assert tone_values and abs(tone_values[-1] - expected_tone) < 1e-5


def test_edited_stop_values_take_effect_in_next_sweep(blend_system: SystemFixture):
    """
    After the user saves an edited Lead snapshot, sweeping to 100% uses the new values.
    This supplements test_snapshots_file_change_triggers_reprepare with an actual sweep.
    """
    handler = blend_system.handler
    hw = blend_system.hw
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)

    assert handler.active_blend_mode
    snapshots_path = handler.active_blend_mode.snapshots_monitor.path

    updated = json.loads(open(snapshots_path).read())
    updated["snapshots"][1]["data"]["BigMuff"]["ports"]["Tone"] = 0.95
    open(snapshots_path, "w").write(json.dumps(updated))
    future = os.path.getmtime(snapshots_path) + 1
    os.utime(snapshots_path, (future, future))

    handler.poll_modui_changes()
    test_ws.sent.clear()

    enc = _blend_encoder(hw)
    enc.current_step = 127
    event = EncoderEvent(controller=enc, rotations=0, new_value=enc.midi_value, new_midi_value=enc.midi_value)
    handler.active_blend_mode.input_controller.handle_event(event)

    tone_values = test_ws.sent_values_for("BigMuff", "Tone")
    assert tone_values and abs(tone_values[-1] - 0.95) < 1e-6


def test_switching_between_blend_modes_applies_correct_initial_values(
    v3_system: SystemFixture, tmp_path, make_plugin, make_parameter, snapshot
):
    """
    User has two blend modes on one pedalboard: "Blend A" (Clean↔Lead) and
    "Blend B" (Clean↔Crunch).  They dial into Lead territory on Blend A, then
    switch to Blend B.  Blend B should immediately sync to the encoder's current
    position — not snap back to Clean — and the LCD should update.

    Encoder at 100%:
      Blend A → Lead:  Tone=0.8, Level=0.9
      Blend B → Crunch: Tone=0.5, Level=0.7
    """
    handler = v3_system.handler
    hw = v3_system.hw
    lcd = v3_system.lcd
    mock_get = v3_system.mock_get

    snapshots_data = {
        "current": 0,
        "snapshots": [
            {
                "name": "Clean",
                "data": {
                    "BigMuff": {"bypassed": False, "ports": {"Tone": 0.2, "Level": 0.5}, "preset": "", "parameters": {}}
                },
            },
            {
                "name": "Lead",
                "data": {
                    "BigMuff": {"bypassed": False, "ports": {"Tone": 0.8, "Level": 0.9}, "preset": "", "parameters": {}}
                },
            },
            {
                "name": "Crunch",
                "data": {
                    "BigMuff": {"bypassed": False, "ports": {"Tone": 0.5, "Level": 0.7}, "preset": "", "parameters": {}}
                },
            },
        ],
    }
    blend_config = {
        "blend_snapshots": [
            {"name": "Blend A", "input_id": 1, "interpolation": "linear", "stops": ["Clean", "Lead"]},
            {"name": "Blend B", "input_id": 1, "interpolation": "linear", "stops": ["Clean", "Crunch"]},
        ]
    }

    bundle_dir = tmp_path / "two_blend.pedalboard"
    bundle_dir.mkdir()
    (bundle_dir / "snapshots.json").write_text(json.dumps(snapshots_data))
    (bundle_dir / "config.yml").write_text(yaml.dump(blend_config))

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "pedalboard/list" in url:
            resp.text = json.dumps(
                [
                    {Token.TITLE: "Two Blend", Token.BUNDLE: str(bundle_dir)},
                    {Token.TITLE: "New Rig", Token.BUNDLE: "/path/to/new.pedalboard"},
                ]
            )
        elif "snapshot/list" in url:
            # Indices 3 and 4 are created by sync_blend_snapshots (3 regular + 2 blend)
            resp.text = json.dumps({"0": "Clean", "1": "Lead", "2": "Crunch", "3": "Blend A", "4": "Blend B"})
        elif "snapshot/name" in url:
            resp.text = json.dumps({"name": "Clean"})
        else:
            resp.text = "{}"
        return resp

    mock_get.side_effect = get_side_effect

    big_muff = make_plugin(
        "BigMuff",
        category="Distortion",
        parameters={
            "Tone": make_parameter("Tone", "BigMuff", value=0.2),
            "Level": make_parameter("Level", "BigMuff", value=0.5),
        },
    )
    pb = handler.pedalboards["/path/to/rig.pedalboard"]
    pb.bundle = str(bundle_dir)
    pb.plugins = [big_muff]

    handler.set_current_pedalboard(pb)

    # Auto-activation should have landed on Blend A (first blend mode)
    assert handler.active_blend_mode is not None
    assert handler.active_blend_mode.config.get("name") == "Blend A"

    # Dial into Lead territory: encoder at 100%
    enc = _blend_encoder(hw)
    enc.current_step = 127
    event = EncoderEvent(controller=enc, rotations=0, new_value=enc.midi_value, new_midi_value=enc.midi_value)
    handler.active_blend_mode.input_controller.handle_event(event)

    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)
    test_ws.sent.clear()

    # User switches to Blend B — encoder still at 100% (Crunch stop)
    test_ws.inject("pedal_snapshot 4 Blend B")
    handler.poll_modui_changes()

    assert handler.active_blend_mode is not None
    assert handler.active_blend_mode.config.get("name") == "Blend B"

    # At 100%, Blend B sends Crunch values, not Lead values
    tone_values = test_ws.sent_values_for("BigMuff", "Tone")
    level_values = test_ws.sent_values_for("BigMuff", "Level")
    assert tone_values and abs(tone_values[-1] - 0.5) < 1e-6
    assert level_values and abs(level_values[-1] - 0.7) < 1e-6

    snapshot("blend_b_full")

    # Roll the encoder back to ~50% — Blend B should interpolate between Clean and Crunch
    enc.current_step = 64
    test_ws.sent.clear()
    event = EncoderEvent(controller=enc, rotations=0, new_value=enc.midi_value, new_midi_value=enc.midi_value)
    handler.active_blend_mode.input_controller.handle_event(event)

    tone_values = test_ws.sent_values_for("BigMuff", "Tone")
    level_values = test_ws.sent_values_for("BigMuff", "Level")
    expected_tone = 0.2 + (0.5 - 0.2) * (64 / 127)  # Clean→Crunch at 50%
    expected_level = 0.5 + (0.7 - 0.5) * (64 / 127)
    assert tone_values and abs(tone_values[-1] - expected_tone) < 1e-5
    assert level_values and abs(level_values[-1] - expected_level) < 1e-5

    snapshot("blend_b_half")


# ---------------------------------------------------------------------------
# MIDI-bound parameter exclusion
# ---------------------------------------------------------------------------


def test_midi_bound_param_excluded_from_blend_sweep(blend_system: SystemFixture):
    """
    A parameter with a MIDI CC binding must never be sent during blend interpolation.
    Binding is detected during prepare(); excluded params are absent from the diff map.
    """
    handler = blend_system.handler
    hw = blend_system.hw
    assert handler.current
    test_ws = cast(FakeWebSocketBridge, handler.ws_bridge)

    # Attach a MIDI binding to Tone on the current pedalboard's BigMuff
    tone_param = handler.current.pedalboard.plugins[0].parameters["Tone"]
    tone_param.binding = "0:74"  # channel 0, CC 74

    # Re-prepare to pick up the binding, then re-activate
    blend_mode = handler.active_blend_mode
    assert blend_mode is not None
    blend_mode.deactivate()
    blend_mode.cleanup()
    blend_mode.prepare()
    blend_mode.activate()
    test_ws.sent.clear()

    enc = _blend_encoder(hw)
    enc.current_step = 127
    event = EncoderEvent(controller=enc, rotations=0, new_value=enc.midi_value, new_midi_value=enc.midi_value)
    blend_mode.input_controller.handle_event(event)

    # Tone is MIDI-bound → excluded from diff map → must not appear in sent messages
    assert test_ws.sent_values_for("BigMuff", "Tone") == []
    # Level is unbound → still interpolated and sent
    assert test_ws.sent_values_for("BigMuff", "Level") != []
