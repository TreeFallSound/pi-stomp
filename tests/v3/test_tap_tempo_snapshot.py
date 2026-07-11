"""Tap tempo LCD snapshot — v3 footswitch strip showing BPM in tap tempo mode."""

from tests.types import SystemFixture


def test_v3_tap_tempo_lcd_snapshot(v3_system: SystemFixture, make_plugin, snapshot):
    handler = v3_system.handler
    hw = v3_system.hw

    plugin = make_plugin("fuzz", category="Distortion", bypassed=False, has_footswitch=True)
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    hw.toggle_tap_tempo_enable(120)
    handler.lcd.draw_footswitches()
    snapshot()
