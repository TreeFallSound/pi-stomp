"""
Snapshot tests for lcd320x240.Lcd.
Run with --snapshot-update to accept new baselines.
"""

from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import PROJECT_ROOT
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


def test_splash_snapshot(lcd, snapshot):
    _, fake = lcd
    assert len(fake.frames) > 0, "expected at least one frame from splash_show during __init__"
    snapshot()


def test_main_panel_snapshot(lcd, snapshot):
    instance, _ = lcd
    setup_main_ui(instance)
    snapshot()


def test_analog_assignments_snapshot(lcd, snapshot):
    instance, _ = lcd
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
    snapshot()


def test_wifi_menu_snapshot(lcd, snapshot):
    instance, _ = lcd
    instance.handler.wifi_status = {"hotspot_active": False}
    setup_main_ui(instance)
    instance.wifi_menu.open(None, None)
    snapshot("wifi_menu")



def test_system_menu_snapshot(lcd, snapshot):
    instance, _ = lcd
    setup_main_ui(instance)
    instance.draw_system_menu(None, None)
    snapshot()


def test_parameter_dialog_snapshot(lcd, snapshot):
    instance, _ = lcd
    setup_main_ui(instance)
    mock_param = MockObject(
        name="Gain",
        instance_id="delay",
        value=0.5,
        minimum=0.0,
        maximum=1.0,
        type=MockObject(value=0),
    )
    instance.draw_parameter_dialog(mock_param)
    snapshot()


def test_update_footswitch_off_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_fs = MockObject(id=0, enabled=True, get_display_label=lambda: "Dist", color="Red")
    mock_current = MockObject(
        pedalboard=MockObject(title="PB", plugins=[]), presets={0: "Clean"}, preset_index=0, analog_controllers={}
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    mock_fs.enabled = False  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)
    snapshot()


def test_update_footswitch_on_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_fs = MockObject(id=1, enabled=False, get_display_label=lambda: "Drive", color="Orange")
    mock_current = MockObject(
        pedalboard=MockObject(title="PB", plugins=[]), presets={0: "Clean"}, preset_index=0, analog_controllers={}
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    mock_fs.enabled = True  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)
    snapshot()


@pytest.mark.parametrize("status,expected", [
    ({"wifi_connected": False, "hotspot_active": True},  "wifi_orange.png"),
    ({"wifi_connected": True,  "hotspot_active": False}, "wifi_silver.png"),
    ({"wifi_connected": False, "hotspot_active": False}, "wifi_gray.png"),
])
def test_update_wifi_idle_icon_selection(lcd, mock_handler, status, expected):
    """When no ops pending, icon resolves to hotspot/connected/disconnected."""
    instance, _ = lcd
    mock_handler.wifi_manager.queue.pending_op_count.return_value = 0
    instance.draw_tools()  # creates w_wifi
    with patch.object(instance.w_wifi, "replace_img") as mock_replace:
        instance.update_wifi(status)
    mock_replace.assert_called_once()
    assert mock_replace.call_args[0][0].endswith(expected)


@pytest.mark.parametrize("status", [
    {"wifi_connected": True,  "hotspot_active": False},
    {"wifi_connected": False, "hotspot_active": True},
    {"wifi_connected": False, "hotspot_active": False},
])
def test_update_wifi_pending_shows_frame(lcd, mock_handler, status):
    """When ops are pending, the widget shows a preloaded animation frame."""
    instance, _ = lcd
    mock_handler.wifi_manager.queue.pending_op_count.return_value = 1
    instance.draw_tools()
    with patch.object(instance.w_wifi, "replace_img") as mock_replace:
        instance.update_wifi(status)
    mock_replace.assert_called_once()
    # Argument must be one of the preloaded PIL.Image frames, not a path.
    assert mock_replace.call_args[0][0] in instance._wifi_frames


def test_wifi_frames_are_preloaded(lcd):
    """Frames are decoded once at draw_tools time, not opened on every update."""
    instance, _ = lcd
    instance.draw_tools()
    assert len(instance._wifi_frames) == 3
    from PIL import Image as PILImage
    for f in instance._wifi_frames:
        assert isinstance(f, PILImage.Image)
        # .load() populates the .im attribute; absence means lazy/closed.
        assert f.im is not None


def test_update_wifi_noop_when_path_unchanged(lcd, mock_handler):
    """Repeated update_wifi calls with same status don't re-blit the icon."""
    instance, _ = lcd
    mock_handler.wifi_manager.queue.pending_op_count.return_value = 0
    instance.draw_tools()
    status = {"wifi_connected": True, "hotspot_active": False}
    instance.update_wifi(status)  # first call sets path
    with patch.object(instance.w_wifi, "refresh") as mock_refresh:
        instance.update_wifi(status)
        instance.update_wifi(status)
    mock_refresh.assert_not_called()


def test_tap_tempo_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_fs = MockObject(id=2, enabled=True, get_display_label=lambda: "120")
    mock_current = MockObject(
        pedalboard=MockObject(title="BPM Test", plugins=[]), presets={0: "Clean"}, preset_index=0, analog_controllers={}
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    instance.update_footswitch(mock_fs)
    snapshot()
