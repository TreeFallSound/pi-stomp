"""The footswitch bar: single-widget NAV selection and the LONG_CLICK bindings
menu (ui/footswitch_menu.py).
"""

from __future__ import annotations

import msgspec
import yaml

from uilib.footswitch import FootswitchBarPanel
from uilib.text import TextWidget
import pistomp.config as config
from pistomp.config.adapt_v1 import _footswitch
from pistomp.config.model import MINUS, LongpressBoard, LongpressMidiCC, LongpressPreset, PresetStep
from pistomp.config.schema_v1 import FootswitchEntry
from ui.footswitch_menu import _partition_rows, _rows_from_bindings
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click, nav_step


def _bindings(entries):
    return [_footswitch(msgspec.convert(e, FootswitchEntry), midi_channel=0) for e in entries]


def test_rows_from_bindings_chords_and_solo():
    id_to_letter = {0: "A", 1: "B", 2: "C", 3: "D"}
    entries = [
        {"id": 0, "longpress": "toggle_bypass"},
        {"id": 1, "longpress": "toggle_bypass"},
        {"id": 2, "longpress": "toggle_tuner_enable"},
        {"id": 3, "longpress": {"pedalboard": "DOWN"}},
    ]
    rows = _rows_from_bindings(_bindings(entries), id_to_letter)
    assert rows == [
        ("A+B", "Toggle Bypass"),
        ("C", "Tuner"),
        ("D", f"Pedalboard {MINUS}"),
    ]


def test_rows_from_bindings_skips_entries_without_longpress():
    id_to_letter = {0: "A", 1: "B"}
    entries = [{"id": 0, "midi_CC": 60}, {"id": 1, "longpress": "next_snapshot"}]
    assert _rows_from_bindings(_bindings(entries), id_to_letter) == [("B", "Snapshot +")]


def test_label_method_on_longpress_actions():
    assert LongpressMidiCC(cc=64).label() == "MIDI CC 64"
    assert LongpressPreset(preset=PresetStep.UP).label() == "Snapshot +"
    assert LongpressPreset(preset=PresetStep.DOWN).label() == f"Snapshot {MINUS}"
    assert LongpressPreset(preset=2).label() == "Snapshot 2"
    assert LongpressBoard(direction="UP").label() == "Pedalboard +"


def _row_texts(dialog) -> list[str]:
    return [w.text for w in dialog.children if isinstance(w, TextWidget) and TextWidget.SPLIT_SEP in w.text]


def test_footswitch_bar_selection_and_menu(v3_system: SystemFixture):
    handler = v3_system.handler
    lcd = handler.lcd
    assert lcd is not None
    bar = lcd.footswitch_panel
    assert isinstance(bar, FootswitchBarPanel)

    # Selecting the bar is one NAV stop, never the individual footswitches.
    while lcd.main_panel.sel_ref is not bar:
        nav_step(handler, 1)
    assert bar.selected

    # LONG_CLICK opens the bindings menu: default_config_pistomptre.yml rows.
    # Every switch carries a two-name longpress there, so each also chords into
    # a pedalboard step.
    nav_click(handler, long=True)
    menu_panel = lcd.footswitch_menu._panel
    assert menu_panel is not None
    assert lcd.pstack.stack[-1] is menu_panel
    texts = _row_texts(menu_panel)
    assert texts == [
        "A" + TextWidget.SPLIT_SEP + f"Snapshot {MINUS}",
        "B" + TextWidget.SPLIT_SEP + "Snapshot +",
        "C" + TextWidget.SPLIT_SEP + "Tuner",
        "D" + TextWidget.SPLIT_SEP + "Tap Tempo",
        "A+B" + TextWidget.SPLIT_SEP + f"Pedalboard {MINUS}",
        "C+D" + TextWidget.SPLIT_SEP + "Pedalboard +",
    ]
    assert menu_panel.divider_y is not None  # pyright: ignore[reportAttributeAccessIssue]

    nav_click(handler)  # Back
    assert lcd.footswitch_menu._panel is None
    assert menu_panel not in lcd.pstack.stack


def test_footswitch_menu_snapshot(v3_system: SystemFixture, snapshot):
    handler = v3_system.handler
    lcd = handler.lcd
    assert lcd is not None

    while lcd.main_panel.sel_ref is not lcd.footswitch_panel:
        nav_step(handler, 1)
    nav_click(handler, long=True)
    snapshot("menu")

    nav_click(handler)  # Back
    assert lcd.footswitch_menu._panel is None
    snapshot("menu_dismissed")


def test_partition_rows_singles_before_chords():
    rows = [("A", "x"), ("A+B", "y"), ("B", "z"), ("C+D", "w")]
    assert _partition_rows(rows) == ([("A", "x"), ("B", "z")], [("A+B", "y"), ("C+D", "w")])


def test_footswitch_menu_pedalboard_rows_and_divider(v3_system: SystemFixture, tmp_path):
    handler = v3_system.handler
    lcd = handler.lcd
    assert lcd is not None

    bundle_dir = tmp_path / "chord.pedalboard"
    bundle_dir.mkdir()
    (bundle_dir / "config.yml").write_text(
        yaml.dump(
            {
                "hardware": {
                    "footswitches": [
                        {"id": 0, "longpress": "toggle_bypass"},
                        {"id": 1, "longpress": "toggle_bypass"},
                    ]
                }
            }
        )
    )
    handler.current.pedalboard.bundle = str(bundle_dir)
    handler.hardware.reinit(config.resolve(handler.hardware.default_cfg, bundle_dir))

    lcd.footswitch_menu.open()
    menu_panel = lcd.footswitch_menu._panel
    assert menu_panel is not None
    texts = _row_texts(menu_panel)
    assert texts == [
        "C" + TextWidget.SPLIT_SEP + "Tuner",
        "D" + TextWidget.SPLIT_SEP + "Tap Tempo",
        "A+B" + TextWidget.SPLIT_SEP + "Toggle Bypass",
        "C+D" + TextWidget.SPLIT_SEP + "Pedalboard +",
    ]
    assert menu_panel.divider_y is not None  # pyright: ignore[reportAttributeAccessIssue]
