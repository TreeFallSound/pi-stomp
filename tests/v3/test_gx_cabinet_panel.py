"""Snapshot sagas for the GxCabinet full-screen panel.

Drives the panel via the public handler entry points
(`show_fullscreen_panel`, `universal_encoder_select`, `universal_encoder_sw`)
and captures the LCD frame at each step.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_gx_cabinet_panel.py --snapshot-update
"""

from __future__ import annotations

import pistomp.switchstate as switchstate
from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.gx_cabinet import GX_CABINET_URI
from plugins.gx_cabinet.panel import GxCabinetPanel
from tests.types import SystemFixture

# ── cab model labels (19 values from the plugin TTL) ────────────────────────

MODEL_LABELS: list[str] = [
    "4x12",
    "2x12",
    "1x12",
    "4x10",
    "2x10",
    "HighGain",
    "Twin",
    "Bassman",
    "Marshall",
    "AC30",
    "Princeton",
    "A2",
    "1x15",
    "Mesa",
    "Briliant",
    "Vitalize",
    "Charisma",
    "1x8",
    "Off",
]

_MODEL_SCALEPOINTS = [{"label": label, "value": float(i)} for i, label in enumerate(MODEL_LABELS)]


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
    instance_id: str = "cabinet",
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


def make_gx_cabinet_plugin(instance_id: str = "cabinet") -> Plugin:
    """Build a Plugin instance mirroring GxCabinet's port layout."""
    params: dict[str, Parameter] = {
        ":bypass": Parameter(
            {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1, "default": 0}},
            False,
            None,
            instance_id,
        ),
        "CLevel": _param("CLevel", 1.0, 0.5, 5.0, 1.0, instance_id),
        "CBass": _param("CBass", 0.0, -10.0, 10.0, 0.0, instance_id),
        "CTreble": _param("CTreble", 0.0, -10.0, 10.0, 0.0, instance_id),
        "c_model": _param("c_model", 0.0, 0.0, 18.0, 0.0, instance_id, enum_values=_MODEL_SCALEPOINTS),
    }
    plugin = Plugin(instance_id, params, {}, "GxCabinet", uri=GX_CABINET_URI)
    plugin.has_footswitch = False
    plugin.pedalboard_snapshot = {sym: float(p.value) if p.value is not None else 0.0 for sym, p in params.items()}
    return plugin


def open_panel(v3_system: SystemFixture) -> Plugin:
    """Install a GxCabinet plugin and open the panel for it."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    plugin = make_gx_cabinet_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.current.pedalboard.connections = []
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    handler.show_fullscreen_panel(plugin, GxCabinetPanel)
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


# ---------------------------------------------------------------------------
# Saga 1 — initial render
# ---------------------------------------------------------------------------


def test_gx_cabinet_initial_render(v3_system: SystemFixture, snapshot):
    """Panel opens with the cab-model selector focused, default values shown."""
    open_panel(v3_system)
    snapshot("opened")


# ---------------------------------------------------------------------------
# Saga 2 — nav cycles Model → Level → Bass → Treble
# ---------------------------------------------------------------------------


def test_gx_cabinet_nav_cycles_values(v3_system: SystemFixture, nav_handler, snapshot):
    """Forward-nav through Model, Level, Bass, Treble; readout follows."""
    handler = v3_system.handler
    open_panel(v3_system)
    snapshot("model")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("level")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("bass")

    nav(nav_handler, 1)
    handler.poll_lcd_updates()
    snapshot("treble")


# ---------------------------------------------------------------------------
# Saga 3 — Tweak1 edits the focused knob
# ---------------------------------------------------------------------------


def test_gx_cabinet_tweak1_edits_focused(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Treble, Tweak1 increases treble by 8 * 0.4 = 3.2."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Nav to Treble (3 steps: Model → Level → Bass → Treble)
    nav(nav_handler, 3)
    handler.poll_lcd_updates()
    snapshot("treble_focused")

    for _ in range(8):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("treble_up")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "CTreble")
    assert len(sent) > 0
    assert abs(sent[-1] - 3.2) < 0.01


# ---------------------------------------------------------------------------
# Saga 4 — Tweak2 cycles Model regardless of focus
# ---------------------------------------------------------------------------


def test_gx_cabinet_tweak2_cycles_model(v3_system: SystemFixture, snapshot):
    """Tweak2 cycles the cab model from 0 (4x12) to 5 (HighGain)."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    for _ in range(5):
        tweak(handler, 2, 1)
    handler.poll_lcd_updates()
    snapshot("model_highgain")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "c_model")
    assert len(sent) > 0
    assert sent[-1] == 5.0


# ---------------------------------------------------------------------------
# Saga 5 — Tweak3 edits Level regardless of focus
# ---------------------------------------------------------------------------


def test_gx_cabinet_tweak3_edits_level(v3_system: SystemFixture, snapshot):
    """Model is focused at open; Tweak3 still edits Level."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Tweak3: +5 detents * 0.05 => 1.0 + 0.25 = 1.25
    for _ in range(5):
        tweak(handler, 3, 1)
    handler.poll_lcd_updates()
    snapshot("level_up_from_model_focus")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "CLevel")
    assert len(sent) > 0
    assert abs(sent[-1] - 1.25) < 0.01


# ---------------------------------------------------------------------------
# Saga 6 — CLICK resets value to lv2:default
# ---------------------------------------------------------------------------


def test_gx_cabinet_click_resets_to_default(v3_system: SystemFixture, nav_handler, snapshot):
    """Edit Bass, click it -> resets to lv2:default (0.0)."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Focus Bass (2 steps: Model -> Level -> Bass) and edit
    nav(nav_handler, 2)
    for _ in range(10):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("bass_edited")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("bass_reset")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "CBass")
    assert len(sent) > 0
    assert sent[-1] == 0.0


# ---------------------------------------------------------------------------
# Saga 7 — chrome Reset restores pedalboard snapshot
# ---------------------------------------------------------------------------


def test_gx_cabinet_reset_restores_snapshot(v3_system: SystemFixture, nav_handler, snapshot):
    """Edit multiple params, Nav to Reset, click -> all restored."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)
    snapshot("opened")

    # Edit level via Tweak3 (works from any focus)
    for _ in range(10):
        tweak(handler, 3, 1)

    # Edit treble via Tweak1 -- nav to Treble (3 steps: Model -> Level -> Bass -> Treble)
    nav(nav_handler, 3)
    for _ in range(5):
        tweak(handler, 1, 1)

    # Edit model via Tweak2
    for _ in range(7):
        tweak(handler, 2, 1)

    handler.poll_lcd_updates()
    snapshot("after_edits")

    # Nav to Reset: from Treble (index 3), forward: Back (4), Bypass (5), Reset (6)
    nav(nav_handler, 3)
    handler.poll_lcd_updates()
    snapshot("reset_focused")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("after_reset")

    level_sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "CLevel")
    treble_sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "CTreble")
    model_sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "c_model")
    assert level_sent[-1] == 1.0
    assert treble_sent[-1] == 0.0
    assert model_sent[-1] == 0.0


# ---------------------------------------------------------------------------
# Saga 8 — bypass toggle
# ---------------------------------------------------------------------------


def test_gx_cabinet_bypass_toggle(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Bypass, click to bypass, click again to re-enable."""
    handler = v3_system.handler
    plugin = open_panel(v3_system)

    # Nav: Model(0) -> Level(1) -> Bass(2) -> Treble(3) -> Back(4) -> Bypass(5)
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
