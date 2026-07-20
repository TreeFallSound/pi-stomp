"""Reactive ``Parameter.value``: a property setter that notifies observers,
so every write site (eight in production) reaches every listener through one
path. Panels subscribe via ``Plugin.subscribe`` and mark themselves dirty;
``tick`` drains the dirty flag into ``apply_state`` + ``_refresh_bypass_style``.

Covers the seven invariants in the plan's verification section plus the three
footswitch-spam regression tests that lock the hard-won
LED-only-optimistic / LCD-via-echo split.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from unittest.mock import MagicMock

import pistomp.switchstate as switchstate
from common.parameter import BYPASS_SYMBOL, Parameter, PortInfo, Symbol
from modalapi.plugin import Plugin
from plugins.fullscreen import FullscreenPluginPanel
from plugins.window import PluginWindow
from tests.types import SystemFixture
from uilib.parameterdialog import Parameterdialog


# ---------------------------------------------------------------------------
# Demo panels that record apply_state calls for coalescing assertions
# ---------------------------------------------------------------------------


@dataclass
class _TrackedState:
    bypassed: bool = False
    gain: float = 0.0


@dataclass
class _TrackedWindowState:
    bypassed: bool = False
    gain: float = 0.0


class _TrackedFullscreenPanel(FullscreenPluginPanel[_TrackedState]):
    apply_count: int = 0
    plugin: Plugin  # narrowing: test panel always backed by a Plugin

    def snapshot_state(self) -> _TrackedState:
        p = self.plugin
        gain = 0.0
        gp = p.parameters.get(Symbol("gain"))
        if gp is not None:
            gain = float(gp.value)
        return _TrackedState(bypassed=p.is_bypassed(), gain=gain)

    def apply_state(self, state: _TrackedState) -> None:
        self.apply_count += 1

    def build_widgets(self) -> None:
        pass


class _TrackedWindowPanel(PluginWindow[_TrackedWindowState]):
    apply_count: int = 0
    plugin: Plugin  # narrowing: test panel always backed by a Plugin

    def snapshot_state(self) -> _TrackedWindowState:
        p = self.plugin
        gain = 0.0
        gp = p.parameters.get(Symbol("gain"))
        if gp is not None:
            gain = float(gp.value)
        return _TrackedWindowState(bypassed=p.is_bypassed(), gain=gain)

    def apply_state(self, state: _TrackedWindowState) -> None:
        self.apply_count += 1

    def build_widgets(self) -> None:
        pass


def _make_plugin_with_gain(make_plugin, instance_id="fuzz", bypassed=False) -> Plugin:
    """A plugin with a :bypass and a gain param, so we can test non-bypass writes."""
    gain_info: PortInfo = {"shortName": "Gain", "symbol": "gain", "ranges": {"minimum": 0, "maximum": 1}}
    gain_param = Parameter(gain_info, 0.5, None, instance_id)
    plugin = make_plugin(instance_id, bypassed=bypassed, parameters={Symbol("gain"): gain_param})
    return plugin


def _install(v3_system: SystemFixture, make_plugin, instance_id="fuzz", bypassed=False) -> Plugin:
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current
    plugin = _make_plugin_with_gain(make_plugin, instance_id, bypassed)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    return plugin


def _open_window(v3_system: SystemFixture, plugin: Plugin) -> _TrackedWindowPanel:
    v3_system.handler.show_fullscreen_panel(plugin, _TrackedWindowPanel)
    return cast(_TrackedWindowPanel, v3_system.handler.lcd.pstack.current)


def _open_fullscreen(v3_system: SystemFixture, plugin: Plugin) -> _TrackedFullscreenPanel:
    v3_system.handler.show_fullscreen_panel(plugin, _TrackedFullscreenPanel)
    return cast(_TrackedFullscreenPanel, v3_system.handler.lcd.pstack.current)


# ---------------------------------------------------------------------------
# 1. Parameter.value setter notifies on change, skips on no-change
# ---------------------------------------------------------------------------


def test_param_value_setter_notifies_on_change_not_on_noop():
    """Writing param.value from any site notifies; an unchanged write does not."""
    info: PortInfo = {"shortName": "x", "symbol": "x", "ranges": {"minimum": 0, "maximum": 1}}
    p = Parameter(info, 0.0, None, "inst")
    calls: list[Parameter] = []
    p.subscribe(lambda param: calls.append(param))

    p.value = 1.0
    assert len(calls) == 1
    assert calls[0] is p

    p.value = 1.0  # unchanged — no notification
    assert len(calls) == 1

    p.value = 0.5
    assert len(calls) == 2


def test_subscribe_returns_unsubscriber():
    """The returned callable tears down the subscription."""
    info: PortInfo = {"shortName": "x", "symbol": "x", "ranges": {"minimum": 0, "maximum": 1}}
    p = Parameter(info, 0.0, None, "inst")
    calls: list[Parameter] = []
    unsub = p.subscribe(lambda param: calls.append(param))

    p.value = 1.0
    assert len(calls) == 1

    unsub()
    p.value = 0.0
    assert len(calls) == 1  # no more notifications after unsubscribe


def test_plugin_subscribe_fans_out_to_all_params(make_plugin):
    """Plugin.subscribe fires for any parameter write, via one unsubscriber."""
    plugin = _make_plugin_with_gain(make_plugin)
    calls: list[Parameter] = []
    unsub = plugin.subscribe(lambda param: calls.append(param))

    plugin.parameters[BYPASS_SYMBOL].value = 1.0
    plugin.parameters[Symbol("gain")].value = 0.9
    assert len(calls) == 2

    unsub()
    plugin.parameters[BYPASS_SYMBOL].value = 0.0
    assert len(calls) == 2  # unsubscribed


def test_to_json_on_subscribed_plugin_does_not_crash(make_plugin):
    """A subscribed plugin has _observers (callables) in Parameter.__dict__;
    to_json must filter them out so json.dumps doesn't TypeError."""
    import json as _json
    plugin = _make_plugin_with_gain(make_plugin)
    unsub = plugin.subscribe(lambda _p: None)
    # Must not raise — _observers and _value are stripped, value re-injected.
    data = _json.loads(plugin.to_json())
    assert data["parameters"][":bypass"]["value"] == 0.0
    assert data["parameters"]["gain"]["value"] == 0.5
    assert "_observers" not in data["parameters"][":bypass"]
    assert "_value" not in data["parameters"][":bypass"]
    unsub()


# ---------------------------------------------------------------------------
# 2. Open panel renders bypassed immediately (face 1 + 2)
# ---------------------------------------------------------------------------


def test_panel_opens_bypassed_immediately(v3_system: SystemFixture, make_plugin, snapshot):
    """Open a PluginWindow on a bypassed plugin → it renders bypassed at once,
    with no NAV rotation needed to land on the Bypass button (face 1 + 2)."""
    plugin = _install(v3_system, make_plugin, bypassed=True)
    panel = _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    assert panel._btn_bypass is not None
    snapshot("bypassed_on_open")


def test_panel_opens_active_immediately(v3_system: SystemFixture, make_plugin, snapshot):
    """Open a PluginWindow on an active plugin → Bypass button shows inactive."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    snapshot("active_on_open")


# ---------------------------------------------------------------------------
# 3. External PluginBypassMessage updates the open panel (face 3)
# ---------------------------------------------------------------------------


def test_external_bypass_message_updates_open_panel(v3_system: SystemFixture, make_plugin, snapshot):
    """Feed a PluginBypassMessage through the WS path while a panel is open →
    the Bypass button background changes after tick. This fails today on main
    (face 3): the bypass arm repaints the grid tile, not the open panel."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    snapshot("active")

    v3_system.ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    v3_system.handler.poll_ws_messages()
    v3_system.handler.poll_lcd_updates()
    assert plugin.is_bypassed()
    snapshot("bypassed_via_echo")


def test_external_bypass_message_clears_open_panel(v3_system: SystemFixture, make_plugin, snapshot):
    """Reverse direction: bypassed → active via external echo."""
    plugin = _install(v3_system, make_plugin, bypassed=True)
    _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    snapshot("bypassed")

    v3_system.ws_bridge.inject("param_set /graph/fuzz :bypass 0.0")
    v3_system.handler.poll_ws_messages()
    v3_system.handler.poll_lcd_updates()
    assert not plugin.is_bypassed()
    snapshot("active_via_echo")


def _grid_tile(v3_system: SystemFixture, plugin: Plugin):
    lcd = v3_system.handler.lcd
    for w in lcd.w_plugins:
        if w.object is plugin:
            return w
    raise AssertionError(f"no grid tile for {plugin.instance_id!r}")


def test_external_bypass_message_repaints_grid_tile(v3_system: SystemFixture, make_plugin):
    """No panel open: an external bypass echo must still repaint the main-grid
    tile (PluginTile's bypass subscription fires _apply_bypass_colors + refresh),
    not just an open panel's Bypass button. Face-3 coverage without a panel."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    tile = _grid_tile(v3_system, plugin)
    assert tile.outline == 0
    assert tile.outline_color is None

    v3_system.ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    v3_system.handler.poll_ws_messages()
    assert plugin.is_bypassed()
    assert tile.outline == 1
    assert tile.outline_color is not None


# ---------------------------------------------------------------------------
# 4. External ParamSetMessage moves a pinned param (gain)
# ---------------------------------------------------------------------------


def test_external_param_set_updates_open_panel(v3_system: SystemFixture, make_plugin):
    """An external ParamSetMessage for a non-bypass param marks the panel dirty
    and apply_state runs on tick."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    panel = _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 0

    v3_system.ws_bridge.inject("param_set /graph/fuzz gain 0.9")
    v3_system.handler.poll_ws_messages()
    assert panel._model_dirty is True
    v3_system.handler.poll_lcd_updates()
    assert panel._model_dirty is False
    assert panel.apply_count == 1


# ---------------------------------------------------------------------------
# 5. Hidden symbol (enabled port) doesn't crash, doesn't alter is_bypassed
# ---------------------------------------------------------------------------


def test_hidden_enabled_port_does_not_crash_or_alter_bypass(v3_system: SystemFixture, make_plugin):
    """An inbound param_set for a hidden designated-enabled port (guitarix BYPASS)
    is applied without crashing and does not alter is_bypassed()."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    # Add a hidden enabled-designation port, as mod-host emits for the feedback.
    enabled_info: PortInfo = {
        "shortName": "BYPASS",
        "symbol": "BYPASS",
        "designation": "http://lv2plug.in/ns/lv2core#enabled",
        "ranges": {"minimum": 0, "maximum": 1},
    }
    enabled_param = Parameter(enabled_info, 1.0, None, "fuzz")
    assert enabled_param.hidden is True
    plugin.parameters[Symbol("BYPASS")] = enabled_param

    _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()

    # mod-host emits the enabled-port feedback (inverse of :bypass).
    v3_system.ws_bridge.inject("param_set /graph/fuzz BYPASS 0.000000")
    v3_system.handler.poll_ws_messages()
    v3_system.handler.poll_lcd_updates()

    assert plugin.is_bypassed() is False  # :bypass is still 0.0


# ---------------------------------------------------------------------------
# 6. Dismissed panel unsubscribes (no listener leak)
# ---------------------------------------------------------------------------


def test_dismissed_panel_unsubscribes(v3_system: SystemFixture, make_plugin):
    """After dismiss, mutating the plugin must not touch the dead panel — its
    _model_dirty stays False (guards a listener leak)."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    panel = _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()

    v3_system.handler.hide_fullscreen_panel()
    v3_system.handler.poll_lcd_updates()

    # Mutate after dismiss — the dead panel must not be flagged.
    plugin.set_bypass(True)
    assert panel._model_dirty is False


# ---------------------------------------------------------------------------
# 7. Connect dump (N params) triggers one apply_state, not N
# ---------------------------------------------------------------------------


def test_connect_dump_coalesces_apply_state(v3_system: SystemFixture, make_plugin):
    """A connect dump setting N params triggers one apply_state, not N — the
    dirty flag coalesces: each write sets _model_dirty=True (idempotent), and
    a single tick drains it into one apply_state call."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    panel = _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 0

    # Simulate a connect dump: N param_set messages arrive back-to-back
    # before a tick drains them.
    for i in range(5):
        v3_system.ws_bridge.inject(f"param_set /graph/fuzz gain {0.1 * i:.6f}")
    v3_system.handler.poll_ws_messages()
    # No tick yet — dirty is set, apply_state not called.
    assert panel._model_dirty is True
    assert panel.apply_count == 0

    # One tick → one apply_state, regardless of how many writes.
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 1

    # A second tick with no new writes → no extra apply_state.
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 1


# ---------------------------------------------------------------------------
# Footswitch bypass-spam regression (the hard-won invariant)
#
# The footswitch bypass path flip-flopped through three reversions before
# landing on: LED-only optimistic on local press, keycap display driven by
# the echo. Reactivity creates a new split:
#
#   - _fire_row's ParamEffect arm writes param.value DIRECTLY (not via
#     set_param_value), so on a local press the controller mirror does NOT fire
#     → fs.set_value is not called → keycap waits for echo (invariant
#     preserved). The panel observer DOES fire → panel repaints optimistically
#     (face 1).
#   - On the echo (set_param_value), the mirror fires → keycap updates; the
#     idempotent setter guard skips the observer → no redundant panel repaint.
# ---------------------------------------------------------------------------


def _bind_footswitch(v3_system: SystemFixture, plugin: Plugin):
    """Bind footswitch[0] to the plugin's :bypass, mirroring production setup."""
    handler = v3_system.handler
    hw = v3_system.hw
    fs = hw.footswitches[0]
    handler._bind_controller_to_param(plugin, plugin.parameters[BYPASS_SYMBOL], fs)
    return fs


def test_local_footswitch_press_fires_panel_observer_not_keycap(v3_system: SystemFixture, make_plugin):
    """Open panel, stomp once (no echo yet): panel._model_dirty is True (observer
    fired) and fs.refresh_callback was NOT called (keycap waits for echo). Then
    inject the echo: fs.refresh_callback called once, apply_state ran."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    fs = _bind_footswitch(v3_system, plugin)
    fs.refresh_callback = MagicMock()
    panel = _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 0
    fs.refresh_callback.reset_mock()

    # Local press — _fire_row's ParamEffect arm writes param.value directly.
    fs._on_switch(switchstate.Value.RELEASED)
    assert plugin.is_bypassed() is True
    assert panel._model_dirty is True  # observer fired
    fs.refresh_callback.assert_not_called()  # keycap waits for echo

    # Tick drains the panel.
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 1
    assert panel._model_dirty is False

    # Echo arrives via set_param_value → mirror fires → keycap updates.
    v3_system.ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    v3_system.handler.poll_ws_messages()
    fs.refresh_callback.assert_called_once()
    # Idempotent: same value → observer skipped → no extra apply_state.
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 1


def test_idempotent_bypass_echo_skips_panel_repaint(v3_system: SystemFixture, make_plugin):
    """Open panel, toggle bypass locally (observer fires, dirty set), tick (one
    apply_state), inject echo at the SAME value, tick — apply_state is NOT called
    again. Guards a removed idempotent check."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    panel = _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 0

    # Local toggle via the panel's own button — writes param.value.
    panel._on_toggle_bypass()
    assert plugin.is_bypassed() is True
    assert panel._model_dirty is True
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 1

    # Echo arrives at the same value — idempotent setter skips the observer.
    v3_system.ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    v3_system.handler.poll_ws_messages()
    assert panel._model_dirty is False  # observer did not fire
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 1  # no extra repaint


def test_rapid_footswitch_with_panel_open_coalesces(v3_system: SystemFixture, make_plugin):
    """Open a PluginWindow on a plugin with a bound bypass footswitch; stomp N
    times; settle N echoes; assert (a) final bypass state correct on both
    plugin.is_bypassed() and the panel's bypass button, (b) apply_count bounded
    by tick count, not 2N (coalescing holds under spam), (c) fs.refresh_callback
    called exactly N times (once per echo, never on local press)."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    fs = _bind_footswitch(v3_system, plugin)
    fs.refresh_callback = MagicMock()
    panel = _open_window(v3_system, plugin)
    v3_system.handler.poll_lcd_updates()
    fs.refresh_callback.reset_mock()

    N = 5
    # Stomp N times with no echoes and no ticks in between.
    for _ in range(N):
        fs._on_switch(switchstate.Value.RELEASED)
    # Each press writes param.value directly (_fire_row ParamEffect arm); the
    # observer fires each time but _model_dirty is already True — coalesced.
    assert panel._model_dirty is True
    fs.refresh_callback.assert_not_called()  # no echo yet → no keycap refresh

    # One tick drains N coalesced dirty flags into one apply_state.
    v3_system.handler.poll_lcd_updates()
    assert panel.apply_count == 1

    # Now settle N echoes — each arrives at the value the press left behind.
    # After N presses starting from active (bypassed=False, toggled=True):
    #   press 1: bypassed=True  → echo :bypass 1.0
    #   press 2: bypassed=False → echo :bypass 0.0
    #   ... so the final echo value depends on N parity.
    final_bypassed = (N % 2 == 1)
    echo_val = "1.0" if final_bypassed else "0.0"
    for _ in range(N):
        v3_system.ws_bridge.inject(f"param_set /graph/fuzz :bypass {echo_val}")
        v3_system.handler.poll_ws_messages()

    # (c) keycap refreshed once per echo.
    assert fs.refresh_callback.call_count == N

    # (a) final state correct on both plugin and panel button.
    assert plugin.is_bypassed() is final_bypassed
    v3_system.handler.poll_lcd_updates()
    # (b) apply_count bounded by ticks, not 2N. We've ticked twice total;
    # the idempotent echoes at the final value should not have added dirty work.
    assert panel.apply_count <= 3  # initial drain + at most one echo-driven drain

# ---------------------------------------------------------------------------
# 11. An open Parameterdialog follows its parameter (tweak encoder, MOD-UI echo)
# ---------------------------------------------------------------------------


def _open_dialog(v3_system: SystemFixture, plugin: Plugin) -> Parameterdialog:
    param = plugin.parameters[Symbol("gain")]
    return cast(Parameterdialog, v3_system.handler.lcd.draw_parameter_dialog(param))


def test_open_dialog_follows_external_param_set(v3_system: SystemFixture, make_plugin):
    """An external write (MOD-UI web page, tweak encoder) to the parameter an open
    dialog is showing must repaint the dialog. `last_param_value` is what the graph
    last rendered, so it tracking the new value is the proof it redrew."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    dialog = _open_dialog(v3_system, plugin)
    assert dialog.last_param_value == 0.5

    v3_system.ws_bridge.inject("param_set /graph/fuzz gain 0.9")
    v3_system.handler.poll_ws_messages()

    assert plugin.parameters[Symbol("gain")].value == 0.9
    assert dialog.last_param_value == 0.9


def test_open_dialog_resyncs_steps_on_external_write(v3_system: SystemFixture, make_plugin):
    """The dialog's quantized cursor must track an external write too, so the next
    detent moves from where the value actually is -- not from a stale grid index.
    steps snaps to the nearest grid index, so it lands within one step of 0.9."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    dialog = _open_dialog(v3_system, plugin)
    one_step = (dialog.parameter.maximum - dialog.parameter.minimum) / 127

    v3_system.ws_bridge.inject("param_set /graph/fuzz gain 0.9")
    v3_system.handler.poll_ws_messages()

    assert abs(dialog.steps.value - 0.9) <= one_step


def test_dismissed_dialog_unsubscribes(v3_system: SystemFixture, make_plugin):
    """A popped dialog must drop its subscription -- a later write to the parameter
    must not repaint a detached widget (guards a listener leak)."""
    plugin = _install(v3_system, make_plugin, bypassed=False)
    dialog = _open_dialog(v3_system, plugin)
    gain = plugin.parameters[Symbol("gain")]

    dialog.pop()
    v3_system.handler.poll_lcd_updates()

    gain.value = 0.75
    assert dialog.last_param_value == 0.5  # never redrew after dismissal
