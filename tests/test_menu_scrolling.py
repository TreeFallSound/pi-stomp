"""
End-to-end tests for Menu scrolling: construct a Menu via Lcd, navigate
to items that overflow max_height, and verify that:
  - Menu.offset reflects the scroll
  - the selected widget's layout box, translated by Menu.offset, lands
    inside the visible viewport
  - the resulting LCD frame matches a stored snapshot

The "selected widget" includes the auto-inserted back arrow that Menu
appends when dismiss_option=True. These tests catch regressions where
selection navigation moves to an off-viewport widget but the container
fails to scroll, leaving the user with an invisible selection.
"""

from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import PROJECT_ROOT
from pistomp.lcd320x240 import Lcd


@pytest.fixture
def long_menu(fake_lcd):
    handler = MagicMock()
    handler.get_banks.return_value = {}
    handler.get_bank.return_value = None
    handler.get_num_footswitches.return_value = 4
    handler.hardware.version = 3
    handler.software_version = "1.0.0"
    handler.build_version = "20231027"
    handler.SystemState = "Running"
    handler.temperature = "45C"
    handler.throttled = "None"
    with patch("pistomp.lcd320x240.LcdIli9341", return_value=fake_lcd):
        lcd = Lcd(cwd=str(PROJECT_ROOT), handler=handler)
    items = [(f"Item {i:02d}", None, None) for i in range(15)]
    menu = lcd.draw_selection_menu(items, title="Long", auto_dismiss=False, dismiss_option=True)
    return menu, fake_lcd


def screen_box_of(widget, menu):
    """Where the widget actually lands inside the menu's viewport,
    given the menu's current scroll offset."""
    ox, oy = menu.offset
    return (
        widget.box.x0 - ox,
        widget.box.y0 - oy,
        widget.box.x1 - ox,
        widget.box.y1 - oy,
    )


def test_long_menu_overflows_initial_offset_zero(long_menu):
    menu, _ = long_menu
    # Sanity: the menu is actually taller than its viewport, so this
    # test is exercising the overflow path.
    total_items_height = menu.item_h * len(menu.sel_list)
    assert total_items_height > menu.box.height
    assert menu.offset == (0, 0)


def test_long_menu_back_arrow_appended(long_menu):
    menu, _ = long_menu
    # dismiss_option=True appends a back arrow as the last selectable item.
    back = menu.sel_list[-1]
    assert back.text == "\u2b05"


def test_navigating_back_to_back_arrow_scrolls(long_menu):
    menu, _ = long_menu
    # sel_prev from the default selection (index 0) wraps to the last item.
    menu.sel_prev()
    assert menu.sel == len(menu.sel_list) - 1
    # The menu must have scrolled — the back arrow's layout y is far below
    # max_height (15 items * item_h), so a non-scrolled menu would leave it
    # invisible.
    assert menu.offset[1] > 0


def test_back_arrow_lands_inside_viewport_after_scroll(long_menu):
    menu, _ = long_menu
    menu.sel_prev()
    back = menu.sel_list[-1]
    _, sy0, _, sy1 = screen_box_of(back, menu)
    # After scrolling, the back arrow must be fully inside [0, menu.box.height).
    assert 0 <= sy0
    assert sy1 <= menu.box.height


def test_scrolling_does_not_mutate_child_boxes(long_menu):
    """Regression guard for the old `_scroll_y` + child-box-mutation design.
    Children should keep their layout coordinates; only menu.offset moves."""
    menu, _ = long_menu
    back = menu.sel_list[-1]
    layout_y0_before = back.box.y0
    menu.sel_prev()
    assert back.box.y0 == layout_y0_before


def test_long_menu_scrolled_to_back_snapshot(long_menu, snapshot):
    menu, fake = long_menu
    menu.sel_prev()
    # The selection change triggers a refresh that propagates to FakeLcd.
    assert len(fake.frames) > 0
    snapshot()
