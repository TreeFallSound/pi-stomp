"""
Integration tests for pi-stomp v3 hardware (Tre) using Modhandler.

These tests boot the full Modhandler + Pistomptre stack with mocked HTTP
and hardware, then drive user interactions at the hardware level (encoder
turns, encoder button presses, footswitch presses) and assert both the
LCD output (via snapshots) and the HTTP traffic to MOD-UI.

Filesystem access (last.json, banks.json) uses real temp directories via
pytest's tmp_path — no patching of Path.exists or os.path.getmtime needed.
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import yaml

import common.token as Token
import pistomp.switchstate as switchstate
from pistomp.footswitch import Footswitch
from tests.conftest import PROJECT_ROOT, assert_snapshot
from modalapi.parameter import Parameter


# Mocking external dependencies before imports that might trigger hardware/system calls
with patch("pistomp.settings.Settings.load_settings"), patch("pistomp.settings.Settings.set_setting"):
    from modalapi.modhandler import Modhandler
    from pistomp.pistomptre import Pistomptre


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin(instance_id, category="Distortion", bypassed=False, has_footswitch=False, parameters=None):
    """Create a real Plugin object with proper bypass parameter."""
    from modalapi.plugin import Plugin

    if parameters is None:
        parameters = {}
    bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
    bypass_param = Parameter(bypass_info, bypassed, None, instance_id)
    parameters[":bypass"] = bypass_param
    p = Plugin(instance_id, parameters, {}, category)
    p.has_footswitch = has_footswitch
    return p


def _make_parameter(name, instance_id, value=0.5, minimum=0.0, maximum=1.0):
    """Create a real Parameter object."""
    info = {"shortName": name, "symbol": name.lower(), "ranges": {"minimum": minimum, "maximum": maximum}}
    return Parameter(info, value, None, instance_id)


def _get_urls(mock_obj):
    """Extract all URLs from a mock's call history."""
    return [call.args[0] for call in mock_obj.call_args_list]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def v3_system(fake_lcd, tmp_path):
    cwd = str(PROJECT_ROOT)

    # Create a real data directory with initial files
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Initial last.json pointing at the first pedalboard
    last_json = data_dir / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/rig.pedalboard"}))

    # Reset singletons for test isolation
    Modhandler._Modhandler__single = None  # pyright: ignore[reportAttributeAccessIssue]
    Pistomptre._Pistomptre__single = None  # pyright: ignore[reportAttributeAccessIssue]

    with (
        patch("requests.get") as mock_get,
        patch("requests.post") as mock_post,
        patch("pistomp.settings.Settings") as mock_settings,
        patch("modalapi.pedalboard.Pedalboard.load_bundle"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output") as mock_sub,
        patch("pistomp.lcd320x240.LcdIli9341", return_value=fake_lcd),
    ):
        mock_sub.return_value = b"SystemState=running"

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "pedalboard/list" in url:
                resp.text = json.dumps(
                    [
                        {Token.TITLE: "Integration Rig", Token.BUNDLE: "/path/to/rig.pedalboard"},
                        {Token.TITLE: "New Rig", Token.BUNDLE: "/path/to/new.pedalboard"},
                    ]
                )
            elif "snapshot/list" in url:
                resp.text = json.dumps({"0": "Clean", "1": "Lead"})
            elif "snapshot/name" in url:
                resp.text = json.dumps({"name": "Clean"})
            else:
                resp.text = "{}"
            return resp

        mock_get.side_effect = get_side_effect

        def post_side_effect(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "{}"
            return resp

        mock_post.side_effect = post_side_effect

        # Load config
        cfg_path = PROJECT_ROOT / "setup" / "config_templates" / "default_config_pistomptre.yml"
        with open(cfg_path, "r") as f:
            cfg = yaml.safe_load(f)

        # Create Handler with real tmp data_dir
        mock_audiocard = MagicMock()
        handler = Modhandler(mock_audiocard, cwd, data_dir=str(data_dir))

        # Create Hardware
        midiout = MagicMock()
        hw = Pistomptre(cfg, handler, midiout, handler.update_lcd_fs)
        handler.add_hardware(hw)

        # Load pedalboards (both rigs pre-loaded)
        handler.load_pedalboards()

        # Set up the initial pedalboard with no plugins
        pb = handler.pedalboards["/path/to/rig.pedalboard"]
        pb.plugins = []
        handler.set_current_pedalboard(pb)

        # Also clear plugins on the second pedalboard (tests add their own)
        pb2 = handler.pedalboards["/path/to/new.pedalboard"]
        pb2.plugins = []

        # Reset mocks so setup HTTP calls don't pollute test assertions
        mock_get.reset_mock()
        mock_get.side_effect = get_side_effect
        mock_post.reset_mock()
        mock_post.side_effect = post_side_effect

        yield handler, hw, fake_lcd, mock_get, mock_post


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def test_v3_startup_snapshot(v3_system, snapshot_update):
    handler, hw, lcd, _, _ = v3_system
    assert len(lcd.frames) > 0
    assert_snapshot(lcd.frames[-1], "v3_integration/startup", update=snapshot_update)


# ---------------------------------------------------------------------------
# Navigation — encoder-driven menu access
# ---------------------------------------------------------------------------


def test_v3_nav_to_system_menu(v3_system, snapshot_update):
    """Wrench is initially selected; clicking encoder opens the system menu."""
    handler, hw, lcd, _, _ = v3_system
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    assert_snapshot(lcd.frames[-1], "v3_integration/system_menu", update=snapshot_update)


# ---------------------------------------------------------------------------
# Footswitch press — MIDI + LCD
# ---------------------------------------------------------------------------


def test_v3_footswitch_press(v3_system, snapshot_update):
    handler, hw, lcd, _, _ = v3_system
    midiout = hw.midiout

    hw.footswitches[0].pressed(switchstate.Value.RELEASED)

    # Assert MIDI CC was sent with the right CC number from config (fs 0 = CC 60)
    midiout.send_message.assert_called_once()
    cc_msg = midiout.send_message.call_args[0][0]
    assert cc_msg[1] == 60  # midi_CC from default config
    assert cc_msg[2] == 127  # enabled

    assert_snapshot(lcd.frames[-1], "v3_integration/footswitch_pressed", update=snapshot_update)


# ---------------------------------------------------------------------------
# Pedalboard change via MOD-UI (file-watch path)
# ---------------------------------------------------------------------------


def test_v3_pedalboard_change_via_modui(v3_system, snapshot_update):
    """Simulate MOD-UI changing the pedalboard by updating last.json.
    poll_modui_changes() detects the mtime change, reads the file, and
    reloads the pedalboard — no outgoing POST to load_bundle."""
    handler, hw, lcd, mock_get, mock_post = v3_system

    # Add a plugin to the new pedalboard so the LCD has something to show
    pb2 = handler.pedalboards["/path/to/new.pedalboard"]
    pb2.plugins = [_make_plugin("fuzz", category="Distortion")]

    # Mock the snapshot response that set_current_pedalboard will trigger
    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "snapshot/list" in url:
            resp.text = json.dumps({"0": "Default"})
        elif "snapshot/name" in url:
            resp.text = json.dumps({"name": "Default"})
        else:
            resp.text = "{}"
        return resp

    mock_get.side_effect = get_side_effect

    # Write the new last.json — exactly what MOD-UI would do
    last_json = Path(handler.data_dir) / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
    # Bump mtime so it differs from the stored timestamp
    os.utime(last_json, (9999, 9999))

    handler.poll_modui_changes()

    # No POST to load_bundle — MOD-UI already did the switch
    post_urls = _get_urls(mock_post)
    assert not any("load_bundle" in u for u in post_urls)

    # LCD should now show the new pedalboard
    assert handler.current.pedalboard.title == "New Rig"
    assert_snapshot(lcd.frames[-1], "v3_integration/pedalboard_change_modui", update=snapshot_update)


# ---------------------------------------------------------------------------
# Pedalboard change via LCD navigation
# ---------------------------------------------------------------------------


def test_v3_pedalboard_change_via_lcd(v3_system, snapshot_update):
    """Navigate encoder to pedalboard widget, select the second board.
    Assert the POST to load_bundle, then simulate MOD-UI completing
    the change via last.json."""
    handler, hw, lcd, mock_get, mock_post = v3_system

    # Add a plugin to the new pedalboard
    pb2 = handler.pedalboards["/path/to/new.pedalboard"]
    pb2.plugins = [_make_plugin("fuzz", category="Distortion")]

    # Nav: wrench (initial) → enc_step(1) → pedalboard widget
    handler.universal_encoder_select(1)
    # Click to open pedalboard menu
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    # Menu shows: "Integration Rig" (current), "New Rig"
    # Step down to "New Rig"
    handler.universal_encoder_select(1)
    # Click to select
    handler.universal_encoder_sw(switchstate.Value.RELEASED)

    # Assert POST to load_bundle with the right bundle path
    post_urls = _get_urls(mock_post)
    assert any("pedalboard/load_bundle" in u for u in post_urls)

    # Assert GET to reset was called first
    get_urls = _get_urls(mock_get)
    assert any("reset" in u for u in get_urls)

    # Now simulate MOD-UI completing the switch (writes last.json)
    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "snapshot/list" in url:
            resp.text = json.dumps({"0": "Default"})
        elif "snapshot/name" in url:
            resp.text = json.dumps({"name": "Default"})
        else:
            resp.text = "{}"
        return resp

    mock_get.reset_mock()
    mock_get.side_effect = get_side_effect

    # Write updated last.json — MOD-UI confirms the switch
    last_json = Path(handler.data_dir) / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
    os.utime(last_json, (9999, 9999))

    handler.poll_modui_changes()

    assert handler.current.pedalboard.title == "New Rig"
    assert_snapshot(lcd.frames[-1], "v3_integration/pedalboard_change_lcd", update=snapshot_update)


# ---------------------------------------------------------------------------
# Preset change via footswitch longpress
# ---------------------------------------------------------------------------


def test_v3_preset_change_via_footswitch_longpress(v3_system, snapshot_update):
    """Footswitch 0 has longpress: previous_snapshot with number_in_group=1.
    A single longpress triggers preset_decr_and_change after 0.4s."""
    handler, hw, lcd, mock_get, mock_post = v3_system

    # Footswitch 0 longpress fires previous_snapshot
    hw.footswitches[0].pressed(switchstate.Value.LONGPRESSED)

    # Advance time past the 0.4s single-longpress threshold, then run
    # the same check that poll_controls() calls at the end of each cycle
    with patch("time.monotonic", return_value=time.monotonic() + 1.0):
        Footswitch.check_longpress_events()

    # previous_snapshot wraps around: from index 0 → max index (1 = "Lead")
    get_urls = _get_urls(mock_get)
    assert any("snapshot/load" in u for u in get_urls)

    assert_snapshot(lcd.frames[-1], "v3_integration/preset_change_longpress", update=snapshot_update)


# ---------------------------------------------------------------------------
# Preset change via LCD navigation
# ---------------------------------------------------------------------------


def test_v3_preset_change_via_lcd(v3_system, snapshot_update):
    """Navigate encoder to preset widget, open menu, select 'Lead',
    assert GET snapshot/load was called."""
    handler, hw, lcd, mock_get, mock_post = v3_system

    # Initial snapshot: main panel with wrench selected
    assert_snapshot(lcd.frames[-1], "v3_integration/preset_nav_A", update=snapshot_update)

    # wrench → pedalboard → preset
    handler.universal_encoder_select(1)  # pedalboard
    handler.universal_encoder_select(1)  # preset

    # Click to open preset menu
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    # Snapshot B: Menu open, "Clean" selected
    assert_snapshot(lcd.frames[-1], "v3_integration/preset_nav_B", update=snapshot_update)

    # Move to "Lead"
    handler.universal_encoder_select(1)
    # Snapshot C: "Lead" highlighted
    assert_snapshot(lcd.frames[-1], "v3_integration/preset_nav_C", update=snapshot_update)

    # Select "Lead"
    handler.universal_encoder_sw(switchstate.Value.RELEASED)

    # Assert GET to snapshot/load?id=1
    get_urls = _get_urls(mock_get)
    assert any("snapshot/load?id=1" in u for u in get_urls)

    # Snapshot D: Back to main, "Lead" shown
    assert_snapshot(lcd.frames[-1], "v3_integration/preset_nav_D", update=snapshot_update)


# ---------------------------------------------------------------------------
# Parameter editing via LCD
# ---------------------------------------------------------------------------


def test_v3_parameter_edit(v3_system, snapshot_update):
    """Navigate to a plugin, long-click to open parameter menu,
    select a parameter, tweak it, confirm, and assert the POST to
    parameter/pi_stomp_set."""
    handler, hw, lcd, mock_get, mock_post = v3_system

    # Add a plugin with a tweakable parameter to the current pedalboard
    gain_param = _make_parameter("Gain", "delay", value=0.5)
    plugin = _make_plugin("delay", category="Delay", parameters={"gain": gain_param})
    handler.current.pedalboard.plugins = [plugin]

    # Redraw with the new plugin
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # Navigate to the plugin (after preset in selection order)
    # wrench → pedalboard → preset → plugin
    handler.universal_encoder_select(1)  # pedalboard
    handler.universal_encoder_select(1)  # preset
    handler.universal_encoder_select(1)  # plugin

    # Long-click to open parameter menu
    handler.universal_encoder_sw(switchstate.Value.LONGPRESSED)
    # Snapshot: parameter menu showing "gain" (bypass filtered out)
    assert_snapshot(lcd.frames[-1], "v3_integration/param_menu", update=snapshot_update)

    # Select "gain" (first and only non-bypass param)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)

    # Snapshot: parameter dialog open
    assert_snapshot(lcd.frames[-1], "v3_integration/param_dialog", update=snapshot_update)

    # Tweak right 3 times
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)

    # Snapshot: value changed
    assert_snapshot(lcd.frames[-1], "v3_integration/param_tweaked", update=snapshot_update)

    # Close dialog (encoder click)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)

    # Poll to let the panel stack settle
    handler.poll_lcd_updates()

    # Snapshot: back to main panel
    assert_snapshot(lcd.frames[-1], "v3_integration/param_closed", update=snapshot_update)
