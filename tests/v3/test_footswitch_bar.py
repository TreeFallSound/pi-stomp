"""The footswitch bar: single-widget NAV selection, CLICK-toggled expansion,
and the LONG_CLICK bindings menu (ui/footswitch_menu.py).
"""

from __future__ import annotations

import yaml

from uilib.footswitch import FootswitchBarPanel
from uilib.gridpanel import GridPanel
from uilib.text import TextWidget
from ui.footswitch_menu import _label_for_mapping, _partition_rows, _rows_from_entries
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click, nav_step


def test_rows_from_entries_chords_and_solo():
    id_to_letter = {0: "A", 1: "B", 2: "C", 3: "D"}
    entries = [
        {"id": 0, "longpress": "toggle_bypass"},
        {"id": 1, "longpress": "toggle_bypass"},  # chords with id 0 (shared name)
        {"id": 2, "longpress": "toggle_tuner_enable"},  # solo
        {"id": 3, "longpress": {"pedalboard": "DOWN"}},  # mapping-form: never chords
    ]
    rows = _rows_from_entries(entries, id_to_letter)
    assert rows == [
        ("A+B", "Toggle Bypass"),
        ("C", "Tuner"),
        ("D", "Pedalboard -"),
    ]


def test_rows_from_entries_skips_entries_without_longpress():
    id_to_letter = {0: "A", 1: "B"}
    entries = [{"id": 0, "midi_CC": 60}, {"id": 1, "longpress": "next_snapshot"}]
    assert _rows_from_entries(entries, id_to_letter) == [("B", "Snapshot +")]


def test_label_for_mapping_preset_and_midi():
    assert _label_for_mapping({"midi_CC": 64}) == "MIDI CC 64"
    assert _label_for_mapping({"preset": "UP"}) == "Preset +"
    assert _label_for_mapping({"preset": "DOWN"}) == "Preset -"
    assert _label_for_mapping({"preset": 2}) == "Preset 2"
    assert _label_for_mapping({"pedalboard": "UP"}) == "Pedalboard +"


def _row_texts(dialog) -> list[str]:
    return [w.text for w in dialog.children if isinstance(w, TextWidget) and TextWidget.SPLIT_SEP in w.text]


def test_footswitch_bar_selection_expand_and_menu(v3_system: SystemFixture):
    handler = v3_system.handler
    lcd = handler.lcd
    assert lcd is not None
    bar = lcd.footswitch_panel
    assert isinstance(bar, FootswitchBarPanel)

    # Selecting the bar is one NAV stop, never the individual footswitches.
    while lcd.main_panel.sel_ref is not bar:
        nav_step(handler, 1)
    assert bar.selected
    assert bar.expanded is False
    collapsed_h = bar.box.height

    # CLICK expands the bar, bottom-anchored, leaving room for three tile rows.
    nav_click(handler)
    assert bar.expanded is True
    assert bar.box.height > collapsed_h
    assert bar.box.y1 == lcd.display_height

    grid = lcd.grid_panel
    assert grid is not None
    assert grid.bottom_inset == bar.box.height
    assert grid._viewport_size()[1] == GridPanel.rows_height(3)

    nav_click(handler)
    assert bar.expanded is False
    assert bar.box.height == collapsed_h
    assert grid.bottom_inset == collapsed_h

    # LONG_CLICK opens the bindings menu: default_config_pistomptre.yml rows,
    # no pedalboard config.yml on this fixture's (fake-path) bundle, so no divider.
    nav_click(handler, long=True)
    menu_panel = lcd.footswitch_menu._panel
    assert menu_panel is not None
    assert lcd.pstack.stack[-1] is menu_panel
    texts = _row_texts(menu_panel)
    assert texts == [
        "A" + TextWidget.SPLIT_SEP + "Snapshot -",
        "B" + TextWidget.SPLIT_SEP + "Snapshot +",
        "C" + TextWidget.SPLIT_SEP + "Tuner",
        "D" + TextWidget.SPLIT_SEP + "Tap Tempo On/Off",
    ]
    assert menu_panel.divider_y is None  # pyright: ignore[reportAttributeAccessIssue]

    nav_click(handler)  # Back
    assert lcd.footswitch_menu._panel is None
    assert menu_panel not in lcd.pstack.stack


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

    lcd.footswitch_menu.open()
    menu_panel = lcd.footswitch_menu._panel
    assert menu_panel is not None
    texts = _row_texts(menu_panel)
    assert texts == [
        "C" + TextWidget.SPLIT_SEP + "Tuner",
        "D" + TextWidget.SPLIT_SEP + "Tap Tempo On/Off",
        "A+B" + TextWidget.SPLIT_SEP + "Toggle Bypass",
    ]
    assert menu_panel.divider_y is not None  # pyright: ignore[reportAttributeAccessIssue]
