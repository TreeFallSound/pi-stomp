"""Snapshot sagas for the caps-Eq10 graphic EQ full-screen panel.

These tests drive the panel via the public handler entry points
(``show_fullscreen_panel``, ``universal_encoder_select``, ``universal_encoder_sw``)
and capture the LCD frame at each step.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_graphic_eq_panel.py --snapshot-update
"""

import pistomp.switchstate as switchstate
from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.capseq10 import CAPSEQ10_URI
from plugins.capseq10.band_spec import BAND_SPECS
from plugins.capseq10.panel import CapsEq10Panel
from tests.types import SystemFixture


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEnc(Controller):
    def __init__(self, id: int):
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id


def _param(
    symbol: str, value: float, minimum: float = 0.0, maximum: float = 1.0, instance_id: str = "eq10"
) -> Parameter:
    info = {"shortName": symbol, "symbol": symbol, "ranges": {"minimum": minimum, "maximum": maximum}}
    return Parameter(info, value, None, instance_id)


def make_capseq10_plugin(instance_id: str = "eq10") -> Plugin:
    """Build a Plugin instance mirroring caps-Eq10's port layout.

    All bands start at 0 dB (enabled), gain range -48..+24 dB.
    """
    params: dict[str, Parameter] = {}

    bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
    params[":bypass"] = Parameter(bypass_info, False, None, instance_id)
    params["enable"] = _param("enable", 1.0, instance_id=instance_id)

    for b in BAND_SPECS:
        params[b.gain_sym] = _param(b.gain_sym, 0.0, b.gain_min, b.gain_max, instance_id=instance_id)

    plugin = Plugin(instance_id, params, {}, "EQ", uri=CAPSEQ10_URI)
    plugin.has_footswitch = False
    plugin.pedalboard_snapshot = {
        sym: float(p.value) if p.value is not None else 0.0
        for sym, p in params.items()
    }
    return plugin


def open_eq(v3_system: SystemFixture) -> Plugin:
    """Install a caps-Eq10 plugin and open the graphic EQ panel for it."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    plugin = make_capseq10_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    handler.show_fullscreen_panel(plugin, CapsEq10Panel)
    handler.poll_lcd_updates()
    return plugin


def nav(nav_handler, steps: int) -> None:
    direction = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        nav_handler(direction)


def tweak(handler, idx: int, rotations: int) -> bool:
    event = EncoderEvent(controller=_FakeEnc(idx), rotations=rotations, new_value=0.0, new_midi_value=0)
    return handler.handle(event)


def short_press(handler) -> None:
    handler.universal_encoder_sw(switchstate.Value.RELEASED)


def long_press(handler) -> None:
    handler.universal_encoder_sw(switchstate.Value.LONGPRESSED)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)


# ---------------------------------------------------------------------------
# Saga 1 — initial render
# ---------------------------------------------------------------------------


def test_initial_render(v3_system: SystemFixture, snapshot):
    """Panel opens with first band selected, all bars at 0 dB."""
    open_eq(v3_system)
    snapshot("opened")


# ---------------------------------------------------------------------------
# Saga 2 — nav cycles bands and readout follows
# ---------------------------------------------------------------------------


def test_nav_cycles_bands(v3_system: SystemFixture, nav_handler, snapshot):
    """Forward-nav through every band; the halo + readout must follow."""
    handler = v3_system.handler
    open_eq(v3_system)
    snapshot(BAND_SPECS[0].name)

    for band in BAND_SPECS[1:]:
        nav(nav_handler, 1)
        handler.poll_lcd_updates()
        snapshot(band.name)


# ---------------------------------------------------------------------------
# Saga 3 — tweak gain on a band, bar moves live
# ---------------------------------------------------------------------------


def test_tweak_gain(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to a band, boost gain, then cut — bar height and readout update."""
    handler = v3_system.handler
    plugin = open_eq(v3_system)

    # Nav to band at index 3 (250 Hz)
    nav(nav_handler, 3)
    handler.poll_lcd_updates()
    snapshot("band_selected")

    # Boost +12 dB (24 ticks at +0.5 dB each)
    for _ in range(24):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("boosted")

    # Cut -18 dB (36 ticks at -0.5 dB each) — past the boost to verify negative
    for _ in range(36):
        tweak(handler, 1, -1)
    handler.poll_lcd_updates()
    snapshot("cut")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "band250hz")
    assert len(sent) > 0
    assert sent[-1] < 0.0


# ---------------------------------------------------------------------------
# Saga 4 — bypass button: nav → highlight → press → dim bars
# ---------------------------------------------------------------------------


def test_bypass_button_saga(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Bypass chrome, short-press to bypass, again to re-enable."""
    handler = v3_system.handler
    plugin = open_eq(v3_system)

    # Boost a band so bars are visible for the dim check
    nav(nav_handler, 2)
    for _ in range(12):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("active_pre_bypass")

    # Nav past remaining bands to Bypass (7 bands + Back + Bypass = 9 steps)
    nav(nav_handler, 9)
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
# Saga 5 — Reset restores pedalboard-saved values
# ---------------------------------------------------------------------------


def test_reset_restores_pedalboard(v3_system: SystemFixture, nav_handler, snapshot):
    """Tweak a band, then Reset; final state should match opened baseline."""
    handler = v3_system.handler
    open_eq(v3_system)
    snapshot("opened")

    nav(nav_handler, 4)
    for _ in range(16):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("after_tweak")

    # Nav to Reset: after band 4, remaining bands + Back + Bypass + Reset
    nav(nav_handler, 8)
    handler.poll_lcd_updates()
    snapshot("reset_focused")

    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("after_reset")


# ---------------------------------------------------------------------------
# Saga 6 — long-press resets a single band to pedalboard snapshot
# ---------------------------------------------------------------------------


def test_long_press_resets_band(v3_system: SystemFixture, nav_handler, snapshot):
    """Long-press on a band resets its gain to the pedalboard snapshot."""
    handler = v3_system.handler
    plugin = open_eq(v3_system)

    # Boost band 0
    for _ in range(20):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("boosted")

    # Long-press to reset
    long_press(handler)
    handler.poll_lcd_updates()
    snapshot("after_long_reset")

    sent = v3_system.ws_bridge.sent_values_for(plugin.instance_id, BAND_SPECS[0].gain_sym)
    assert sent[-1] == 0.0


# ---------------------------------------------------------------------------
# Saga 7 — Tweak2/3 are consumed but no-op on graphic EQ
# ---------------------------------------------------------------------------


def test_tweak23_consumed_noop(v3_system: SystemFixture, nav_handler):
    """Tweak2 and Tweak3 are consumed by the panel (no handler fall-through)."""
    handler = v3_system.handler
    open_eq(v3_system)

    def _lcd_consumes(enc_id: int) -> bool:
        event = EncoderEvent(controller=_FakeEnc(enc_id), rotations=1, new_value=0.0, new_midi_value=0)
        return handler.lcd.handle(event)

    assert _lcd_consumes(1) is True
    assert _lcd_consumes(2) is True
    assert _lcd_consumes(3) is True

    # On chrome: Tweak3 falls through, Tweak1/2 consumed
    nav(nav_handler, 10)
    assert _lcd_consumes(3) is False
    assert _lcd_consumes(1) is True
    assert _lcd_consumes(2) is True
