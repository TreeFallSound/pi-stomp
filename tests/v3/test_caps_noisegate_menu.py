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
    event = EncoderEvent(controller=_FakeEnc(idx), rotations=rotations)
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


def _enum_param(symbol: str, minimum: float, maximum: float, points: list[tuple[str, float]], value: float = 0.0) -> Parameter:
    return Parameter(
        {
            "shortName": symbol,
            "symbol": symbol,
            "ranges": {"minimum": minimum, "maximum": maximum},
            "properties": ["enumeration", "integer"],
            "scalePoints": [{"label": lbl, "value": val} for lbl, val in points],
        },
        value,
        None,
        "mix",
    )


def test_discrete_types_pin_as_rings(v3_system: SystemFixture, nav_handler, snapshot):
    """Discrete params pin as rings showing their picked label: a contiguous
    enum (mode) and a toggle (boost, green On/Off ring). Rotating cycles them."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, "mix"),
        Symbol("gain"): _param(Symbol("gain"), 0.5, 0.0, 1.0, "mix", unit="dB"),
        Symbol("mode"): _enum_param("mode", 0, 2, [("Bypass", 0.0), ("Warm", 1.0), ("Bright", 2.0)]),
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

    # Rings in LV2 port order: gain, mode, boost. Step onto the mode ring and
    # rotate it to "Warm", then back to the boost ring and flip it On.
    lcd.pstack.current.input_step(1, 1, 1.0)
    handler.poll_lcd_updates()
    tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    assert plugin.parameters[Symbol("mode")].value == 1.0
    snapshot("mode_warm")

    lcd.pstack.current.input_step(1, 1, 1.0)
    handler.poll_lcd_updates()
    tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    assert plugin.parameters[Symbol("boost")].value == 1.0
    snapshot("boost_on")


def test_discrete_list_rows_on_overflow(v3_system: SystemFixture, nav_handler, snapshot):
    """Discrete params only pin if they fit the 4-ring budget; overflow falls to
    list rows that still show the picked label (enum scale-point, toggle On/Off),
    no bar."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    params: dict[Symbol, Parameter] = {
        BYPASS_SYMBOL: Parameter({"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, False, None, "mix"),
        Symbol("a1"): _param(Symbol("a1"), 0.5, 0.0, 1.0, "mix", unit="dB"),
        Symbol("a2"): _param(Symbol("a2"), 0.5, 0.0, 1.0, "mix", unit="dB"),
        Symbol("a3"): _param(Symbol("a3"), 0.5, 0.0, 1.0, "mix", unit="dB"),
        Symbol("a4"): _param(Symbol("a4"), 0.5, 0.0, 1.0, "mix", unit="dB"),
        Symbol("mode"): _enum_param("mode", 0, 2, [("Bypass", 0.0), ("Warm", 1.0), ("Bright", 2.0)]),
        Symbol("tog"): Parameter(
            {"shortName": "tog", "symbol": "tog", "ranges": {"minimum": 0, "maximum": 1}, "properties": ["toggled"]},
            1.0,
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

def test_tweak_bound_to_pedalboard_param_not_corrupted_by_open_menu(v3_system: SystemFixture):
    """The original bug, end to end: a plugin parameter menu (ParameterWindow) is
    open and badged to tweak1, and tweak1 is *also* bound to a separate
    pedalboard param B. Turning tweak1 edits the menu's selected slot and must
    NOT write B — nor move B's w_controls bar (the visible phantom-bar symptom).

    Drives the real enc1.refresh(1): refresh() is where the old shadow-accumulator
    eagerly wrote enc1.parameter before dispatch. A hand-built event can't catch it."""
    hw = v3_system.hw

    plugin = open_menu(v3_system)

    # tweak1 (the real hardware encoder id=1) bound to a separate pedalboard param B.
    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1 and e.midi_CC is not None)
    bound_param = hw.create_external_parameter("virtual", enc1.midi_channel, enc1.midi_CC)
    enc1.bind_to_parameter(bound_param)

    slot = plugin.parameters[Symbol("open")]  # the initially-selected menu slot
    bound_before = bound_param.value
    slot_before = slot.value
    bar_before = enc1.bar_midi_value()

    enc1.refresh(1)

    # The menu's selected slot moved (the menu consumed the tweak) ...
    assert slot.value != slot_before
    # ... but the pedalboard-bound param B and its bar are untouched.
    assert bound_param.value == bound_before
    assert enc1.bar_midi_value() == bar_before


def test_unbound_tweak_not_corrupted_by_open_menu(v3_system: SystemFixture):
    """The user's exact repro: tweak1 is bound to NOTHING. Its unbound "None"
    value sits at 0. Open a plugin parameter menu (badged to tweak1), select a
    slot, and turn tweak1 right to raise it. Closing the menu, tweak1's own
    "None" value must still be 0 — the menu borrowed the turn; the fallback CC
    must not creep up. refresh() must not advance the fallback before dispatch."""
    hw = v3_system.hw

    plugin = open_menu(v3_system)

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1 and e.midi_CC is not None)
    assert enc1.parameter is None  # unbound
    fallback_before = v3_system.handler.encoder_fallback(enc1)

    slot = plugin.parameters[Symbol("open")]
    slot_before = slot.value

    for _ in range(8):
        enc1.refresh(1)

    # The menu's selected slot moved (the menu consumed the tweaks) ...
    assert slot.value != slot_before
    # ... but the unbound tweak's own "None" fallback CC never crept.
    assert v3_system.handler.encoder_fallback(enc1) == fallback_before


def test_unbound_fallback_owned_by_handler(v3_system: SystemFixture):
    """The unbound MIDI-learn fallback CC belongs to the handler (the emitter),
    not the encoder — an encoder is a pure delta source. With no panel to borrow
    the turn, refresh() falls through to the handler's unbound arm, which advances
    the fallback it owns and emits from it."""
    hw = v3_system.hw
    handler = v3_system.handler

    enc1 = next(e for e in hw.encoders if getattr(e, "id", None) == 1 and e.midi_CC is not None)
    assert enc1.parameter is None
    start = handler.encoder_fallback(enc1)

    for _ in range(3):
        enc1.refresh(1)

    assert handler.encoder_fallback(enc1) > start
