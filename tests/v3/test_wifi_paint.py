"""Snapshot the WiFi menu / SSID-entry flow to catch paint-context regressions.

The refactor/paint-context branch reworked widget `_draw(ctx, frame)` signatures.
The wifi dialog exercises a prompt-prefixed TextWidget plus a nested TextEditor
panel — areas the refactor touched — so snapshots at each level surface any
clip/frame coordinate mistakes.
"""

from tests.types import SystemFixture
from uilib.misc import InputEvent


def test_v3_wifi_ssid_entry(v3_system: SystemFixture, snapshot):
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    assert handler.lcd
    assert handler.wifi_manager

    handler.wifi_manager.get_ssid.return_value = "MyNet"
    handler.wifi_manager.get_psk.return_value = "secret"
    handler.wifi_status = {"hotspot_active": False, "wifi_connected": True}

    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    snapshot("main")

    handler.lcd.draw_wifi_menu(None, None)
    snapshot("wifi_menu")

    handler.lcd.draw_wifi_dialog(None)
    snapshot("wifi_dialog")

    # Click the SSID field to open the TextEditor (letter selector).
    assert handler.lcd.w_wifi_ssid is not None
    handler.lcd.w_wifi_ssid.input_event(InputEvent.CLICK)
    handler.poll_lcd_updates()
    snapshot("ssid_editor")
