"""
Snapshot tests for lcd320x240.Lcd.
Run with --snapshot-update to accept new baselines.
"""

from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import PROJECT_ROOT
from tests import pedalboard_fixtures
from pistomp.lcd320x240 import Lcd
import common.token as Token
from uilib.misc import InputEvent
from modalapi.connections import Connection, Endpoint, EndpointKind


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
    # MagicMock would auto-truthify `ethernet_manager.carrier_up` and surface
    # the Wired Connection row in every wifi-menu snapshot. Pin it off here;
    # tests that exercise the ethernet flow can override per-test.
    handler.ethernet_manager = None
    return handler


@pytest.fixture
def lcd(fake_lcd, mock_handler):
    with patch("pistomp.lcd320x240.LcdIli9341", return_value=fake_lcd):
        instance = Lcd(cwd=str(PROJECT_ROOT), handler=mock_handler)
    fake_lcd.flush_callback = instance.pstack.poll_updates
    return instance, fake_lcd


def setup_main_ui(instance):
    mock_gain = MockObject(
        name="Gain",
        instance_id="distortion",
        value=0.5,
        minimum=0.0,
        maximum=1.0,
        type=MockObject(value=0),
        get_taper=lambda: 1,
        format=lambda v: f"{v:.2f}",
    )
    mock_time = MockObject(
        name="Time",
        instance_id="delay",
        value=0.3,
        minimum=0.0,
        maximum=1.0,
        type=MockObject(value=0),
        get_taper=lambda: 1,
        format=lambda v: f"{v:.2f}",
    )
    mock_mix = MockObject(
        name="Mix",
        instance_id="reverb",
        value=0.4,
        minimum=0.0,
        maximum=1.0,
        type=MockObject(value=0),
        get_taper=lambda: 1,
        format=lambda v: f"{v:.2f}",
    )
    plugins = [
        MockObject(
            instance_id="distortion",
            uri="mock://distortion",
            display_name="distortion",
            is_bypassed=lambda: False,
            category="Distortion",
            has_footswitch=True,
            controllers=[],
            parameters={":bypass": MockObject(name=":bypass"), "gain": mock_gain},
        ),
        MockObject(
            instance_id="delay",
            uri="mock://delay",
            display_name="delay",
            is_bypassed=lambda: False,
            category="Delay",
            has_footswitch=True,
            controllers=[],
            parameters={":bypass": MockObject(name=":bypass"), "time": mock_time},
        ),
        MockObject(
            instance_id="reverb",
            uri="mock://reverb",
        ),
        MockObject(
            instance_id="reverb",
            display_name="reverb",
            is_bypassed=lambda: True,
            category="Reverb",
            has_footswitch=True,
            controllers=[],
            parameters={":bypass": MockObject(name=":bypass"), "mix": mock_mix},
        ),
        MockObject(
            instance_id="chorus",
            uri="mock://chorus",
        ),
        MockObject(
            instance_id="chorus",
            display_name="chorus",
            is_bypassed=lambda: False,
            category="Modulator",
            has_footswitch=False,
            controllers=[],
            parameters={":bypass": MockObject(name=":bypass")},
        ),
    ]
    ids = [p.instance_id for p in plugins]  # pyright: ignore[reportAttributeAccessIssue]
    connections = [
        Connection(
            src=Endpoint(kind=EndpointKind.PLUGIN, id=ids[i], port_symbol="", port_idx=0),
            dst=Endpoint(kind=EndpointKind.PLUGIN, id=ids[i + 1], port_symbol="", port_idx=0),
        )
        for i in range(len(ids) - 1)
    ]
    mock_pedalboard = MockObject(title="Rock Rig", plugins=plugins, connections=connections)
    mock_current = MockObject(
        pedalboard=mock_pedalboard,
        presets={0: "Clean", 1: "Lead"},
        preset_index=0,
        analog_controllers={
            "exp:pedal": {Token.ID: 0, Token.TYPE: Token.EXPRESSION, Token.COLOR: "Red", Token.NAME: "Wah"},
        },
    )
    mock_footswitches = [MockObject(id=i, toggled=False, get_display_label=lambda: "", parameter=None) for i in range(4)]
    instance.link_data(pedalboards=[mock_pedalboard], current=mock_current, footswitches=mock_footswitches)
    instance.draw_main_panel()


def test_splash_snapshot(lcd, snapshot):
    _, fake = lcd
    fake.flush()
    assert len(fake.frames) > 0, "expected at least one frame from splash_show during __init__"
    snapshot()


def test_main_panel_snapshot(lcd, snapshot):
    instance, _ = lcd
    setup_main_ui(instance)
    snapshot()


def test_analog_assignments_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_pedalboard = MockObject(title="Analog Test", plugins=[], connections=[])
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
        get_taper=lambda: 1,
        format=lambda v: f"{v:.2f}",
    )
    instance.draw_parameter_dialog(mock_param)
    snapshot()


def test_plugin_longpress_opens_parameter_menu(lcd, snapshot):
    """Long-click on a selected plugin widget opens the parameter menu."""
    instance, _ = lcd
    setup_main_ui(instance)
    # Select the first plugin widget (distortion)
    instance.main_panel.sel_widget(instance.w_plugins[0])
    # Simulate the long-press event that travels through the panel stack
    instance.main_panel.input_event(InputEvent.LONG_CLICK)
    snapshot()


def test_update_footswitch_off_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_fs = MockObject(id=0, toggled=True, get_display_label=lambda: "Dist", color="Red", parameter=None)
    mock_current = MockObject(
        pedalboard=MockObject(title="PB", plugins=[], connections=[]),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    mock_fs.toggled = False  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)
    snapshot()


def test_update_footswitch_on_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_fs = MockObject(id=1, toggled=False, get_display_label=lambda: "Drive", color="Orange", parameter=None)
    mock_current = MockObject(
        pedalboard=MockObject(title="PB", plugins=[], connections=[]),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    mock_fs.toggled = True  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)
    snapshot()


@pytest.mark.parametrize(
    "status,expected",
    [
        ({"wifi_connected": False, "hotspot_active": True}, "wifi_orange.png"),
        ({"wifi_connected": True, "hotspot_active": False}, "wifi_silver.png"),
        ({"wifi_connected": False, "hotspot_active": False}, "wifi_gray.png"),
    ],
)
def test_update_wifi_idle_icon_selection(lcd, mock_handler, status, expected):
    """When no ops pending, icon resolves to hotspot/connected/disconnected."""
    instance, _ = lcd
    mock_handler.wifi_manager.queue.pending_op_count.return_value = 0
    instance.draw_tools()  # creates w_wifi
    with patch.object(instance.w_wifi, "replace_img") as mock_replace:
        instance.update_wifi(status)
    mock_replace.assert_called_once()
    assert mock_replace.call_args[0][0].endswith(expected)


@pytest.mark.parametrize(
    "status",
    [
        {"wifi_connected": True, "hotspot_active": False},
        {"wifi_connected": False, "hotspot_active": True},
        {"wifi_connected": False, "hotspot_active": False},
    ],
)
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
    import pygame

    instance, _ = lcd
    instance.draw_tools()
    assert len(instance._wifi_frames) == 3
    for f in instance._wifi_frames:
        assert isinstance(f, pygame.Surface)
        assert f.get_width() > 0 and f.get_height() > 0


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
    mock_fs = MockObject(id=2, toggled=True, get_display_label=lambda: "120", parameter=None)
    mock_current = MockObject(
        pedalboard=MockObject(title="BPM Test", plugins=[], connections=[]),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    instance.update_footswitch(mock_fs)
    snapshot()


def test_tap_tempo_disable_clears_label(lcd, snapshot):
    instance, _ = lcd
    labels = ["120"]
    mock_fs = MockObject(id=2, toggled=True, get_display_label=lambda: labels[0], parameter=None)
    mock_current = MockObject(
        pedalboard=MockObject(title="BPM Test", plugins=[], connections=[]),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    instance.update_footswitch(mock_fs)
    snapshot("tap_tempo_enabled")

    labels[0] = ""
    mock_fs.toggled = False  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)
    snapshot("tap_tempo_disabled")


def test_update_footswitch_clears_label_when_empty(lcd):
    instance, _ = lcd
    labels = ["120"]

    def get_label():
        return labels[0]

    mock_fs = MockObject(id=2, toggled=True, get_display_label=get_label, parameter=None)
    mock_current = MockObject(
        pedalboard=MockObject(title="BPM Test", plugins=[], connections=[]),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    instance.update_footswitch(mock_fs)

    wfs = instance.w_footswitches[0]
    assert wfs.label == "120"

    labels[0] = ""
    mock_fs.toggled = False  # pyright: ignore[reportAttributeAccessIssue]
    instance.update_footswitch(mock_fs)

    assert wfs.label == "", f"Expected empty label after tap tempo disabled, got: {wfs.label!r}"


def _setup_pedalboard(instance, pb):
    mock_current = MockObject(
        pedalboard=pb,
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    mock_footswitches = [MockObject(id=i, toggled=False, get_display_label=lambda: "", parameter=None) for i in range(4)]
    instance.link_data(pedalboards=[pb], current=mock_current, footswitches=mock_footswitches)
    instance.draw_main_panel()


@pytest.mark.parametrize("topology", ["blank", "linear", "parallel", "stereo", "tall_parallel"])
def test_routing_snapshot(lcd, snapshot, topology):
    instance, _ = lcd
    _setup_pedalboard(instance, pedalboard_fixtures.REGISTRY[topology]())
    snapshot(topology)


def test_tall_parallel_scrolled_to_last(lcd, snapshot):
    """Selecting the last plugin in a 5-row tall pedalboard must scroll it
    clear of the footswitch bar (bottom_inset ensures this)."""
    instance, _ = lcd
    pb = pedalboard_fixtures.tall_parallel()
    _setup_pedalboard(instance, pb)
    snapshot("initial")
    for _ in range(len(pb.plugins) + 2):
        instance.main_panel.sel_next()
    snapshot("scrolled_to_last")
