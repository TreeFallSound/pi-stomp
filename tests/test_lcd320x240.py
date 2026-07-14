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
from common.parameter import BYPASS_SYMBOL, Parameter, PortInfo, Symbol
from pistomp.encoder_controller import EncoderController
from pistomp.footswitch import Footswitch
from pistomp.lcd320x240 import Lcd
from pistomp.taptempo import TapTempo
import common.token as Token
from uilib.misc import InputEvent
from modalapi.connections import Connection, Endpoint, EndpointKind
from modalapi.pedalboard import Pedalboard
from modalapi.plugin import Plugin
from pistomp.current import Current


def _make_plugin(
    instance_id: str,
    uri: str | None = None,
    category: str | None = None,
    has_footswitch: bool = False,
    bypassed: bool = False,
    parameters: dict[Symbol, Parameter] | None = None,
) -> Plugin:
    bypass_info: PortInfo = {"shortName": "bypass", "symbol": BYPASS_SYMBOL, "ranges": {"minimum": 0, "maximum": 1}}
    all_params: dict[Symbol, Parameter] = dict(parameters or {})
    all_params[BYPASS_SYMBOL] = Parameter(bypass_info, 1.0 if bypassed else 0.0, None, instance_id)
    plugin = Plugin(instance_id, all_params, {}, category, uri=uri)
    plugin.has_footswitch = has_footswitch
    return plugin


def _make_pedalboard(title: str, plugins: list[Plugin], connections: list[Connection]) -> Pedalboard:
    pedalboard = Pedalboard(title, bundle="")
    pedalboard.plugins = plugins
    pedalboard.connections = connections
    return pedalboard


def _make_footswitch(id: int, toggled: bool = False, display_label: str = "", taptempo=None) -> Footswitch:
    fs = Footswitch(
        id=id, led_pin=None, pixel=None, midi_CC=1, midi_channel=0,
        refresh_callback=lambda *a, **k: None, taptempo=taptempo,
    )
    fs.toggled = toggled
    fs.display_label = display_label
    return fs


def _real_param(
    name: str = "Gain",
    symbol: str = "gain",
    instance_id: str = "delay",
    value: float = 0.5,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> Parameter:
    """A real Parameter with the same defaults as the old _mock_param helper,
    so the dialog tests exercise the reactive property path."""
    info: PortInfo = {
        "shortName": name,
        "symbol": symbol,
        "ranges": {"minimum": minimum, "maximum": maximum},
    }
    return Parameter(info, value, None, instance_id)


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
    mock_gain = _real_param(name="Gain", symbol="gain", instance_id="distortion", value=0.5)
    mock_time = _real_param(name="Time", symbol="time", instance_id="delay", value=0.3)
    mock_mix = _real_param(name="Mix", symbol="mix", instance_id="reverb", value=0.4)
    plugins = [
        _make_plugin(
            "distortion", uri="mock://distortion", category="Distortion", has_footswitch=True,
            parameters={Symbol("gain"): mock_gain},
        ),
        _make_plugin(
            "delay", uri="mock://delay", category="Delay", has_footswitch=True,
            parameters={Symbol("time"): mock_time},
        ),
        _make_plugin(
            "reverb", uri="mock://reverb", category="Reverb", has_footswitch=True, bypassed=True,
            parameters={Symbol("mix"): mock_mix},
        ),
        _make_plugin("chorus", uri="mock://chorus", category="Modulator", has_footswitch=False),
    ]
    ids = [p.instance_id for p in plugins]
    connections = [
        Connection(
            src=Endpoint(kind=EndpointKind.PLUGIN, id=ids[i], port_symbol="", port_idx=0),
            dst=Endpoint(kind=EndpointKind.PLUGIN, id=ids[i + 1], port_symbol="", port_idx=0),
        )
        for i in range(len(ids) - 1)
    ]
    mock_pedalboard = _make_pedalboard("Rock Rig", plugins, connections)
    mock_current = Current(
        pedalboard=mock_pedalboard,
        presets={0: "Clean", 1: "Lead"},
        preset_index=0,
        analog_controllers={
            "exp:pedal": {Token.ID: 0, Token.TYPE: Token.EXPRESSION},
        },
    )
    mock_footswitches = [_make_footswitch(i) for i in range(4)]
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
    mock_pedalboard = _make_pedalboard("Analog Test", [], [])
    mock_current = Current(
        pedalboard=mock_pedalboard,
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={
            "exp:pedal": {Token.ID: 0, Token.TYPE: Token.EXPRESSION},
            "gain:knob": {Token.ID: 1, Token.TYPE: Token.KNOB},
            "vol:knob": {Token.ID: 2, Token.TYPE: Token.VOLUME},
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
    mock_param = _real_param(name="Gain", instance_id="delay", value=0.5)
    instance.draw_parameter_dialog(mock_param)
    snapshot()


def test_parameter_dialog_batches_detents(lcd):
    """A tick's worth of detents advances the value once, in a single render.

    On v2 the nav encoder is the only way into this dialog, so a per-detent
    render would put a fast spin over the 10ms tick budget.
    """
    instance, _ = lcd
    setup_main_ui(instance)
    mock_param = _real_param(name="Gain", instance_id="delay", value=0.5)
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
    mock_param = _real_param(name="Gain", instance_id="delay", value=0.0)
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
    return _real_param(**overrides)


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
    gain_param = distortion.parameters[Symbol("gain")]

    fs = Footswitch(id=2, led_pin=None, pixel=None, midi_CC=10, midi_channel=0, refresh_callback=MagicMock())
    instance.handler.hardware.controllers = {"0:10": fs}
    instance.handler.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.FOOTSWITCH, EventKind.PRESS): [_footswitch_row(distortion, gain_param.symbol, "0:10")]
                },
            )
        ]
    )

    assert instance.footswitch_badge_letter(distortion, gain_param) == "C"


def test_footswitch_badge_letter_none_when_shadowed(lcd):
    """Badge honesty (requirement 5): a SHADOWED row must not surface a badge."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters[Symbol("gain")]

    fs = Footswitch(id=0, led_pin=None, pixel=None, midi_CC=10, midi_channel=0, refresh_callback=MagicMock())
    instance.handler.hardware.controllers = {"0:10": fs}
    row = _footswitch_row(distortion, "gain", "0:10", shadow_state=ShadowState.SHADOWED)
    instance.handler.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD), rows={(ControlClass.FOOTSWITCH, EventKind.PRESS): [row]}
            )
        ]
    )

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
    gain_param = distortion.parameters[Symbol("gain")]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=2)
    instance.handler.hardware.controllers = {"encoder2": enc}
    instance.handler.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.ANALOG, EventKind.ROTATE): [_analog_row(distortion, gain_param.symbol, "encoder2")]
                },
            )
        ]
    )

    assert instance.tweak_badge_number(distortion, gain_param) == 2


def test_tweak_badge_number_none_when_shadowed(lcd):
    """Badge honesty: a SHADOWED analog row must not surface a tweak badge."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters[Symbol("gain")]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=2)
    instance.handler.hardware.controllers = {"encoder2": enc}
    row = _analog_row(distortion, gain_param.symbol, "encoder2", shadow_state=ShadowState.SHADOWED)
    instance.handler.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD), rows={(ControlClass.ANALOG, EventKind.ROTATE): [row]}
            )
        ]
    )

    assert instance.tweak_badge_number(distortion, gain_param) is None


def test_parameter_menu_shows_tweak_badge(lcd, snapshot):
    """The parameter window shows badge on list rows for tweak-bound params."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters[Symbol("gain")]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=3)
    instance.handler.hardware.controllers = {"encoder3": enc}
    instance.handler.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.ANALOG, EventKind.ROTATE): [_analog_row(distortion, gain_param.symbol, "encoder3")]
                },
            )
        ]
    )

    # Long-press opens ParameterWindow
    instance.main_panel.sel_widget(instance.w_plugins[0])
    instance.main_panel.input_event(InputEvent.LONG_CLICK)
    snapshot()


def test_parameter_dialog_shows_tweak_badge_snapshot(lcd, snapshot):
    """Parameterdialog badges itself ② when opened for a parameter that's
    TTL/config-bound to a physical tweak encoder."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters[Symbol("gain")]

    enc = EncoderController(d_pin=None, clk_pin=None, type=None, id=2)
    instance.handler.hardware.controllers = {"encoder2": enc}
    instance.handler.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.ANALOG, EventKind.ROTATE): [_analog_row(distortion, gain_param.symbol, "encoder2")]
                },
            )
        ]
    )

    instance.draw_parameter_dialog(gain_param)
    snapshot()


def test_parameter_menu_shows_footswitch_badge(lcd, snapshot):
    """The parameter window shows badge on list rows for footswitch-bound params."""
    instance, _ = lcd
    setup_main_ui(instance)
    distortion = instance.current.pedalboard.plugins[0]
    gain_param = distortion.parameters[Symbol("gain")]

    fs = Footswitch(id=0, led_pin=None, pixel=None, midi_CC=10, midi_channel=0, refresh_callback=MagicMock())
    instance.handler.hardware.controllers = {"0:10": fs}
    instance.handler.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.FOOTSWITCH, EventKind.PRESS): [_footswitch_row(distortion, gain_param.symbol, "0:10")]
                },
            )
        ]
    )

    # Long-press opens ParameterWindow
    instance.main_panel.sel_widget(instance.w_plugins[0])
    instance.main_panel.input_event(InputEvent.LONG_CLICK)
    snapshot()


def test_update_footswitch_off_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_fs = _make_footswitch(0, toggled=True, display_label="Dist")
    mock_current = Current(
        pedalboard=_make_pedalboard("PB", [], []),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    mock_fs.toggled = False
    instance.update_footswitch(mock_fs)
    snapshot()


def test_update_footswitch_on_snapshot(lcd, snapshot):
    instance, _ = lcd
    mock_fs = _make_footswitch(1, toggled=False, display_label="Drive")
    mock_current = Current(
        pedalboard=_make_pedalboard("PB", [], []),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    mock_fs.toggled = True
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
    mock_fs = _make_footswitch(2, toggled=True, taptempo=tt)
    mock_current = Current(
        pedalboard=_make_pedalboard("BPM Test", [], []),
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
    mock_fs = _make_footswitch(2, toggled=True, taptempo=tt)
    mock_current = Current(
        pedalboard=_make_pedalboard("BPM Test", [], []),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    instance.update_footswitch(mock_fs)
    snapshot("tap_tempo_enabled")

    tt.enable(False)
    mock_fs.toggled = False
    instance.update_footswitch(mock_fs)
    snapshot("tap_tempo_disabled")


def test_update_footswitch_clears_label_when_empty(lcd):
    instance, _ = lcd
    mock_fs = _make_footswitch(2, toggled=True, display_label="120")
    mock_current = Current(
        pedalboard=_make_pedalboard("BPM Test", [], []),
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    instance.link_data(pedalboards=[], current=mock_current, footswitches=[mock_fs])
    instance.draw_main_panel()
    instance.update_footswitch(mock_fs)

    wfs = instance.w_footswitches[0]
    assert wfs.label == "120"

    mock_fs.display_label = ""
    mock_fs.toggled = False
    instance.update_footswitch(mock_fs)

    assert wfs.label == "", f"Expected empty label after tap tempo disabled, got: {wfs.label!r}"


def _setup_pedalboard(instance, pb):
    mock_current = Current(
        pedalboard=pb,
        presets={0: "Clean"},
        preset_index=0,
        analog_controllers={},
    )
    mock_footswitches = [_make_footswitch(i) for i in range(4)]
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
