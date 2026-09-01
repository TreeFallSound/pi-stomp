"""The analog row: single-widget NAV selection, and the menu that turns one
input on or off (ui/analog_menu.py)."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

from pistomp.controller import ControlType
from pistomp.input_enable import SETTING
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click, nav_step
from uilib.analog_bar import AnalogBarPanel
from uilib.text import TextWidget


@pytest.fixture
def input_enable_seed():
    """This module pins the shipped device default, not the test-rig default."""
    return None


def _row_texts(dialog) -> list[str]:
    return [w.text for w in dialog.children if isinstance(w, TextWidget) and TextWidget.SPLIT_SEP in w.text]


def _select_analog_row(handler) -> AnalogBarPanel:
    lcd = handler.lcd
    assert lcd is not None
    bar = lcd.analog_panel
    assert isinstance(bar, AnalogBarPanel)
    while lcd.main_panel.sel_ref is not bar:
        nav_step(handler, 1)
    return bar


def _expression(hw):
    return next(c for c in hw.analog_controls if c.type is ControlType.EXPRESSION)


def test_expression_input_is_off_until_the_user_turns_it_on(v3_system: SystemFixture):
    """An empty jack reads noise, so EXPRESSION starts off. Every other input
    starts on."""
    hw = v3_system.hw
    assert _expression(hw).disabled
    assert not any(e.disabled for e in hw.encoders)


def test_analog_row_selection_and_menu(v3_system: SystemFixture):
    handler = v3_system.handler
    lcd = handler.lcd
    assert lcd is not None

    bar = _select_analog_row(handler)
    assert bar.selected

    nav_click(handler)
    menu_panel = lcd.analog_menu._panel
    assert menu_panel is not None
    assert lcd.pstack.stack[-1] is menu_panel
    assert _row_texts(menu_panel) == [
        "EXP  CC 75" + TextWidget.SPLIT_SEP + "off",
        "K1  CC 70" + TextWidget.SPLIT_SEP + "on",
        "K2  CC 71" + TextWidget.SPLIT_SEP + "on",
        "VOL  output volume" + TextWidget.SPLIT_SEP + "on",
    ]

    nav_step(handler, len(_row_texts(menu_panel)))  # past the last row, onto Back
    nav_click(handler)
    assert lcd.analog_menu._panel is None
    assert menu_panel not in lcd.pstack.stack


def test_toggle_expression_on_and_off(v3_system: SystemFixture):
    handler = v3_system.handler
    hw = v3_system.hw
    lcd = handler.lcd
    assert lcd is not None
    control = _expression(hw)

    _select_analog_row(handler)
    nav_click(handler)
    menu_panel = lcd.analog_menu._panel
    assert menu_panel is not None

    settings = cast(MagicMock, handler.settings)

    nav_click(handler)  # the EXP row is the first stop
    assert not control.disabled
    assert _row_texts(menu_panel)[0] == "EXP  CC 75" + TextWidget.SPLIT_SEP + "on"
    settings.set_setting.assert_called_with(SETTING, {0: True})

    nav_click(handler)
    assert control.disabled
    settings.set_setting.assert_called_with(SETTING, {0: False})


def test_the_choice_outlives_a_pedalboard_load(v3_system: SystemFixture):
    """`reinit` applies the config of the new board to every control, so the
    user's choice has to survive it."""
    handler = v3_system.handler
    hw = v3_system.hw
    control = _expression(hw)

    hw.set_input_enabled(control, True)
    hw.reinit(hw.config)
    assert not control.disabled

    hw.set_input_enabled(control, False)
    hw.reinit(hw.config)
    assert control.disabled


def test_analog_menu_snapshot(v3_system: SystemFixture, snapshot):
    handler = v3_system.handler
    lcd = handler.lcd
    assert lcd is not None

    snapshot("row_expression_off")
    _select_analog_row(handler)
    nav_click(handler)
    snapshot("menu")

    nav_click(handler)  # turn the expression pedal on
    snapshot("menu_expression_on")

    nav_step(handler, 4)
    nav_click(handler)  # Back
    assert lcd.analog_menu._panel is None
    snapshot("row_expression_on")
