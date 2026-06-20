"""FootswitchWidget snapshot coverage — 8 configurations across 2 frames.

Each frame mimics the v3 footswitch strip (4 slots, 320x36) so a single
snapshot exercises four widget configurations at once.
"""
from uilib.box import Box
from uilib.footswitch import FootswitchWidget
from uilib.panel import Panel


NUM_SLOTS = 4
PANEL_W = 320
PANEL_H = 36
SLOT_PITCH = PANEL_W // NUM_SLOTS  # 80
SLOT_WIDTH = SLOT_PITCH


def _render(configs, is_on):
    panel = Panel(box=Box.xywh(0, 0, PANEL_W, PANEL_H))
    for i, (color, label) in enumerate(configs):
        FootswitchWidget(
            Box.xywh(i * SLOT_PITCH, 0, SLOT_WIDTH, PANEL_H),
            label, color, not is_on,
            parent=panel,
        )
    panel.refresh()
    return panel.surface


def test_v3_footswitch_widget_on_configs(fake_lcd, snapshot):
    configs = [
        ((255, 235, 59),  "BRIGHT"),   # bound + on, light category color
        ((26, 58, 138),   "NIGHT"),    # bound + on, dark category color
        (None,            "DFLT"),     # bound + on, no color → white dot
        (None,            None),       # unassigned → letter badge "D"
    ]
    fake_lcd.frames.append(_render(configs, is_on=True))
    snapshot()


def test_v3_footswitch_widget_off_configs(fake_lcd, snapshot):
    configs = [
        ((220, 40, 40),   "DIM"),      # bound + off, red category
        (None,            "OFF"),      # bound + off, no color
        ((220, 40, 40),   None),       # unassigned → letter badge "C"
        (None,            None),       # unassigned → letter badge "D"
    ]
    fake_lcd.frames.append(_render(configs, is_on=False))
    snapshot()


def test_v3_footswitch_widget_all_states(fake_lcd, snapshot):
    # All four visual states side-by-side for comparison.
    configs = [
        ((220, 40, 40),  "ON"),    # bound + on
        (None,           "on"),    # bound + on, no color
        ((220, 40, 40),  "OFF"),   # bound + off
        (None,           None),    # unassigned → letter badge
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
