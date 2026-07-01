"""Snapshot sagas for the TAP Reverberator full-screen panel.

Drives the panel via the public handler entry points
(`show_fullscreen_panel`, `universal_encoder_select`, `universal_encoder_sw`)
and captures the LCD frame at each step.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_tap_reverb_panel.py --snapshot-update
"""

from __future__ import annotations

import pistomp.switchstate as switchstate
from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.tap_reverb import TAP_REVERB_URI
from plugins.tap_reverb.panel import TapReverbPanel
from tests.types import SystemFixture

# ── mode labels (43 values from the plugin TTL) ─────────────────────────────

MODE_LABELS: list[str] = [
    "AfterBurn",
    "AfterBurn (Long)",
    "Ambience",
    "Ambience (Thick)",
    "Ambience (Thick) - HD",
    "Cathedral",
    "Cathedral - HD",
    "Drum Chamber",
    "Garage",
    "Garage (Bright)",
    "Gymnasium",
    "Gymnasium (Bright)",
    "Gymnasium (Bright) - HD",
    "Hall (Small)",
    "Hall (Medium)",
    "Hall (Large)",
    "Hall (Large) - HD",
    "Plate (Small)",
    "Plate (Medium)",
    "Plate (Large)",
    "Plate (Large) - HD",
    "Pulse Chamber",
    "Pulse Chamber (Reverse)",
    "Resonator (96 ms)",
    "Resonator (152 ms)",
    "Resonator (208 ms)",
    "Room (Small)",
    "Room (Medium)",
    "Room (Large)",
    "Room (Large) - HD",
    "Slap Chamber",
    "Slap Chamber - HD",
    "Slap Chamber (Bright)",
    "Slap Chamber (Bright) - HD",
    "Smooth Hall (Small)",
    "Smooth Hall (Medium)",
    "Smooth Hall (Large)",
    "Smooth Hall (Large) - HD",
    "Vocal Plate",
    "Vocal Plate - HD",
    "Warble Chamber",
    "Warehouse",
    "Warehouse - HD",
]

_MODE_SCALEPOINTS = [{"label": label, "value": float(i)} for i, label in enumerate(MODE_LABELS)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEnc(Controller):
    def __init__(self, id: int):
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id


def _param(
    symbol: str,
    value: float,
    minimum: float,
    maximum: float,
    default: float,
    instance_id: str = "reverb",
    enum_values: list | None = None,
) -> Parameter:
    info: dict = {
        "shortName": symbol,
        "symbol": symbol,
        "ranges": {"minimum": minimum, "maximum": maximum, "default": default},
    }
    if enum_values is not None:
        info["properties"] = ["enumeration"]
        info["scalePoints"] = enum_values
    return Parameter(info, value, None, instance_id)


def make_tap_reverb_plugin(instance_id: str = "reverb") -> Plugin:
    """Build a Plugin instance mirroring TAP Reverberator's port layout."""
    params: dict[str, Parameter] = {
        ":bypass": Parameter(
            {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1, "default": 0}},
            False,
            None,
            instance_id,
        ),
        "decay": _param("decay", 2800.0, 0.0, 10000.0, 2800.0, instance_id),
        "drylevel": _param("drylevel", -4.0, -70.0, 10.0, -4.0, instance_id),
        "wetlevel": _param("wetlevel", -12.0, -70.0, 10.0, -12.0, instance_id),
        "mode": _param("mode", 0.0, 0.0, 42.0, 0.0, instance_id, enum_values=_MODE_SCALEPOINTS),
    }
    plugin = Plugin(instance_id, params, {}, "Reverb", uri=TAP_REVERB_URI)
    plugin.has_footswitch = False
    plugin.pedalboard_snapshot = {sym: float(p.value) if p.value is not None else 0.0 for sym, p in params.items()}
    return plugin


def open_panel(v3_system: SystemFixture) -> Plugin:
    """Install a TAP Reverb plugin and open the panel for it."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    plugin = make_tap_reverb_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    handler.show_fullscreen_panel(plugin, TapReverbPanel)
    handler.poll_lcd_updates()
    return plugin


def nav(nav_handler, steps: int) -> None:
    direction = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        nav_handler(direction)


def tweak(handler, idx: int, rotations: int) -> bool:
    event = EncoderEvent(
        controller=_FakeEnc(idx),
        rotations=rotations,
        new_value=0.0,
        new_midi_value=0,
    )
    return handler.handle(event)


def short_press(handler) -> None:
    handler.universal_encoder_sw(switchstate.Value.RELEASED)


def long_press(handler) -> None:
    handler.universal_encoder_sw(switchstate.Value.LONGPRESSED)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)


# ---------------------------------------------------------------------------
# Saga 1 — initial render
# ---------------------------------------------------------------------------


def test_tap_reverb_initial_render(v3_system: SystemFixture, snapshot):
    """Panel opens with Mode selected, default values shown."""
    open_panel(v3_system)
    snapshot("opened")


# ---------------------------------------------------------------------------
# Saga 2 — nav cycles Mode → Decay → Dry → Wet → chrome
# ---------------------------------------------------------------------------


def test_tap_reverb_nav_cycles_values(v3_system: SystemFixture, nav_handler, snapshot):
    """Forward-nav through Mode, Decay, Dry, Wet; readout follows."""
    handler = v3_system.handler
    open_panel(v3_system)
    snapshot("mode")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("decay")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("dry")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("wet")


# ---------------------------------------------------------------------------
# Saga 3 — Tweak1 edits the focused knob
# ---------------------------------------------------------------------------


def test_tap_reverb_tweak1_edits_focused(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Wet, Tweak1 increases wetlevel by 8 * 0.8 = 6.4 dB."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Nav to Wet (3 steps: Mode → Decay → Dry → Wet)
    nav(nav_handler, 3)
    handler.poll_lcd_updates()
    snapshot("wet_focused")

    # Tweak1: +8 detents → +6.4 dB → -12 + 6.4 = -5.6 dB
    for _ in range(8):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("wet_up")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "wetlevel")
    assert len(sent) > 0
    assert abs(sent[-1] - (-5.6)) < 0.01


# ---------------------------------------------------------------------------
# Saga 4 — Tweak2 cycles Mode regardless of focus
# ---------------------------------------------------------------------------


def test_tap_reverb_tweak2_cycles_mode(v3_system: SystemFixture, snapshot):
    """Tweak2 cycles mode from 0 (AfterBurn) to 5 (Cathedral)."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    for _ in range(5):
        tweak(handler, 2, 1)
    handler.poll_lcd_updates()
    snapshot("mode_cathedral")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "mode")
    assert len(sent) > 0
    assert sent[-1] == 5.0


# ---------------------------------------------------------------------------
# Saga 5 — Tweak3 edits Decay regardless of focus
# ---------------------------------------------------------------------------


def test_tap_reverb_tweak3_edits_decay(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Mode (focus away from Decay), then Tweak3 edits Decay."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Mode is already focused at open — no nav needed
    handler.poll_lcd_updates()

    # Tweak3: +5 detents → +500 ms → 2800 + 500 = 3300 ms
    for _ in range(5):
        tweak(handler, 3, 1)
    handler.poll_lcd_updates()
    snapshot("decay_up_from_mode_focus")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "decay")
    assert len(sent) > 0
    assert abs(sent[-1] - 3300.0) < 0.01


# ---------------------------------------------------------------------------
# Saga 6 — Tweak1 edits Mode when Mode is focused
# ---------------------------------------------------------------------------


def test_tap_reverb_tweak1_edits_mode_when_focused(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Mode, Tweak1 cycles the mode."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Mode is already focused at open
    handler.poll_lcd_updates()
    snapshot("mode_focused")

    for _ in range(3):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("mode_3")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "mode")
    assert len(sent) > 0
    assert sent[-1] == 3.0


# ---------------------------------------------------------------------------
# Saga 7 — CLICK resets value to lv2:default
# ---------------------------------------------------------------------------


def test_tap_reverb_click_resets_to_default(v3_system: SystemFixture, nav_handler, snapshot):
    """Edit Decay, click it → resets to lv2:default (2800 ms)."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Focus Decay (1 step from Mode) and edit
    nav(nav_handler, 1)
    for _ in range(10):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("decay_edited")

    # Click → reset to default
    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("decay_reset")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "decay")
    assert len(sent) > 0
    assert sent[-1] == 2800.0


# ---------------------------------------------------------------------------
# Saga 8 — CLICK on Mode opens the parameter dialog (list of all modes)
# ---------------------------------------------------------------------------


def test_tap_reverb_click_mode_opens_dialog(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Mode, click → opens a selection menu of all 43 modes."""
    handler = v3_system.handler
    open_panel(v3_system)

    # Tweak2 to advance mode to 5 (Cathedral)
    for _ in range(5):
        tweak(handler, 2, 1)

    # Mode is already focused at open
    handler.poll_lcd_updates()
    snapshot("mode_focused_at_5")

    # Click → opens parameter dialog (selection menu of 43 modes)
    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("mode_dialog_open")


# ---------------------------------------------------------------------------
# Saga 9 — chrome Reset restores pedalboard snapshot
# ---------------------------------------------------------------------------


def test_tap_reverb_reset_restores_snapshot(v3_system: SystemFixture, nav_handler, snapshot):
    """Edit multiple params, Nav to Reset, click → all restored."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)
    snapshot("opened")

    # Edit decay via Tweak3 (works from any focus)
    for _ in range(10):
        tweak(handler, 3, 1)

    # Edit wet via Tweak1 — nav to Wet (3 steps: Mode → Decay → Dry → Wet)
    nav(nav_handler, 3)
    for _ in range(5):
        tweak(handler, 1, 1)

    # Edit mode via Tweak2
    for _ in range(7):
        tweak(handler, 2, 1)

    handler.poll_lcd_updates()
    snapshot("after_edits")

    # Nav to Reset: from Wet (index 3), forward: Back (4), Bypass (5), Reset (6)
    nav(nav_handler, 3)
    handler.poll_lcd_updates()
    snapshot("reset_focused")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("after_reset")

    # Verify params restored to snapshot
    decay_sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "decay")
    wet_sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "wetlevel")
    mode_sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "mode")
    assert decay_sent[-1] == 2800.0
    assert wet_sent[-1] == -12.0
    assert mode_sent[-1] == 0.0


# ---------------------------------------------------------------------------
# Saga 10 — bypass toggle
# ---------------------------------------------------------------------------


def test_tap_reverb_bypass_toggle(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Bypass, click to bypass, click again to re-enable."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Nav: Mode(0) → Decay(1) → Dry(2) → Wet(3) → Back(4) → Bypass(5)
    nav(nav_handler, 5)
    handler.poll_lcd_updates()
    snapshot("bypass_focused")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("bypassed")

    assert plugin.is_bypassed()

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("re_enabled")

    assert not plugin.is_bypassed()


# ---------------------------------------------------------------------------
# Saga 11 — Tweak3 always edits Decay, even when chrome is focused
# ---------------------------------------------------------------------------


def test_tap_reverb_tweak3_edits_decay_on_chrome(v3_system: SystemFixture, nav_handler):
    """Tweak3 is a dedicated shortcut: edits Decay even when chrome is focused.
    Tweak1/2 are silently consumed by the panel (no-op, no MIDI leak)."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Nav to Back (4 steps: Mode → Decay → Dry → Wet → Back)
    nav(nav_handler, 4)

    def _lcd_consumes(enc_id: int) -> bool:
        event = EncoderEvent(
            controller=_FakeEnc(enc_id),
            rotations=1,
            new_value=0.0,
            new_midi_value=0,
        )
        return handler.lcd.handle(event)

    # Tweak3 is always consumed (dedicated Decay shortcut)
    assert _lcd_consumes(3) is True
    # Tweak1/2 are silently consumed by the panel on chrome (no-op)
    assert _lcd_consumes(1) is True
    assert _lcd_consumes(2) is True

    # Flush the param queue so the WS send is visible
    handler.poll_lcd_updates()

    # Tweak3 actually sent a decay param even from chrome focus
    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "decay")
    assert len(sent) > 0
