"""EthernetMenu snapshot + behaviour tests.

Replaces the live EthernetManager (sysfs polling thread) and JackMute
(subprocess) on the handler with controllable fakes, then exercises the
menu's render and action paths.
"""

from typing import Optional
from unittest.mock import patch

import pytest

from emulator.stubs import StubJackMute
from ui.ethernet_menu import EthernetMenu
from uilib.dialog import Dialog, MessageDialog
from uilib.misc import InputEvent


class FakeEthernetManager:
    """Mirrors the EthernetManager surface used by EthernetMenu, with no I/O."""

    def __init__(self, carrier_up=True, service_active=False,
                 ipv4="169.254.125.193/16", jack=(48000, 128),
                 xruns=(0, 0, 0)):
        self.carrier_up = carrier_up
        self.service_active = service_active
        self._ipv4 = ipv4
        self._jack = jack
        self._xruns = xruns
        self.start_calls = 0
        self.stop_calls = 0

    def read_ipv4(self) -> Optional[str]:
        return self._ipv4

    def read_jack_settings(self):
        return self._jack

    def read_xrun_buckets(self):
        return self._xruns

    def start_service(self) -> None:
        self.start_calls += 1
        self.service_active = True

    def stop_service(self) -> None:
        self.stop_calls += 1
        self.service_active = False

    def shutdown(self) -> None:
        pass


@pytest.fixture
def ethernet_env(v3_system):
    """Replace the live ethernet_manager and jack_mute with fakes; yield (lcd, fake_em, fake_mute)."""
    handler = v3_system.handler
    handler.ethernet_manager.shutdown()
    fake_em = FakeEthernetManager()
    fake_mute = StubJackMute()
    handler.ethernet_manager = fake_em
    handler.jack_mute = fake_mute
    return v3_system.handler._lcd, fake_em, fake_mute


def _open(lcd) -> EthernetMenu:
    menu = EthernetMenu(lcd)
    menu.open()
    return menu


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------


def test_ethernet_menu_disabled(ethernet_env, snapshot):
    """Service inactive — only IP shown, toggle says Enable, MOD not muted."""
    lcd, em, _ = ethernet_env
    em.service_active = False
    _open(lcd)
    snapshot()


def test_ethernet_menu_enabled_with_stats(ethernet_env, snapshot):
    """Service active — sample rate, period, xrun buckets visible."""
    lcd, em, _ = ethernet_env
    em.service_active = True
    em._xruns = (1, 3, 7)
    _open(lcd)
    snapshot()


def test_ethernet_menu_muted(ethernet_env, snapshot):
    """Service active + MOD muted → button reads "Unmute MOD"."""
    lcd, em, mute = ethernet_env
    em.service_active = True
    mute.mute()
    _open(lcd)
    snapshot()


def test_ethernet_menu_cable_disconnected(ethernet_env, snapshot):
    """No carrier → dialog reports the cable is disconnected, no toggle row."""
    lcd, em, _ = ethernet_env
    em.carrier_up = False
    _open(lcd)
    snapshot()


# ---------------------------------------------------------------------------
# Behaviour tests
# ---------------------------------------------------------------------------


def test_enable_calls_start_service(ethernet_env):
    lcd, em, _ = ethernet_env
    em.service_active = False
    menu = _open(lcd)
    menu._on_enable()
    assert em.start_calls == 1


def test_disable_calls_stop_service(ethernet_env):
    lcd, em, _ = ethernet_env
    em.service_active = True
    menu = _open(lcd)
    menu._on_disable()
    assert em.stop_calls == 1


def test_toggle_mute_when_unmuted_calls_mute(ethernet_env):
    lcd, em, mute = ethernet_env
    em.service_active = True
    menu = _open(lcd)
    assert mute.is_muted() is False
    menu._on_toggle_mute()
    assert mute.is_muted() is True


def test_toggle_mute_when_muted_calls_unmute(ethernet_env):
    lcd, em, mute = ethernet_env
    em.service_active = True
    mute.mute()
    menu = _open(lcd)
    menu._on_toggle_mute()
    assert mute.is_muted() is False


def test_open_with_no_carrier_shows_message_dialog(ethernet_env):
    lcd, em, _ = ethernet_env
    em.carrier_up = False
    _open(lcd)
    assert isinstance(lcd.pstack.current, MessageDialog)


def test_notify_change_rerenders_on_state_flip(ethernet_env):
    lcd, em, _ = ethernet_env
    em.service_active = False
    menu = _open(lcd)
    first_panel = menu._panel
    em.service_active = True
    menu.notify_change()
    assert menu._panel is not first_panel  # rebuilt
    assert lcd.pstack.current is menu._panel


def test_notify_change_pops_when_cable_unplugged(ethernet_env):
    lcd, em, _ = ethernet_env
    em.service_active = True
    menu = _open(lcd)
    em.carrier_up = False
    menu.notify_change()
    assert menu._panel is None
    assert isinstance(lcd.pstack.current, MessageDialog)


def test_back_pops_panel(ethernet_env):
    lcd, em, _ = ethernet_env
    menu = _open(lcd)
    panel = menu._panel
    assert lcd.pstack.current is panel
    menu._on_back()
    assert menu._panel is None
    assert lcd.pstack.current is not panel


def test_enable_then_state_flip_shows_disable(ethernet_env):
    """After Enable fires, bg poll flips service_active; next render shows Disable."""
    lcd, em, _ = ethernet_env
    em.service_active = False
    menu = _open(lcd)
    menu._on_enable()  # StubFake flips service_active to True synchronously
    # Find the toggle widget by walking the panel's selectable list.
    labels = [w.text for w in menu._panel.sel_list]
    assert "Disable" in labels
