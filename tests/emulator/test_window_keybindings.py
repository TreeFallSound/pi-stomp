"""Keybinding → control-callback dispatch in EmulatorWindow.

Builds a real EmulatorWindow against a fake hardware object whose controls are
all MagicMocks, then drives synthetic pygame KEYDOWN events through
process_events() and asserts the right control method was invoked. Catches
keybinding-map drift without booting the full handler stack."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame
import pygame._freetype as _freetype
import pytest

import pistomp.switchstate as switchstate
from emulator.window import EmulatorWindow


@pytest.fixture(scope="module", autouse=True)
def _pygame_init():
    pygame.init()
    _freetype.init()
    yield
    pygame.quit()


def _fake_lcd():
    surf = pygame.Surface((320, 240))
    return SimpleNamespace(
        width=320,
        height=240,
        surface=surf,
        blit_scaled=MagicMock(),
    )


def _make_window(num_fs=4, num_tweak=2, with_nav=True, with_volume=True, with_expr=True):
    hw = SimpleNamespace()
    hw.lcd_pygame = _fake_lcd()
    hw.footswitches = [
        MagicMock(name=f"fs{i}", display_label=None, get_display_label=MagicMock(return_value=None))
        for i in range(num_fs)
    ]
    for fs in hw.footswitches:
        fs.toggled = False

    nav = MagicMock(name="nav") if with_nav else None
    if nav:
        nav.press_callback = None
    hw.nav_encoder = nav
    hw.encoders = []
    if nav:
        hw.encoders.append(nav)

    hw.tweak_encoders = []
    for i in range(num_tweak):
        t = MagicMock(name=f"tweak{i}")
        t.midi_CC = 70 + i
        t.id = i + 1
        t.press_callback = None
        hw.tweak_encoders.append(t)
        hw.encoders.append(t)

    vol = MagicMock(name="vol") if with_volume else None
    if vol:
        vol.type = "VOLUME"
        vol.id = "v"
        vol.press_callback = None
        vol.midi_CC = None
    hw.volume_encoder = vol
    if vol:
        hw.encoders.append(vol)

    if with_expr:
        expr = MagicMock(name="expr")
        expr.midi_CC = 75
        hw.analog_controls = [expr]
    else:
        hw.analog_controls = []

    return EmulatorWindow(hw), hw


def _send_key(window, key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
    window.process_events()


# ---------------------------------------------------------------------------
# Footswitches
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,index",
    [
        (pygame.K_1, 0),
        (pygame.K_2, 1),
        (pygame.K_3, 2),
        (pygame.K_4, 3),
    ],
)
def test_number_key_presses_corresponding_footswitch(key, index):
    window, hw = _make_window()
    _send_key(window, key)
    hw.footswitches[index].press.assert_called_once_with()
    for i, fs in enumerate(hw.footswitches):
        if i != index:
            fs.press.assert_not_called()


# ---------------------------------------------------------------------------
# Nav encoder
# ---------------------------------------------------------------------------


def test_arrows_step_nav_encoder():
    window, hw = _make_window()
    _send_key(window, pygame.K_LEFT)
    _send_key(window, pygame.K_RIGHT)
    assert [c.args for c in hw.nav_encoder.step.call_args_list] == [(-1,), (1,)]


def test_enter_and_l_press_nav_encoder_with_correct_state():
    window, hw = _make_window()
    _send_key(window, pygame.K_RETURN)
    _send_key(window, pygame.K_l)
    calls = [c.args for c in hw.nav_encoder.press.call_args_list]
    assert calls == [(switchstate.Value.RELEASED,), (switchstate.Value.LONGPRESSED,)]


# ---------------------------------------------------------------------------
# Tweak encoders
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "left,right,press,index",
    [
        (pygame.K_q, pygame.K_w, pygame.K_e, 0),
        (pygame.K_a, pygame.K_s, pygame.K_d, 1),
    ],
)
def test_tweak_encoder_keybindings(left, right, press, index):
    window, hw = _make_window()
    _send_key(window, left)
    _send_key(window, right)
    _send_key(window, press)
    enc = hw.tweak_encoders[index]
    assert [c.args for c in enc.step.call_args_list] == [(-1,), (1,)]
    enc.press.assert_called_once_with(switchstate.Value.RELEASED)


# ---------------------------------------------------------------------------
# Expression pedal
# ---------------------------------------------------------------------------


def test_up_down_arrows_nudge_expression_pedal():
    window, hw = _make_window()
    expr = hw.analog_controls[0]
    start = window._exp_value

    _send_key(window, pygame.K_UP)
    assert window._exp_value == start + 5
    expr.set_value.assert_called_with(start + 5)
    expr.send_midi.assert_called_with(start + 5)

    _send_key(window, pygame.K_DOWN)
    assert window._exp_value == start


# ---------------------------------------------------------------------------
# Quit
# ---------------------------------------------------------------------------


def test_escape_raises_keyboard_interrupt():
    window, _ = _make_window()
    with pytest.raises(KeyboardInterrupt):
        _send_key(window, pygame.K_ESCAPE)
