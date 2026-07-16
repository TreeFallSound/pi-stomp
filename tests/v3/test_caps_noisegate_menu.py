"""Snapshot sagas for the CAPS Noisegate custom-layout menu widget.

Long-press the Noisegate plugin tile to open the arc-ring window with the
4 arc-ring slots (Open, Close, Attack, Mains). Tweak1 adjusts the selected
slot; navigation cycles slots via Nav.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_caps_noisegate_menu.py --snapshot-update
"""

from __future__ import annotations

from unittest.mock import MagicMock

from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextLayer,
    ContextRef,
    ControlClass,
    ControlRef,
    EventKind,
    ParamEffect,
    ShadowState,
)
from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.footswitch import Footswitch
from pistomp.input.event import EncoderEvent
from plugins.customization import lookup
from uilib.misc import InputEvent
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from common.parameter import BYPASS_SYMBOL, PortInfo, Symbol


CAPS_NOISEGATE_URI = "http://moddevices.com/plugins/caps/Noisegate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEnc(Controller):
    def __init__(self, id: int):
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id


def _param(
    symbol: Symbol, value: float, minimum: float, maximum: float, instance_id: str = "Gate", unit: str | None = None
) -> Parameter:
    info: PortInfo = {"shortName": symbol, "symbol": symbol, "ranges": {"minimum": minimum, "maximum": maximum}}
    if unit is not None:
        info["units"] = {"symbol": unit}
    return Parameter(info, value, None, instance_id)


def make_noisegate_plugin(instance_id: str = "Gate") -> Plugin:
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, instance_id),
        Symbol("open"): _param(Symbol("open"), -45.0, -60.0, 0.0, instance_id, unit="dB"),
        Symbol("attack"): _param(Symbol("attack"), 0.0, 0.0, 5.0, instance_id, unit="ms"),
        Symbol("close"): _param(Symbol("close"), -67.5, -80.0, 0.0, instance_id, unit="dB"),
        Symbol("mains"): _param(Symbol("mains"), 50.0, 0.0, 100.0, instance_id, unit="Hz"),
    }
    plugin = Plugin(instance_id, params, {}, "Dynamics", uri=CAPS_NOISEGATE_URI, customization=lookup(CAPS_NOISEGATE_URI))
    plugin.has_footswitch = True
    plugin.pedalboard_snapshot = {
        sym: float(p.value) if p.value is not None else 0.0
        for sym, p in params.items()
    }
    return plugin


def bind_footswitch(handler, plugin: Plugin, symbol: Symbol, fs_id: int) -> None:
    """Bind *symbol* to footswitch *fs_id* in the effective table, which is
    where the badge letters are resolved from."""
    control_id = f"0:{10 + fs_id}"
    fs = Footswitch(
        id=fs_id, led_pin=None, pixel=None, midi_CC=10 + fs_id, midi_channel=0, refresh_callback=MagicMock()
    )
    handler.hardware.controllers[control_id] = fs
    row = BindingDecl(
        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=control_id),
        event_kind=EventKind.PRESS,
        effects=(ParamEffect(plugin=plugin, symbol=symbol),),
        context=ContextRef(kind=ContextKind.PEDALBOARD),
        shadow_state=ShadowState.ACTIVE,
    )
    key = (ControlClass.FOOTSWITCH, EventKind.PRESS)
    for layer in handler.effective_table.layers:
        if layer.ref.kind is ContextKind.PEDALBOARD:
            layer.rows.setdefault(key, []).append(row)
            return
    handler.effective_table.layers.append(
        ContextLayer(ref=ContextRef(kind=ContextKind.PEDALBOARD), rows={key: [row]})
    )


def open_menu(v3_system: SystemFixture) -> Plugin:
    """Install a Noisegate plugin and open its custom layout menu. Returns the plugin."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    plugin = make_noisegate_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # Long-press the plugin tile to open the custom layout menu
    lcd = handler.lcd
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()
    return plugin


def tweak(handler, idx: int, rotations: int) -> bool:
    event = EncoderEvent(controller=_FakeEnc(idx), rotations=rotations, new_value=0.0, new_midi_value=0)
    return handler.handle(event)


def long_press(handler) -> None:
    nav_click(handler, long=True)
    nav_click(handler)


# ---------------------------------------------------------------------------
# Sagas
# ---------------------------------------------------------------------------


def test_noisegate_menu_initial_render(v3_system: SystemFixture, snapshot):
    """Menu opens with 4 arc rings: Open, Close, Attack, Mains."""
    open_menu(v3_system)
    snapshot()


def test_noisegate_menu_tweak_open(v3_system: SystemFixture, nav_handler, snapshot):
    """Tweak1 raises the Open threshold toward 0 dB."""
    handler = v3_system.handler
    open_menu(v3_system)
    for _ in range(8):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot()


def test_noisegate_menu_nav_to_mains(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav cycles to the Mains slot (4th)."""
    handler = v3_system.handler
    open_menu(v3_system)
    for _ in range(3):
        nav_handler(1)
        handler.poll_lcd_updates()
    snapshot()


def test_parameter_window_scrolls_when_content_overflows(v3_system: SystemFixture, snapshot):
    """A plugin with many params: 4 pinned rings + 8 list rows. The list
    overflows the window; the last rows and the Back/Bypass/Reset row must be
    reachable by scrolling, and a bound param must badge whether it renders as
    a pinned ring or a list row."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, "many"),
    }
    for i in range(12):
        sym = Symbol(f"param_{i:02d}")
        params[sym] = _param(sym, 0.5, 0.0, 1.0, "many", unit="dB")
    plugin = Plugin("many", params, {}, "Dynamics")
    plugin.has_footswitch = True
    plugin.pedalboard_snapshot = {sym: 0.5 for sym in params}

    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    # param_00 pins to a ring, param_05 lands in the list, :bypass drives the
    # footer button — all three must surface their badge.
    bind_footswitch(handler, plugin, Symbol("param_00"), fs_id=0)
    bind_footswitch(handler, plugin, Symbol("param_05"), fs_id=1)
    bind_footswitch(handler, plugin, BYPASS_SYMBOL, fs_id=2)

    lcd = handler.lcd
    assert lcd.pstack.current is not None
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()
    snapshot("initial")

    # Nav down past the 4 rings into the list, then keep going to the last row
    for _ in range(4 + 7):  # 4 rings + 7 nav steps to reach last of 8 list rows
        lcd.pstack.current.input_step(1, 1, 1.0)
        handler.poll_lcd_updates()
    snapshot("scrolled_to_last")

    # One more step lands on Back: the button row scrolls into view as the last
    # body element, it is not fixed chrome.
    lcd.pstack.current.input_step(1, 1, 1.0)
    handler.poll_lcd_updates()
    snapshot("scrolled_to_footer")


def test_list_row_tweak1_edits_value(v3_system: SystemFixture, nav_handler, snapshot):
    """Selecting a list row and rotating Tweak1 edits the param: the readout,
    bar fill, and focused-row highlight all track the new value live."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, "many"),
    }
    for i in range(6):
        sym = Symbol(f"param_{i:02d}")
        params[sym] = _param(sym, 0.5, 0.0, 1.0, "many", unit="dB")
    plugin = Plugin("many", params, {}, "Dynamics")
    plugin.pedalboard_snapshot = {sym: 0.5 for sym in params}

    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    lcd = handler.lcd
    assert lcd.pstack.current is not None
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()

    # 4 rings pinned; step past them onto the first list row (param_04).
    for _ in range(4):
        lcd.pstack.current.input_step(1, 1, 1.0)
    handler.poll_lcd_updates()

    for _ in range(20):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()

    assert plugin.parameters[Symbol("param_04")].value > 0.5
    snapshot("row_edited")


def test_list_rows_discrete_types(v3_system: SystemFixture, nav_handler, snapshot):
    """Enum and toggle list rows show a picked label (mode / On-Off), no bar;
    continuous rows keep the bar. Tweak1 cycles the selected enum's label."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, "mix"),
        Symbol("gain"): _param(Symbol("gain"), 0.5, 0.0, 1.0, "mix", unit="dB"),
        Symbol("mode"): Parameter(
            {
                "shortName": "mode",
                "symbol": "mode",
                "ranges": {"minimum": 0, "maximum": 2},
                "properties": ["enumeration"],
                "scalePoints": [
                    {"label": "Bypass", "value": 0.0},
                    {"label": "Warm", "value": 1.0},
                    {"label": "Bright", "value": 2.0},
                ],
            },
            0.0,
            None,
            "mix",
        ),
        Symbol("boost"): Parameter(
            {"shortName": "boost", "symbol": "boost", "ranges": {"minimum": 0, "maximum": 1}, "properties": ["toggled"]},
            0.0,
            None,
            "mix",
        ),
    }
    plugin = Plugin("mix", params, {}, "Utility")
    plugin.pedalboard_snapshot = {sym: float(p.value or 0.0) for sym, p in params.items()}

    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    lcd = handler.lcd
    assert lcd.pstack.current is not None
    lcd.main_panel.sel_widget(lcd.w_plugins[0])
    lcd.main_panel.input_event(InputEvent.LONG_CLICK)
    handler.poll_lcd_updates()
    snapshot("initial")

    # gain pins to a ring; list rows sort as boost, mode. Step past the ring and
    # boost onto the mode enum, then cycle it.
    for _ in range(2):
        lcd.pstack.current.input_step(1, 1, 1.0)
    handler.poll_lcd_updates()
    tweak(handler, 1, 1)
    handler.poll_lcd_updates()

    assert plugin.parameters[Symbol("mode")].value == 1.0
    snapshot("mode_warm")