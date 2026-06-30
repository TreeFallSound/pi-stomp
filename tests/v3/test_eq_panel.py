"""Snapshot sagas for the x42-eq (fil4) full-screen panel.

These tests drive the panel via the public handler entry points
(`show_fullscreen_panel`, `universal_encoder_select`, `universal_encoder_sw`)
and capture the LCD frame at each step.

Each test is a multi-step "saga" rather than a single assertion. The goal
is broad ground-truth coverage of what the panel renders today so the
upcoming surgical-redraw optimization can be validated against these
baselines.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_eq_panel.py --snapshot-update
"""

import pistomp.switchstate as switchstate
from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.fil4 import FIL4_MONO_URI
from plugins.fil4.band_spec import BAND_SPECS, PLUGIN_ENABLE_SYM
from plugins.fil4.panel import Fil4Panel
from tests.types import SystemFixture


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEnc(Controller):
    def __init__(self, id: int):
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id
        # Leave `type` as the class default (None) so the panel treats this as a
        # generic tweak encoder, not a nav/volume encoder.


def _param(
    symbol: str, value: float, minimum: float = 0.0, maximum: float = 1.0, instance_id: str = "fil4"
) -> Parameter:
    info = {"shortName": symbol, "symbol": symbol, "ranges": {"minimum": minimum, "maximum": maximum}}
    return Parameter(info, value, None, instance_id)


def make_fil4_plugin(instance_id: str = "fil4") -> Plugin:
    """Build a Plugin instance mirroring fil4's port layout.

    Provides every symbol the EQ panel reads, with neutral defaults
    (all bands disabled, geometric-mean freq, Q=1.0, gain=0 dB).
    """
    params: dict[str, Parameter] = {}

    # Plugin-wide
    bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
    params[":bypass"] = Parameter(bypass_info, False, None, instance_id)
    params[PLUGIN_ENABLE_SYM] = _param(PLUGIN_ENABLE_SYM, 1.0, instance_id=instance_id)
    params["gain"] = _param("gain", 0.0, -18.0, 18.0, instance_id=instance_id)

    # Per-band
    for b in BAND_SPECS:
        if b.enable_sym is not None:
            params[b.enable_sym] = _param(b.enable_sym, 0.0, instance_id=instance_id)
        f0 = (b.freq_min * b.freq_max) ** 0.5
        params[b.freq_sym] = _param(b.freq_sym, f0, b.freq_min, b.freq_max, instance_id=instance_id)
        if b.q_sym is not None:
            params[b.q_sym] = _param(b.q_sym, 1.0, b.q_min, b.q_max, instance_id=instance_id)
        if b.gain_sym is not None:
            params[b.gain_sym] = _param(b.gain_sym, 0.0, -18.0, 18.0, instance_id=instance_id)

    plugin = Plugin(instance_id, params, {}, "Filter", uri=FIL4_MONO_URI)
    plugin.has_footswitch = False
    # Simulate parse-time snapshot for Reset
    plugin.pedalboard_snapshot = {
        sym: float(p.value) if p.value is not None else 0.0
        for sym, p in params.items()
    }
    return plugin


def open_eq(v3_system: SystemFixture) -> Plugin:
    """Install a fil4 plugin and open the EQ panel for it. Returns the plugin."""
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    plugin = make_fil4_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    handler.show_fullscreen_panel(plugin, Fil4Panel)
    handler.poll_lcd_updates()
    return plugin


def nav(nav_handler, steps: int) -> None:
    """Move Nav by `steps` (positive = forward)."""
    direction = 1 if steps > 0 else -1
    for _ in range(abs(steps)):
        nav_handler(direction)


def tweak(handler, idx: int, rotations: int) -> bool:
    """Drive a tweak encoder rotation through the handler dispatch.

    The LCD gets first crack; if the EQ panel is topmost it consumes the
    event via PluginPanel.on_encoder_rotation.
    """
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


def test_eq_initial_render(v3_system: SystemFixture, snapshot):
    """Panel opens with HP selected, neutral curve, no chrome highlighted."""
    open_eq(v3_system)
    snapshot("opened")


# ---------------------------------------------------------------------------
# Saga 2 — nav cycles bands and produces correct readout per band
# ---------------------------------------------------------------------------


def test_eq_nav_cycles_bands(v3_system: SystemFixture, nav_handler, snapshot):
    """Forward-nav through every band; the halo + readout must follow."""
    handler = v3_system.handler
    open_eq(v3_system)
    snapshot(BAND_SPECS[0].name)

    for band in BAND_SPECS[1:]:
        nav(nav_handler, 1)
        handler.poll_lcd_updates()
        snapshot(band.name)


# ---------------------------------------------------------------------------
# Saga 3 — tweak gain/freq/Q on a peaking band, curve updates live
# ---------------------------------------------------------------------------


def test_eq_tweak_gain_freq_q(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to B1 (peaking), enable it, then move each parameter."""
    handler = v3_system.handler
    plugin = open_eq(v3_system)

    # HP, LS, B1 — three forward nav steps
    nav(nav_handler, 2)
    handler.poll_lcd_updates()
    snapshot("b1_disabled")

    # enable B1
    short_press(handler)
    handler.poll_lcd_updates()
    snapshot("b1_enabled")

    # Tweak1 → +6 dB gain (12 single-rotation ticks at +0.5 dB each)
    for _ in range(12):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("gain_up")

    # Tweak2 → sweep freq upward (12 semitones = one octave)
    for _ in range(12):
        tweak(handler, 2, 1)
    handler.poll_lcd_updates()
    snapshot("freq_up")

    # Tweak3 → widen Q downward (8 ticks × -0.05)
    for _ in range(8):
        tweak(handler, 3, -1)
    handler.poll_lcd_updates()
    snapshot("q_down")

    # Sanity: each tweak pushed at least one param_set; final value sane
    sent_gain = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "gain1")
    sent_freq = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "freq1")
    sent_q = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "q1")
    assert len(sent_gain) > 0 and sent_gain[-1] > 0
    assert len(sent_freq) > 0 and sent_freq[-1] > 0
    assert len(sent_q) > 0


# ---------------------------------------------------------------------------
# Saga 4 — short-press toggles a band's enable; readout shows "disabled"
# ---------------------------------------------------------------------------


def test_eq_enable_disable_band(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to B2, enable it, tweak gain so the curve is visible, then disable."""
    handler = v3_system.handler
    plugin = open_eq(v3_system)

    nav(nav_handler, 3)  # HP, LS, B1, B2
    short_press(handler)  # enable B2
    for _ in range(16):
        tweak(handler, 1, 1)  # +8 dB
    handler.poll_lcd_updates()
    snapshot("b2_boosted")

    short_press(handler)  # disable — readout should now show "disabled"
    handler.poll_lcd_updates()
    snapshot("b2_disabled")

    assert v3_system.ws_bridge.sent_values_for(plugin.instance_id, "sec2")[-1] == 0.0


# ---------------------------------------------------------------------------
# Saga 5 — HP/LP have no gain; Tweak1 on HP is a no-op
# ---------------------------------------------------------------------------


def test_eq_hp_no_gain_axis(v3_system: SystemFixture, snapshot):
    """HP is selected at open; Tweak1 sends no param. Tweak2/3 still work."""
    handler = v3_system.handler
    plugin = open_eq(v3_system)
    short_press(handler)  # enable HP

    handler.poll_lcd_updates()
    snapshot("hp_enabled")

    # Tweak1 → no gain symbol for HP, should send nothing and not crash
    for _ in range(4):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("hp_after_gain_noop")  # should match previous

    # Tweak2 sweeps HP freq
    for _ in range(10):
        tweak(handler, 2, 1)
    handler.poll_lcd_updates()
    snapshot("hp_freq_up")

    assert v3_system.ws_bridge.sent_values_for(plugin.instance_id, "HPfreq")
    # HP has no gain symbol — nothing for HPgain
    assert v3_system.ws_bridge.sent_values_for(plugin.instance_id, "HPgain") == []


# ---------------------------------------------------------------------------
# Saga 6 — bypass button: nav → highlight → press → red bg + dim curve
# ---------------------------------------------------------------------------


def test_eq_bypass_button_saga(v3_system: SystemFixture, nav_handler, snapshot):
    """Nav to Bypass chrome, short-press to bypass, again to re-enable."""
    handler = v3_system.handler
    plugin = open_eq(v3_system)

    # Enable + boost a band so the curve is visible for the bypass-dim check
    nav(nav_handler, 2)  # HP, LS, B1
    short_press(handler)
    for _ in range(12):
        tweak(handler, 1, 1)
    handler.poll_lcd_updates()
    snapshot("active_pre_bypass")

    # Nav past the remaining bands to Bypass (chrome order: Back, Bypass, Reset)
    # After B1: B2, B3, B4, HS, LP, Back, Bypass — 7 steps
    nav(nav_handler, 7)
    handler.poll_lcd_updates()
    snapshot("bypass_focused")

    short_press(handler)  # toggle bypass
    handler.poll_lcd_updates()
    snapshot("bypassed")

    assert plugin.is_bypassed()

    short_press(handler)  # un-bypass
    handler.poll_lcd_updates()
    snapshot("re_enabled")

    assert not plugin.is_bypassed()


# ---------------------------------------------------------------------------
# Saga 7 — Reset restores pedalboard-saved values after multiple tweaks
# ---------------------------------------------------------------------------


def test_eq_reset_restores_pedalboard(v3_system: SystemFixture, nav_handler, snapshot):
    """Tweak B1 + B3, then Reset; final state should match opened baseline."""
    handler = v3_system.handler
    open_eq(v3_system)
    snapshot("opened")  # baseline

    nav(nav_handler, 2)  # B1
    short_press(handler)
    for _ in range(10):
        tweak(handler, 1, 1)

    nav(nav_handler, 2)  # B3
    short_press(handler)
    for _ in range(8):
        tweak(handler, 1, -1)
    handler.poll_lcd_updates()
    snapshot("after_tweaks")

    # Nav to Reset: after B3 we're at sel index for B3.  Forward nav cycles
    # B4, HS, LP, Back, Bypass, Reset → 6 steps.
    nav(nav_handler, 6)
    handler.poll_lcd_updates()
    snapshot("reset_focused")

    short_press(handler)
    handler.poll_lcd_updates()
    # After reset we're still focused on the Reset button, not a band, so
    # this can't reuse the "opened" label (different selection).
    snapshot("after_reset")


# ---------------------------------------------------------------------------
# Saga 8 — multi-band cumulative curve (multiple peaks at once)
# ---------------------------------------------------------------------------


def test_eq_multi_band_cumulative_curve(v3_system: SystemFixture, nav_handler, snapshot):
    """Enable + boost B1/B3, cut B2 — verify the composed magnitude curve."""
    handler = v3_system.handler
    open_eq(v3_system)

    # B1: +6 dB
    nav(nav_handler, 2)
    short_press(handler)
    for _ in range(12):
        tweak(handler, 1, 1)

    # B2: -6 dB
    nav(nav_handler, 1)
    short_press(handler)
    for _ in range(12):
        tweak(handler, 1, -1)

    # B3: +9 dB
    nav(nav_handler, 1)
    short_press(handler)
    for _ in range(18):
        tweak(handler, 1, 1)

    handler.poll_lcd_updates()
    snapshot("three_band_curve")


# ---------------------------------------------------------------------------
# Saga 9 — chrome selection lets the volume encoder fall through
# ---------------------------------------------------------------------------


def test_eq_volume_passthrough_on_chrome(v3_system: SystemFixture, nav_handler):
    """When Back/Bypass/Reset is focused, the panel does NOT consume Tweak3
    (volume encoder falls through to handler), but Tweak1/2 are silently
    absorbed so they don't leak MIDI from the chrome context."""
    handler = v3_system.handler
    open_eq(v3_system)

    # Helper: ask the LCD whether it would consume a tweak encoder event.
    def _lcd_consumes(enc_id: int) -> bool:
        event = EncoderEvent(controller=_FakeEnc(enc_id), rotations=1, new_value=0.0, new_midi_value=0)
        return handler.lcd.handle(event)

    # Tweak3 on a band → consumed by the panel (controls Q)
    assert _lcd_consumes(3) is True

    # Nav past all 8 bands to Back (HP→LS→B1→B2→B3→B4→HS→LP→Back = 8 steps)
    nav(nav_handler, 8)

    # On chrome: Tweak3 falls through (panel does NOT consume it)
    assert _lcd_consumes(3) is False
    # Tweak1/2 are silently consumed by the panel (no-op, no handler dispatch)
    assert _lcd_consumes(1) is True
    assert _lcd_consumes(2) is True
