# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from typing import TYPE_CHECKING, Optional, Protocol, cast

from pathlib import Path
from uilib.pygame_init import font as _make_font

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

from modalapi.ethernet import EthernetManager
from modalapi.jack_mute import JackMute
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
BACK_GLYPH = "\u2b05"  # ⬅ — matches uilib.menu's dismiss-row idiom
DIALOG_W = 280
DIALOG_H = 200


class _EthernetHost(Protocol):
    # Optional on v1/v2 (mod.py); v3 (modhandler.py) always sets them. EthernetMenu
    # is only reachable when WifiMenu has already verified the manager is present
    # and carrier is up, so the properties below assert rather than guarding.
    ethernet_manager: Optional[EthernetManager]
    jack_mute: Optional[JackMute]


class EthernetMenu:
    """The Wired Connection sub-screen. Status readout only.

    The Enable/Disable toggle is gone (see modalapi/ethernet/manager.py).
    pi-stomp-jackbridge starts when the Mac asks for it and stays under
    systemd supervision. A musician has nothing to toggle here. The repair
    verbs live in the Mac menu.

    One Dialog sits on the panel stack. A re-render pops and rebuilds it
    (like WifiMenu.notify_status_change). State comes from EthernetManager,
    which polls on a background thread. This class touches the panel stack
    only from the UI thread.
    """

    def __init__(self, lcd: "Lcd") -> None:
        self.lcd: "Lcd" = lcd
        self._panel: Optional[Dialog] = None
        # Kept across a pop/rebuild so a re-render holds the user's selection.
        # One of: 'back', 'mute', or None.
        self._last_selected_role: Optional[str] = None
        self._role_widgets: dict[str, object] = {}
        # Widgets that mutate in place. Reset on every _render(). tick()
        # updates the xrun rows with set_text(); the mute handler updates its
        # own label the same way. Neither path rebuilds the dialog, so a
        # button never moves under the user's finger.
        self._xrun_widgets: list[TextWidget] = []
        self._mute_btn: Optional[TextWidget] = None

    def _capture_selected_role(self) -> None:
        if self._panel is None or self._panel.sel_ref is None:
            return
        sel = self._panel.sel_ref
        for role, w in self._role_widgets.items():
            if w is sel:
                self._last_selected_role = role
                return

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
    def _mute(self) -> JackMute:
        m = self._host.jack_mute
        assert m is not None, "EthernetMenu opened without JackMute"
        return m

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
        """Carrier or service-active changed. Re-render if this panel is on top.

        If the cable was pulled, pop the sub-screen and show the
        disconnected dialog so no stale IP stays on screen."""
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
        """Update the xrun counters in place while this panel is on top.

        The other rows and the buttons are static between state changes.
        set_text() takes the per-widget dirty-rect path, so the buttons stay
        put and the SPI bus sees no full redraw."""
        if self._panel is None or self._pstack.current is not self._panel:
            return
        if not self._manager.carrier_up:
            return  # notify_change will handle pop-and-dialog
        if not self._manager.service_active:
            return  # no xrun rows to update
        if not self._xrun_widgets:
            return
        b1, b5, b15 = self._manager.read_xrun_buckets()
        self._xrun_widgets[0].set_text("xruns 1m:" + SPLIT + str(b1))
        self._xrun_widgets[1].set_text("xruns 5m:" + SPLIT + str(b5))
        self._xrun_widgets[2].set_text("xruns 15m:" + SPLIT + str(b15))

    # ----- rendering -----

    def _render(self) -> None:
        if self._panel is not None:
            self._capture_selected_role()
            old = self._panel
            self._panel = None
            self._pstack.pop_panel(old)

        # The old widgets are gone. Drop the refs so a render that races a
        # poll does not touch a dead widget.
        self._xrun_widgets = []
        self._mute_btn = None

        active = self._manager.service_active
        n_adapters, n_wired, route = self._manager.read_netadapter_health()
        resyncing, restarts = self._manager.read_link_health()

        d = Dialog(width=DIALOG_W, height=DIALOG_H, title="Ethernet Audio Interface", auto_destroy=True)
        font = _make_font(_FONTS_DIR / "DejaVuSans.ttf", 14)

        rows: list[tuple[str, str]] = [("IP:", self._manager.read_ipv4() or "—")]
        if active:
            sr, period = self._manager.read_jack_settings()
            b1, b5, b15 = self._manager.read_xrun_buckets()
            rows.append(("Sample Rate:", "%d Hz" % sr if sr else "—"))
            rows.append(("Period:", "%d frames" % period if period else "—"))
            rows.append(("xruns 1m:", str(b1)))
            rows.append(("xruns 5m:", str(b5)))
            rows.append(("xruns 15m:", str(b15)))
            if resyncing:
                # The ports stay wired through a netadapter restart, so the
                # port count (unfortunately) continues to read healthy
                rows.append(("Link:", f"⚠ resyncing (x{restarts})"))
                rows.append(("", "Restart JackBridge on Host"))
            else:
                rows.append(("Link ports:", f"{n_wired}/6 wired"))
            if n_adapters > 1:
                rows.append(("Adapters:", f"⚠ {n_adapters} (duplicate)"))
            if not route or route.startswith("wl"):
                rows.append(("Route:", f"⚠ {route or 'none'}"))

        muted = self._mute.is_muted()
        mute_label = "Unmute MOD" if muted else "Mute MOD"

        line_h = 18
        y = 4
        xrun_label_set = {"xruns 1m:", "xruns 5m:", "xruns 15m:"}
        for label, value in rows:
            w = TextWidget(
                box=Box.xywh(8, y, DIALOG_W - 16, line_h),
                text=label + SPLIT + value,
                font=font,
                parent=d,
                outline=0,
                sel_width=0,
                align=WidgetAlign.NONE,
            )
            if label in xrun_label_set:
                self._xrun_widgets.append(w)
            y += line_h

        btn_y = DIALOG_H - 36
        back_btn = TextWidget(
            box=Box.xywh(8, btn_y, 0, 0),
            text=BACK_GLYPH,
            parent=d,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=self._on_back,
            align=WidgetAlign.NONE,
            name="ethernet_back_btn",
        )
        d.add_sel_widget(back_btn)

        # Size the mute button for "Unmute MOD" so a set_text back to
        # "Mute MOD" leaves no dead space at the right edge.
        mute_btn = TextWidget(
            box=Box.xywh(0, btn_y, 0, 0),
            text="Unmute MOD",
            parent=d,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=self._on_toggle_mute,
            align=WidgetAlign.NONE,
            name="ethernet_mute_btn",
        )
        assert mute_btn.box
        mute_w = mute_btn.box.width
        mute_h = mute_btn.box.height
        mute_btn.set_text(mute_label)
        mute_btn.set_box(Box.xywh(DIALOG_W - 8 - mute_w, btn_y, mute_w, mute_h))
        d.add_sel_widget(mute_btn)
        self._mute_btn = mute_btn

        # Track which role holds the selection. A panel pop destroys widget
        # identity, so a re-render restores selection by role, not by ref.
        self._role_widgets = {"back": back_btn, "mute": mute_btn}

        # Keep the selection across a rebuild so ticks and the Mute action
        # do not move the focus.
        restore_target = self._role_widgets.get(self._last_selected_role or "mute", mute_btn)
        d.sel_widget(restore_target)

        self._panel = d
        self._pstack.push_panel(d)
        d.refresh()

    def _show_disconnected_dialog(self) -> None:
        self._pstack.push_panel(MessageDialog(self._pstack, "Ethernet cable disconnected.", title="Wired Connection"))

    # ----- actions -----

    # No _on_toggle_service: the Enable/Disable button is gone. The Mac menu
    # owns start and stop; this screen only renders.

    def _on_toggle_mute(self, _event: object = None, _widget: object = None) -> None:
        if self._mute.is_muted():
            self._mute.unmute()
            new_label = "Mute MOD"
        else:
            self._mute.mute()
            new_label = "Unmute MOD"
        if self._mute_btn is not None:
            self._mute_btn.set_text(new_label)
        # Refresh the Audio & MIDI toolbar tile so the muted state surfaces
        # even when the user muted via the Ethernet menu rather than the
        # Audio & MIDI menu.
        self.lcd.update_audio_midi_tile()

    def _on_back(self, _event: object = None, _widget: object = None) -> None:
        if self._panel is not None:
            old = self._panel
            self._panel = None
            self._pstack.pop_panel(old)
