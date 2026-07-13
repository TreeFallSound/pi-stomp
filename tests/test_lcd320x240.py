"""
Snapshot tests for lcd320x240.Lcd.
Run with --snapshot-update to accept new baselines.
"""

from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import PROJECT_ROOT
from tests import pedalboard_fixtures
from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextLayer,
    ContextRef,
    ContextStack,
    ControlClass,
    ControlRef,
    EventKind,
    ParamEffect,
    ShadowState,
)
from pistomp.encoder_controller import EncoderController
from pistomp.footswitch import Footswitch
from pistomp.lcd320x240 import Lcd
from pistomp.taptempo import TapTempo
import common.token as Token
from uilib.misc import InputEvent
from modalapi.connections import Connection, Endpoint, EndpointKind


class MockObject:
    preset_callback_arg = None  # footswitch default; override via kwargs

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @property
    def subtitle(self):
        return None

    @property
    def tile_active_color(self):
        return None

    @property
    def tile_border(self):
        return None

    @property
    def panel_cls(self):
        return None

    @property
    def intercept_shortpress(self):
        return False


@pytest.fixture
def mock_handler():
    handler = MagicMock()
    handler.get_banks.return_value = {}
    handler.get_bank.return_value = None
    handler.get_num_footswitches.return_value = 4
    handler.hardware.version = 3
    handler.software_version = "1.0.0"
    handler.get_software_version.return_value = "1.0.0"
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


def _enc_step(instance, d, multiplier=1.0):
    """Step the top panel's nav selector, as the retired lcd.enc_step did."""
    if d == 0:
        return
    instance.pstack.input_step(1 if d > 0 else -1, abs(d), multiplier)


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
            uri="mock://reverb",
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
            uri="mock://chorus",
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
    mock_footswitches = [
        MockObject(id=i, toggled=False, get_display_label=lambda: "", parameter=None) for i in range(4)
    ]
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


def test_system_info_dialog_snapshot(lcd, snapshot):
    """The System Info MessageDialog must show all 5 lines without clipping."""
    instance, _ = lcd
    setup_main_ui(instance)
    instance.draw_system_info_dialog(None)
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


def test_parameter_dialog_batches_detents(lcd):
    """A tick's worth of detents advances the value once, in a single render.

    On v2 the nav encoder is the only way into this dialog, so a per-detent
    render would put a fast spin over the 10ms tick budget.
    """
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
    dialog = instance.draw_parameter_dialog(mock_param)

    renders = 0
    original = dialog._draw_graph

    def counting_draw_graph():
        nonlocal renders
        renders += 1
        original()

    dialog._draw_graph = counting_draw_graph
    _enc_step(instance, 3)

    # 0.5 sits on step 63 of the 128-step grid; 3 detents → step 66.
    assert dialog.parameter.value == pytest.approx(dialog.steps.values[66])
    assert renders == 1


def test_parameter_dialog_applies_encoder_multiplier(lcd):
    """The nav encoder's speed factor scales the step; menus ignore it."""
    instance, _ = lcd
    setup_main_ui(instance)
    mock_param = MockObject(
        name="Gain",
        instance_id="delay",
        value=0.0,
        minimum=0.0,
        maximum=1.0,
        type=MockObject(value=0),
        get_taper=lambda: 1,
        format=lambda v: f"{v:.2f}",
    )
    dialog = instance.draw_parameter_dialog(mock_param)

    # 2 detents at 3x = 6 grid steps from the bottom.
    _enc_step(instance, 2, multiplier=3.0)
    assert dialog.parameter.value == pytest.approx(dialog.steps.values[6])


def test_menu_ignores_encoder_multiplier(lcd):
    """Selection is discrete: a fast spin must not skip extra widgets."""
    instance, _ = lcd
    setup_main_ui(instance)
    panel = instance.pstack.current

    _enc_step(instance, 2, multiplier=4.0)
    accelerated = panel.sel_ref

    _enc_step(instance, -2, multiplier=4.0)
    _enc_step(instance, 2)

    assert panel.sel_ref is accelerated


def test_menu_batches_detents_into_one_selection_move(lcd):
    """A batch of detents lands on the same widget as the same number of singles."""
    instance, _ = lcd
    setup_main_ui(instance)
    panel = instance.pstack.current

    _enc_step(instance, 3)
    batched = panel.sel_ref

    _enc_step(instance, -3)
    for _ in range(3):
        _enc_step(instance, 1)

    assert panel.sel_ref is batched


def _mock_param(**overrides):
    defaults = dict(
        name="Gain",
        symbol="gain",
        instance_id="delay",
        value=0.5,
        minimum=0.0,
        maximum=1.0,
        type=MockObject(value=0),
        get_taper=lambda: 1,
        format=lambda v: f"{v:.2f}",
    )
    defaults.update(overrides)
    return MockObject(**defaults)


def test_tweak_dialog_has_no_timeout_and_shows_close_button(lcd):
    """Tweak-encoder edits (display_parameter_value) must stay open with a Close button."""
    instance, _ = lcd
    setup_main_ui(instance)
    d = instance.draw_parameter_dialog(_mock_param())
    assert d.timeout is None
    assert any(getattr(w, "text", None) == "Close" for w in d.children)


def test_tweak_dialog_never_autocloses(lcd):
    instance, _ = lcd
    setup_main_ui(instance)
    d = instance.draw_parameter_dialog(_mock_param())
    d.parameter_value_change(1)  # simulate a tweak; reset_timeout() is a no-op when timeout is None
    assert d.expiry_time is None
    d.tick()
    assert d.parent is not None  # still open


def test_tweak_button_click_closes_parameter_dialog(lcd):
    """A tweak/volume encoder button press confirms & closes an open param dialog
    (the NAV button isn't the only way to dismiss it)."""
    from pistomp.controller import Controller
    from pistomp.input.event import SwitchEvent, SwitchEventKind

    instance, _ = lcd
    setup_main_ui(instance)
    d = instance.draw_parameter_dialog(_mock_param())
    assert d.parent is not None  # open

    knob = Controller(midi_channel=0, midi_CC=None)
    knob.type = Token.KNOB
    knob.id = 1
    instance.handle(SwitchEvent(controller=knob, kind=SwitchEventKind.PRESS, timestamp=0.0))
    assert d.parent is None  # closed by the tweak-button click


def test_volume_dialog_autocloses_and_has_no_close_button(lcd):
    """The Volume/audio-card dialog must autoclose and never show a Close button."""
    instance, _ = lcd
    setup_main_ui(instance)
    d = instance.draw_audio_parameter_dialog(_mock_param(name="Volume"), commit_callback=lambda *_: None)
    assert d.timeout is not None
    assert not any(getattr(w, "text", None) == "Close" for w in d.children)


def test_volume_dialog_autocloses_after_timeout(lcd):
    instance, _ = lcd
    setup_main_ui(instance)
    d = instance.draw_audio_parameter_dialog(_mock_param(name="Volume"), commit_callback=lambda *_: None)
    d.expiry_time = 1  # force expiry without sleeping
    d.tick()
    assert d.parent is None  # popped


def test_volume_dialog_still_autocloses_after_being_updated_again(lcd):
    """Regression: turning the volume encoder again (update_value) must keep autoclose armed."""
    instance, _ = lcd
    setup_main_ui(instance)
    d = instance.draw_audio_parameter_dialog(_mock_param(name="Volume"), commit_callback=lambda *_: None)
    d.update_value(0.7)
    assert d.timeout is not None
    d.expiry_time = 1
    d.tick()
    assert d.parent is None


def test_plugin_longpress_opens_parameter_menu(lcd, snapshot):
    """Long-click on a selected plugin widget opens the parameter menu."""
    instance, _ = lcd
    setup_main_ui(instance)
    # Select the first plugin widget (distortion)
    instance.main_panel.sel_widget(instance.w_plugins[0])
    # Simulate the long-press event that travels through the panel stack
    instance.main_panel.input_event(InputEvent.LONG_CLICK)
    snapshot()


def _footswitch_row(plugin, symbol, control_id, shadow_state=ShadowState.ACTIVE):
    return BindingDecl(
        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=control_id),
        event_kind=EventKind.PRESS,
        effects=(ParamEffect(plugin=plugin, symbol=symbol),),
        context=ContextRef(kind=ContextKind.PEDALBOARD),
        shadow_state=shadow_state,
    )


def test_footswitch_badge_letter_from_effective_table(lcd):
    """(A)-(D): footswitch_badge_letter reads the effective binding table and
    resolves the physical footswitch's slot letter, not the CC identity."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters["gain"]

    fs = Footswitch(id=2, led_pin=None, pixel=None, midi_CC=10, midi_channel=0, refresh_callback=MagicMock())
    instance.handler.hardware.controllers = {"0:10": fs}
    instance.handler.effective_table = ContextStack(layers=[
        ContextLayer(
            ref=ContextRef(kind=ContextKind.PEDALBOARD),
            rows={(ControlClass.FOOTSWITCH, EventKind.PRESS): [_footswitch_row(distortion, gain_param.name, "0:10")]},
        )
    ])

    assert instance.footswitch_badge_letter(distortion, gain_param) == "C"


def test_footswitch_badge_letter_none_when_shadowed(lcd):
    """Badge honesty (requirement 5): a SHADOWED row must not surface a badge."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters["gain"]

    fs = Footswitch(id=0, led_pin=None, pixel=None, midi_CC=10, midi_channel=0, refresh_callback=MagicMock())
    instance.handler.hardware.controllers = {"0:10": fs}
    row = _footswitch_row(distortion, "gain", "0:10", shadow_state=ShadowState.SHADOWED)
    instance.handler.effective_table = ContextStack(layers=[
        ContextLayer(ref=ContextRef(kind=ContextKind.PEDALBOARD), rows={(ControlClass.FOOTSWITCH, EventKind.PRESS): [row]})
    ])

    assert instance.footswitch_badge_letter(distortion, gain_param) is None


def _analog_row(plugin, symbol, control_id, shadow_state=ShadowState.ACTIVE):
    return BindingDecl(
        control=ControlRef(cls=ControlClass.ANALOG, id=control_id),
        event_kind=EventKind.ROTATE,
        effects=(ParamEffect(plugin=plugin, symbol=symbol),),
        context=ContextRef(kind=ContextKind.PEDALBOARD),
        shadow_state=shadow_state,
    )


def test_tweak_badge_number_from_effective_table(lcd):
    """1/2/3: tweak_badge_number reads the effective table's legacy
    ANALOG-class binding — the TTL/config-bound tweak encoder, independent of
    any open custom panel (TWEAK rows themselves are always panel-scoped)."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters["gain"]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=2)
    instance.handler.hardware.controllers = {"encoder2": enc}
    instance.handler.effective_table = ContextStack(layers=[
        ContextLayer(
            ref=ContextRef(kind=ContextKind.PEDALBOARD),
            rows={(ControlClass.ANALOG, EventKind.ROTATE): [_analog_row(distortion, gain_param.name, "encoder2")]},
        )
    ])

    assert instance.tweak_badge_number(distortion, gain_param) == 2


def test_tweak_badge_number_none_when_shadowed(lcd):
    """Badge honesty: a SHADOWED analog row must not surface a tweak badge."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters["gain"]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=2)
    instance.handler.hardware.controllers = {"encoder2": enc}
    row = _analog_row(distortion, gain_param.name, "encoder2", shadow_state=ShadowState.SHADOWED)
    instance.handler.effective_table = ContextStack(layers=[
        ContextLayer(ref=ContextRef(kind=ContextKind.PEDALBOARD), rows={(ControlClass.ANALOG, EventKind.ROTATE): [row]})
    ])

    assert instance.tweak_badge_number(distortion, gain_param) is None


def test_parameter_menu_shows_tweak_badge(lcd, snapshot):
    """The parameter-list menu prepends the digit badge to a tweak-bound row,
    same slot the footswitch letter uses (mutually exclusive: a parameter has
    exactly one `binding`)."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters["gain"]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=3)
    instance.handler.hardware.controllers = {"encoder3": enc}
    instance.handler.effective_table = ContextStack(layers=[
        ContextLayer(
            ref=ContextRef(kind=ContextKind.PEDALBOARD),
            rows={(ControlClass.ANALOG, EventKind.ROTATE): [_analog_row(distortion, gain_param.name, "encoder3")]},
        )
    ])

    instance.draw_parameter_menu(distortion)
    snapshot()


def test_parameter_dialog_shows_tweak_badge_snapshot(lcd, snapshot):
    """Parameterdialog badges itself ② when opened for a parameter that's
    TTL/config-bound to a physical tweak encoder."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters["gain"]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=2)
    instance.handler.hardware.controllers = {"encoder2": enc}
    instance.handler.effective_table = ContextStack(layers=[
        ContextLayer(
            ref=ContextRef(kind=ContextKind.PEDALBOARD),
            rows={(ControlClass.ANALOG, EventKind.ROTATE): [_analog_row(distortion, gain_param.name, "encoder2")]},
        )
    ])

    instance.draw_parameter_dialog(gain_param)
    snapshot()


def test_parameter_menu_shows_footswitch_badge(lcd, snapshot):
    """The parameter-list menu prepends the (X) badge to a footswitch-bound row."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters["gain"]

    fs = Footswitch(id=0, led_pin=None, pixel=None, midi_CC=10, midi_channel=0, refresh_callback=MagicMock())
    instance.handler.hardware.controllers = {"0:10": fs}
    instance.handler.effective_table = ContextStack(layers=[
        ContextLayer(
            ref=ContextRef(kind=ContextKind.PEDALBOARD),
            rows={(ControlClass.FOOTSWITCH, EventKind.PRESS): [_footswitch_row(distortion, gain_param.name, "0:10")]},
        )
    ])

    instance.draw_parameter_menu(distortion)
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
    tt = TapTempo()
    tt.enable(True)
    tt.set_bpm(120.0)
    mock_fs = MockObject(id=2, toggled=True, get_display_label=lambda: "120", parameter=None, taptempo=tt)
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
    tt = TapTempo()
    tt.enable(True)
    tt.set_bpm(120.0)
    # Mirrors Footswitch.get_display_label(): BPM when enabled, empty when not.
    mock_fs = MockObject(
        id=2,
        toggled=True,
        get_display_label=lambda: str(round(tt.get_bpm())) if tt.is_enabled() else "",
        parameter=None,
        taptempo=tt,
    )
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

    tt.enable(False)
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
    mock_footswitches = [
        MockObject(id=i, toggled=False, get_display_label=lambda: "", parameter=None) for i in range(4)
    ]
    instance.link_data(pedalboards=[pb], current=mock_current, footswitches=mock_footswitches)
    instance.draw_main_panel()


@pytest.mark.parametrize("topology", ["blank", "linear", "parallel", "tall_parallel", "stereo_chain", "split_merge"])
def test_routing_snapshot(lcd, snapshot, topology):
    instance, _ = lcd
    _setup_pedalboard(instance, pedalboard_fixtures.REGISTRY[topology]())
    snapshot(topology)


def test_tall_parallel_scrolled_to_last(lcd, snapshot):
    """Selecting the last plugin in col 0 must scroll it clear of the footswitch bar."""
    instance, _ = lcd
    pb = pedalboard_fixtures.tall_parallel()
    _setup_pedalboard(instance, pb)
    snapshot("initial")
    tiles = instance.grid_panel.tile_order
    col0_x = tiles[0].box.x0
    col0_count = sum(1 for t in tiles if t.box.x0 == col0_x)
    for _ in range(col0_count - 1 + 3):
        instance.main_panel.sel_next()
    snapshot("scrolled_to_last")
