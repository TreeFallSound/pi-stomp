"""Startup smoke test for the v1 (Mod + Pistomp) stack."""


def test_v1_startup_snapshot(v1_system, snapshot):
    lcd = v1_system.lcd
    assert len(lcd.frames) > 0
    snapshot()
