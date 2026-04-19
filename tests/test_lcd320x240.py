"""
Snapshot tests for lcd320x240.Lcd.
Run with --snapshot-update to accept new baselines.
"""

from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import PROJECT_ROOT, assert_snapshot
from pistomp.lcd320x240 import Lcd
import common.token as Token


class MockObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@pytest.fixture
def mock_handler():
    handler = MagicMock()
    handler.get_banks.return_value = {}
    handler.get_bank.return_value = None
    handler.get_num_footswitches.return_value = 4
    handler.hardware.version = 3
    handler.software_version = "1.0.0"
    handler.build_version = "20231027"
    handler.SystemState = "Running"
    handler.temperature = "45C"
    handler.throttled = "None"
    return handler


@pytest.fixture
def lcd(fake_lcd, mock_handler):
    with patch("pistomp.lcd320x240.LcdIli9341", return_value=fake_lcd):
        instance = Lcd(cwd=str(PROJECT_ROOT), handler=mock_handler)
    return instance, fake_lcd


def setup_main_ui(instance):
    plugins = [
        MockObject(
            instance_id="distortion",
            is_bypassed=lambda: False,
            category="Distortion",
            has_footswitch=True,
            controllers=[],
        ),
        MockObject(
            instance_id="delay", is_bypassed=lambda: False, category="Delay", has_footswitch=True, controllers=[]
        ),
        MockObject(
            instance_id="reverb", is_bypassed=lambda: True, category="Reverb", has_footswitch=True, controllers=[]
        ),
        MockObject(
            instance_id="chorus", is_bypassed=lambda: False, category="Modulator", has_footswitch=False, controllers=[]
        ),
    ]
    mock_pedalboard = MockObject(title="Rock Rig", plugins=plugins)
    mock_current = MockObject(
        pedalboard=mock_pedalboard,
        presets={0: "Clean", 1: "Lead"},
        preset_index=0,
        analog_controllers={
            "exp:pedal": {Token.ID: 0, Token.TYPE: Token.EXPRESSION, Token.COLOR: "Red", Token.NAME: "Wah"},
        },
    )
    mock_footswitches = [MockObject(id=i, enabled=False, get_display_label=lambda: "") for i in range(4)]
    instance.link_data(pedalboards=[mock_pedalboard], current=mock_current, footswitches=mock_footswitches)
    instance.draw_main_panel()


def test_splash_snapshot(lcd, snapshot_update):
    _, fake = lcd
    assert len(fake.frames) > 0, "expected at least one frame from splash_show during __init__"
    assert_snapshot(fake.frames[-1], "lcd320x240/splash", update=snapshot_update)


def test_main_panel_snapshot(lcd, snapshot_update):
    instance, fake = lcd
    setup_main_ui(instance)
    assert_snapshot(fake.frames[-1], "lcd320x240/main_panel", update=snapshot_update)


def test_analog_assignments_snapshot(lcd, snapshot_update):
    instance, fake = lcd

    # Custom mock data for this specific test
    mock_pedalboard = MockObject(title="Analog Test", plugins=[])
    mock_current = MockObject(
        pedalboard=mock_pedalboard,
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={
            "exp:pedal": {Token.ID: 0, Token.TYPE: Token.EXPRESSION, Token.COLOR: "Red", Token.NAME: "Wah"},
            "gain:knob": {Token.ID: 1, Token.TYPE: Token.KNOB, Token.COLOR: "Green", Token.NAME: "Gain"},
            "vol:knob": {Token.ID: 2, Token.TYPE: Token.VOLUME, Token.COLOR: "Blue", Token.NAME: "Volume"},
        },
    )

    instance.link_data(pedalboards=[mock_pedalboard], current=mock_current, footswitches=[])
    instance.draw_main_panel()

    assert_snapshot(fake.frames[-1], "lcd320x240/analog_assignments", update=snapshot_update)


def test_wifi_menu_snapshot(lcd, snapshot_update):
    instance, fake = lcd
    instance.handler.wifi_status = {"hotspot_active": False}
    setup_main_ui(instance)

    instance.draw_wifi_menu(None, None)
    assert_snapshot(fake.frames[-1], "lcd320x240/wifi_menu", update=snapshot_update)


def test_system_menu_snapshot(lcd, snapshot_update):
    instance, fake = lcd
    setup_main_ui(instance)

    instance.draw_system_menu(None, None)
    assert_snapshot(fake.frames[-1], "lcd320x240/system_menu", update=snapshot_update)


def test_parameter_dialog_snapshot(lcd, snapshot_update):
    instance, fake = lcd
    setup_main_ui(instance)

    mock_param = MockObject(
        name="Gain",
        instance_id="delay",
        value=0.5,
        minimum=0.0,
        maximum=1.0,
        type=MockObject(value=0),  # Default
    )

    instance.draw_parameter_dialog(mock_param)
    assert_snapshot(fake.frames[-1], "lcd320x240/parameter_dialog", update=snapshot_update)


def test_update_footswitch_off_snapshot(lcd, snapshot_update):
    instance, fake = lcd

    mock_fs = MockObject(id=0, enabled=True, get_display_label=lambda: "Dist", color="Red")

    # Draw main UI first to clear splash and set context
    mock_current = MockObject(
        pedalboard=MockObject(title="PB", plugins=[]), presets={0: "Clean"}, preset_index=0, analog_controllers={}
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()

    # Now update footswitch to OFF (bypassed)
    mock_fs.enabled = False  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)

    assert_snapshot(fake.frames[-1], "lcd320x240/footswitch_off", update=snapshot_update)


def test_update_footswitch_on_snapshot(lcd, snapshot_update):
    instance, fake = lcd

    mock_fs = MockObject(id=1, enabled=False, get_display_label=lambda: "Drive", color="Orange")

    # Draw main UI first
    mock_current = MockObject(
        pedalboard=MockObject(title="PB", plugins=[]), presets={0: "Clean"}, preset_index=0, analog_controllers={}
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()

    # Now update footswitch to ON (not bypassed)
    mock_fs.enabled = True  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)

    assert_snapshot(fake.frames[-1], "lcd320x240/footswitch_on", update=snapshot_update)


def test_tap_tempo_snapshot(lcd, snapshot_update):
    instance, fake = lcd

    # Mock footswitch with tap tempo enabled
    mock_fs = MockObject(
        id=2,
        enabled=True,
        get_display_label=lambda: "120",  # BPM
    )

    # Mock main UI
    mock_current = MockObject(
        pedalboard=MockObject(title="BPM Test", plugins=[]), presets={0: "Clean"}, preset_index=0, analog_controllers={}
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()

    # Trigger update to show BPM
    instance.update_footswitch(mock_fs)

    assert_snapshot(fake.frames[-1], "lcd320x240/tap_tempo", update=snapshot_update)
