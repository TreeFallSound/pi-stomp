"""EthernetMenu snapshot + behaviour tests.

Replaces the live EthernetManager (sysfs polling thread) and JackMute
(subprocess) on the handler with controllable fakes, then exercises the
menu's render and action paths.

The menu is *read-only* since the "Mac owns the lifecycle" change: there
is no Enable/Disable button anymore, only status rows + Mute MOD + Back.
"""

from typing import Optional

import pytest

from emulator.stubs import StubJackMute
from ui.ethernet_menu import EthernetMenu, SPLIT
from uilib.dialog import MessageDialog


class FakeEthernetManager:
    """Mirrors the read-only EthernetManager surface used by EthernetMenu."""

    def __init__(
        self,
        carrier_up=True,
        service_active=False,
        ipv4="169.254.125.193/16",
        jack=(48000, 128),
        xruns=(0, 0, 0),
        health=(1, 6, "eth0"),
        link=(False, 0),
    ):
        self.carrier_up = carrier_up
        self.service_active = service_active
        self._ipv4 = ipv4
        self._jack = jack
        self._xruns = xruns
        self._health = health
        self._link = link

    def read_ipv4(self) -> Optional[str]:
        return self._ipv4

    def read_jack_settings(self):
        return self._jack

    def read_xrun_buckets(self):
        return self._xruns

    def read_netadapter_health(self):
        return self._health

    def read_link_health(self):
        return self._link

    def shutdown(self) -> None:
        pass


@pytest.fixture
def ethernet_env(v3_system):
    """Replace ethernet_manager and jack_mute with fakes; yield (lcd, fake_em, fake_mute)."""
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
    """Service inactive — only IP shown, MOD not muted."""
    lcd, em, _ = ethernet_env
    em.service_active = False
    _open(lcd)
    snapshot()


def test_ethernet_menu_enabled_with_stats(ethernet_env, snapshot):
    """Service active — sample rate, period, xrun buckets, link ports visible."""
    lcd, em, _ = ethernet_env
    em.service_active = True
    em._xruns = (1, 3, 7)
    _open(lcd)
    snapshot()


def test_ethernet_menu_duplicate_adapters_warning(ethernet_env, snapshot):
    """netadapters > 1 surfaces the duplicate-slave warning row."""
    lcd, em, _ = ethernet_env
    em.service_active = True
    em._health = (2, 6, "eth0")  # two netadapters contend for one stream
    _open(lcd)
    snapshot()


def test_ethernet_menu_link_resyncing(ethernet_env, snapshot):
    """netadapter is restarting its link — the port count is replaced by the
    one row that reports it, plus the remedy."""
    lcd, em, _ = ethernet_env
    em.service_active = True
    em._link = (True, 4)
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
    """No carrier → dialog reports the cable is disconnected."""
    lcd, em, _ = ethernet_env
    em.carrier_up = False
    _open(lcd)
    snapshot()


# ---------------------------------------------------------------------------
# Behaviour tests
# ---------------------------------------------------------------------------


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


def test_menu_has_no_enable_disable_button(ethernet_env):
    """The Enable/Disable verb went with the Mac-owns-lifecycle change.
    Nothing on this screen may let a musician toggle the service."""
    lcd, em, _ = ethernet_env
    em.service_active = False
    menu = _open(lcd)
    assert menu._panel is not None
    labels = [w.text for w in menu._panel.sel_list]
    assert "Enable" not in labels
    assert "Disable" not in labels


# ---------------------------------------------------------------------------
# In-place update regression tests
# ---------------------------------------------------------------------------


def test_tick_does_not_rebuild_panel(ethernet_env):
    lcd, em, _ = ethernet_env
    em.service_active = True
    em._xruns = (0, 0, 0)
    menu = _open(lcd)
    first_panel = menu._panel
    menu.tick()
    assert menu._panel is first_panel, "tick() must not pop+rebuild the dialog"
    assert len(menu._xrun_widgets) == 3
    widget_ids = [id(w) for w in menu._xrun_widgets]
    menu.tick()
    assert [id(w) for w in menu._xrun_widgets] == widget_ids


def test_tick_updates_xrun_text_in_place(ethernet_env):
    lcd, em, _ = ethernet_env
    em.service_active = True
    em._xruns = (0, 0, 0)
    menu = _open(lcd)
    em._xruns = (1, 3, 7)
    menu.tick()
    assert menu._xrun_widgets[0].text == "xruns 1m:" + SPLIT + "1"
    assert menu._xrun_widgets[1].text == "xruns 5m:" + SPLIT + "3"
    assert menu._xrun_widgets[2].text == "xruns 15m:" + SPLIT + "7"


def test_tick_noop_when_service_inactive(ethernet_env):
    lcd, em, _ = ethernet_env
    em.service_active = False
    menu = _open(lcd)
    first_panel = menu._panel
    assert menu._xrun_widgets == []
    menu.tick()
    assert menu._panel is first_panel  # still untouched


def test_toggle_mute_updates_button_label(ethernet_env):
    lcd, em, mute = ethernet_env
    em.service_active = True
    menu = _open(lcd)
    mute_btn = menu._mute_btn
    assert mute_btn is not None
    assert mute_btn.text == "Mute MOD"
    menu._on_toggle_mute()
    assert menu._panel is mute_btn.parent  # no rebuild
    assert mute_btn.text == "Unmute MOD"
    menu._on_toggle_mute()
    assert mute_btn.text == "Mute MOD"


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
