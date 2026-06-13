"""FootswitchWidget snapshot coverage — 8 configurations across 2 frames.

Each frame mimics the v3 footswitch strip (4 slots) so a single snapshot
exercises four widget configurations at once.
"""
from uilib.box import Box
from uilib.footswitch import FootswitchWidget
from uilib.panel import Panel


SLOT_PITCH = 80
SLOT_WIDTH = 80
PANEL_W = SLOT_PITCH * 4
PANEL_H = 32


def _render(configs, is_on):
    panel = Panel(box=Box.xywh(0, 0, PANEL_W, PANEL_H))
    for i, (color, label) in enumerate(configs):
        FootswitchWidget(
            Box.xywh(i * SLOT_PITCH, 0, SLOT_WIDTH, PANEL_H),
            i, label, color, not is_on,
            parent=panel,
        )
    panel.refresh()
    return panel.image


def test_v3_footswitch_widget_on_configs(fake_lcd, snapshot):
    configs = [
        ((255, 235, 59),  "BRIGHT"),   # light pill → LUT picks black FG
        ((26, 58, 138),   "NIGHT"),    # dark pill  → LUT picks white FG
        (None,            "DFLT"),     # no color → explicit white default
        (None,            None),       # chassis only, no label
    ]
    fake_lcd.frames.append(_render(configs, is_on=True))
    snapshot()


def test_v3_footswitch_widget_off_configs(fake_lcd, snapshot):
    configs = [
        ((220, 40, 40),   "DIM"),
        (None,            "OFF"),
        ((220, 40, 40),   None),
        (None,            None),
    ]
    fake_lcd.frames.append(_render(configs, is_on=False))
    snapshot()


def test_v3_footswitch_widget_all_states(fake_lcd, snapshot):
    # All four visual states side-by-side for comparison.
    configs = [
        ((220, 40, 40),  "ON"),    # bound + on
        (None,           "on"),    # unbound + on
        ((220, 40, 40),  "OFF"),   # bound-but-off
        (None,           "off"),   # unbound + off
    ]
    fake_lcd.frames.append(_render(configs, is_on=False))
    snapshot()


def test_v3_footswitch_widget_truncates_long_labels(fake_lcd, snapshot):
    configs = [
        ((255, 235, 59), "Reverberation"),
        ((26, 58, 138),  "DistortionPlus"),
        (None,           "WWWWWWWWWWWW"),
        (None,           "Solo Channel 3"),
    ]
    fake_lcd.frames.append(_render(configs, is_on=True))
    snapshot()
