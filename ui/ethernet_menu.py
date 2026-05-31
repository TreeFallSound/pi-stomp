# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from typing import TYPE_CHECKING, Optional, Protocol, cast

from PIL import ImageFont

from modalapi.ethernet import EthernetManager
from uilib import (
    Box,
    Dialog,
    MessageDialog,
    TextWidget,
    WidgetAlign,
)

if TYPE_CHECKING:
    from pistomp.lcd320x240 import Lcd


SPLIT = TextWidget.SPLIT_SEP
DIALOG_W = 280
DIALOG_H = 200


class _EthernetHost(Protocol):
    # Optional on v1/v2 (mod.py); v3 (modhandler.py) always sets it. EthernetMenu
    # is only reachable when WifiMenu has already verified the manager is present
    # and carrier is up, so the property below asserts rather than guarding.
    ethernet_manager: Optional[EthernetManager]


class EthernetMenu:
    """The Wired Connection sub-screen: status readout + enable/disable toggle.

    A single Dialog is pushed onto the panel stack; re-renders are done by
    popping and rebuilding (mirroring WifiMenu.notify_status_change). State
    comes from EthernetManager, which polls carrier + service-active on a
    background thread; this class touches the panel stack only from the UI
    thread (via handler poll-loop callbacks).
    """

    def __init__(self, lcd: 'Lcd') -> None:
        self.lcd: 'Lcd' = lcd
        self._panel: Optional[Dialog] = None

    @property
    def _host(self) -> _EthernetHost:
        h = self.lcd.handler
        assert h is not None, "EthernetMenu requires lcd.handler to be set"
        return cast(_EthernetHost, h)

    @property
    def _manager(self) -> EthernetManager:
        mgr = self._host.ethernet_manager
        assert mgr is not None, "EthernetMenu opened without EthernetManager"
        return mgr

    @property
    def _pstack(self):
        return self.lcd.pstack

    # ----- entry points -----

    def open(self, event: object = None, widget: object = None) -> None:
        if not self._manager.carrier_up:
            self._show_disconnected_dialog()
            return
        self._render()

    def notify_change(self) -> None:
        """Carrier or service-active flipped — re-render if we're on top.

        If the cable was pulled, pop the sub-screen and surface the
        disconnected dialog so the user isn't left looking at a stale IP."""
        if self._panel is None or self._pstack.current is not self._panel:
            return
        if not self._manager.carrier_up:
            old = self._panel
            self._panel = None
            self._pstack.pop_panel(old)
            self._show_disconnected_dialog()
            return
        self._render()

    def tick(self) -> None:
        """Periodic re-render while we're on top, so xrun counters update
        without the user leaving the screen. Cheap — the file is bounded."""
        if self._panel is None or self._pstack.current is not self._panel:
            return
        if not self._manager.carrier_up:
            return  # notify_change will handle pop-and-dialog
        if not self._manager.service_active:
            return  # static screen, no need to redraw
        self._render()

    # ----- rendering -----

    def _render(self) -> None:
        if self._panel is not None:
            old = self._panel
            self._panel = None
            self._pstack.pop_panel(old)

        d = Dialog(width=DIALOG_W, height=DIALOG_H,
                   title="Ethernet Audio Interface", auto_destroy=True)
        font = ImageFont.truetype("DejaVuSans.ttf", 14)

        rows: list[tuple[str, str]] = [("IP:", self._manager.read_ipv4() or "—")]
        if self._manager.service_active:
            sr, period = self._manager.read_jack_settings()
            b1, b5, b15 = self._manager.read_xrun_buckets()
            rows.append(("Sample Rate:", "%d Hz" % sr if sr else "—"))
            rows.append(("Period:", "%d frames" % period if period else "—"))
            rows.append(("xruns 1m:", str(b1)))
            rows.append(("xruns 5m:", str(b5)))
            rows.append(("xruns 15m:", str(b15)))
            button_label = "Disable Ethernet Audio"
            action = self._on_disable
        else:
            button_label = "Enable Ethernet Audio"
            action = self._on_enable

        line_h = 18
        y = 4
        for label, value in rows:
            TextWidget(box=Box.xywh(8, y, DIALOG_W - 16, line_h),
                       text=label + SPLIT + value, font=font, parent=d,
                       outline=0, sel_width=0, align=WidgetAlign.NONE)
            y += line_h

        btn_y = DIALOG_H - 36
        btn = TextWidget(box=Box.xywh(0, btn_y, 0, 0), text=button_label, parent=d,
                         outline=1, sel_width=3, outline_radius=5,
                         action=action, align=WidgetAlign.CENTRE,
                         name='ethernet_toggle_btn')
        d.add_sel_widget(btn)
        d.sel_widget(btn)

        self._panel = d
        self._pstack.push_panel(d)
        d.refresh()

    def _show_disconnected_dialog(self) -> None:
        self._pstack.push_panel(
            MessageDialog(self._pstack, "Ethernet cable disconnected.",
                          title="Wired Connection"))

    # ----- actions -----

    def _on_enable(self, _event: object = None, _widget: object = None) -> None:
        self._manager.start_service()
        # service_active flips on the next manager poll cycle (≤2s);
        # notify_change() will re-render at that point.

    def _on_disable(self, _event: object = None, _widget: object = None) -> None:
        self._manager.stop_service()
