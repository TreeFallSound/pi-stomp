"""Preset navigation requiring v3 hardware interactions (longpress, LCD encoder menu)."""

import time
from unittest.mock import patch

import pistomp.switchstate as switchstate
from tests.types import SystemFixture
from uilib.misc import get_text_size


def test_v3_preset_change_via_footswitch_longpress(v3_system: SystemFixture, snapshot, get_urls):
    """Footswitch 0 longpress fires previous_snapshot → wraps from 0 to max index."""
    handler = v3_system.handler
    hw = v3_system.hw
    mock_get = v3_system.mock_get

    hw.footswitches[0]._on_switch(switchstate.Value.LONGPRESSED, timestamp=time.monotonic())
    with patch("time.monotonic", return_value=time.monotonic() + 1.0):
        handler._tick_chords()

    assert any("snapshot/load" in u for u in get_urls(mock_get))
    snapshot()


def test_v3_preset_change_via_lcd(v3_system: SystemFixture, nav_handler, snapshot, get_urls):
    """Encoder navigates to preset widget, opens menu, selects 'Lead', fires snapshot/load."""
    handler = v3_system.handler
    mock_get = v3_system.mock_get

    snapshot("nav_A")

    nav_handler(1)
    nav_handler(1)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot("nav_B")

    nav_handler(1)
    snapshot("nav_C")

    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    assert any("snapshot/load?id=1" in u for u in get_urls(mock_get))
    snapshot("nav_D")


def test_draw_preset_never_paints_a_stale_cached_label(v3_system: SystemFixture, monkeypatch):
    """Ensure we don't ever blit the original text after it's been changed (caching issue)."""
    handler = v3_system.handler
    lcd = handler.lcd
    w_preset = lcd.w_preset
    assert w_preset is not None
    assert w_preset.text == "Clean"

    mismatches = []
    orig_draw = type(w_preset)._draw

    def spy_draw(self, ctx):
        if self is w_preset and self.cached_text_image is not None:
            expected_w = get_text_size(self.text, self.font)[0] if self.text else 0
            if self.cached_text_width != expected_w:
                mismatches.append((self.text, self.cached_text_width, expected_w))
        return orig_draw(self, ctx)

    monkeypatch.setattr(type(w_preset), "_draw", spy_draw)

    handler.current.preset_index = 1
    lcd.draw_preset(handler.current.presets[1])

    assert mismatches == [], f"painted with a cached glyph width that didn't match the current text: {mismatches}"
