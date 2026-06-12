"""Per-pedalboard hardware config overlay — reinit correctness tests.

Green tests document existing behaviour.
Red tests (encoder_switch_map, encoder longpress, footswitch disable) are
written first and are expected to fail until the corresponding fixes land.
"""
import pytest

import common.token as Token
from tests.types import SystemFixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(footswitches=None, encoders=None):
    """Build a minimal hardware config dict for use with hw.reinit()."""
    hw: dict = {}
    if footswitches is not None:
        hw[Token.FOOTSWITCHES] = footswitches
    if encoders is not None:
        hw[Token.ENCODERS] = encoders
    return {Token.HARDWARE: hw}


# ---------------------------------------------------------------------------
# Footswitch longpress — existing behaviour
# ---------------------------------------------------------------------------

def test_footswitch_longpress_set_from_default(v3_system: SystemFixture):
    """FS0 longpress comes from default_config after fixture setup."""
    hw = v3_system.hw
    assert "previous_snapshot" in hw.footswitches[0].longpress_groups


def test_footswitch_longpress_override(v3_system: SystemFixture):
    """Pedalboard config can change FS0 longpress to a different action."""
    hw = v3_system.hw
    handler = v3_system.handler

    hw.reinit(_cfg(footswitches=[{"id": 0, "longpress": "toggle_bypass"}]))

    assert "toggle_bypass" in hw.footswitches[0].longpress_groups


def test_footswitch_longpress_reset_to_default(v3_system: SystemFixture):
    """After an override, reinit(None) restores the default longpress."""
    hw = v3_system.hw

    hw.reinit(_cfg(footswitches=[{"id": 0, "longpress": "toggle_bypass"}]))
    hw.reinit(None)

    assert "previous_snapshot" in hw.footswitches[0].longpress_groups
    assert "toggle_bypass" not in hw.footswitches[0].longpress_groups


def test_footswitch_longpress_suppress_with_none(v3_system: SystemFixture):
    """Explicit null longpress in pedalboard config clears the default."""
    hw = v3_system.hw

    hw.reinit(_cfg(footswitches=[{"id": 0, "longpress": None}]))

    assert len(hw.footswitches[0].longpress_groups) == 0


# ---------------------------------------------------------------------------
# Footswitch color — existing behaviour
# ---------------------------------------------------------------------------

def test_footswitch_color_override(v3_system: SystemFixture):
    """Pedalboard config can set FS0 lcd_color."""
    hw = v3_system.hw

    hw.reinit(_cfg(footswitches=[{"id": 0, "color": "Red"}]))

    assert hw.footswitches[0].lcd_color == "Red"


def test_footswitch_color_unaffected_without_key(v3_system: SystemFixture):
    """FS0 lcd_color is not changed when the override has no color key."""
    hw = v3_system.hw

    hw.reinit(_cfg(footswitches=[{"id": 0, "color": "Red"}]))
    hw.reinit(_cfg(footswitches=[{"id": 0, "longpress": "toggle_bypass"}]))  # no color key

    # Color persists because reinit doesn't clear it when the key is absent.
    assert hw.footswitches[0].lcd_color == "Red"


# ---------------------------------------------------------------------------
# Footswitch disable — NEW: expected to fail until fix lands
# ---------------------------------------------------------------------------

def test_footswitch_disable_override(v3_system: SystemFixture):
    """Pedalboard config can mark FS0 as disabled."""
    hw = v3_system.hw

    hw.reinit(_cfg(footswitches=[{"id": 0, "disable": True}]))

    assert hw.footswitches[0].disabled is True


def test_footswitch_disable_reset_to_enabled(v3_system: SystemFixture):
    """Disabled FS resets to enabled when a different pedalboard is loaded."""
    hw = v3_system.hw

    hw.reinit(_cfg(footswitches=[{"id": 0, "disable": True}]))
    hw.reinit(None)  # new pedalboard with no overrides

    assert hw.footswitches[0].disabled is False


def test_footswitch_disabled_does_not_respond(v3_system: SystemFixture):
    """A disabled footswitch ignores poll() events."""
    import pistomp.switchstate as switchstate

    hw = v3_system.hw
    hw.reinit(_cfg(footswitches=[{"id": 0, "disable": True}]))

    fs0 = hw.footswitches[0]
    fires = []
    original_on_switch = fs0._on_switch
    fs0._on_switch = lambda state, timestamp=0.0: fires.append(state)

    # Simulate a poll (bypass the GPIO layer)
    fs0.poll()  # should no-op because disabled

    # Nothing fired
    assert fires == []

    # Restore
    fs0._on_switch = original_on_switch


# ---------------------------------------------------------------------------
# Encoder longpress — stored as string name; resolved by handler at dispatch.
# ---------------------------------------------------------------------------

def _enc(hw, enc_id):
    return next(e for e in hw.encoders if getattr(e, "id", None) == enc_id)


def test_encoder_longpress_set_from_default(v3_system: SystemFixture):
    """Enc1 longpress name matches default_config (previous_snapshot) after boot."""
    hw = v3_system.hw

    assert _enc(hw, 1).longpress == "previous_snapshot"


def test_encoder_longpress_override(v3_system: SystemFixture):
    """Pedalboard config can change enc1 longpress to toggle_bypass."""
    hw = v3_system.hw

    hw.reinit(_cfg(encoders=[{"id": 1, "longpress": "toggle_bypass"}]))

    assert _enc(hw, 1).longpress == "toggle_bypass"


def test_encoder_longpress_reset_to_default(v3_system: SystemFixture):
    """After an encoder longpress override, reinit(None) restores the default."""
    hw = v3_system.hw

    hw.reinit(_cfg(encoders=[{"id": 1, "longpress": "toggle_bypass"}]))
    hw.reinit(None)

    assert _enc(hw, 1).longpress == "previous_snapshot"


def test_encoder_longpress_suppress_with_none(v3_system: SystemFixture):
    """Explicit null in pedalboard config clears the default encoder longpress."""
    hw = v3_system.hw

    hw.reinit(_cfg(encoders=[{"id": 1, "longpress": None}]))

    assert _enc(hw, 1).longpress is None


def test_encoder_unmentioned_keeps_default(v3_system: SystemFixture):
    """Overriding enc2 does not disturb enc1's default longpress."""
    hw = v3_system.hw

    hw.reinit(_cfg(encoders=[{"id": 2, "longpress": "toggle_bypass"}]))

    assert _enc(hw, 1).longpress == "previous_snapshot"
