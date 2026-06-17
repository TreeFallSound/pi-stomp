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
    """The Wired Connection sub-screen: status readout + enable/disable toggle.

    A single Dialog is pushed onto the panel stack; re-renders are done by
    popping and rebuilding (mirroring WifiMenu.notify_status_change). State
    comes from EthernetManager, which polls carrier + service-active on a
    background thread; this class touches the panel stack only from the UI
    thread (via handler poll-loop callbacks).
    """

    def __init__(self, lcd: "Lcd") -> None:
        self.lcd: "Lcd" = lcd
        self._panel: Optional[Dialog] = None
        # Remembered across pop/rebuild so periodic re-renders don't yank focus
        # back to the toggle button after the user has moved selection.
        # One of: 'back', 'toggle', 'mute', or None.
        self._last_selected_role: Optional[str] = None
        self._role_widgets: dict[str, object] = {}

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
            self._capture_selected_role()
            old = self._panel
            self._panel = None
            self._pstack.pop_panel(old)

        active = self._manager.service_active

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

        if active:
            toggle_label, toggle_action = "Disable", self._on_disable
        else:
            toggle_label, toggle_action = "Enable", self._on_enable

        muted = self._mute.is_muted()
        mute_label = "Unmute MOD" if muted else "Mute MOD"

        line_h = 18
        y = 4
        for label, value in rows:
            TextWidget(
                box=Box.xywh(8, y, DIALOG_W - 16, line_h),
                text=label + SPLIT + value,
                font=font,
                parent=d,
                outline=0,
                sel_width=0,
                align=WidgetAlign.NONE,
            )
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

        # Toggle sits to the right of back; mute is right-aligned. Auto-width
        # buttons (w=0) compute their box during init, so we read back .width
        # to chain placements without overlap. Rapid taps are harmless:
        # systemctl no-ops when the service is already in the target state,
        # and the bg poll flips the label within POLL_INTERVAL_S.
        assert back_btn.box
        toggle_x = back_btn.box.x0 + back_btn.box.width + 6
        toggle_btn = TextWidget(
            box=Box.xywh(toggle_x, btn_y, 0, 0),
            text=toggle_label,
            parent=d,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=toggle_action,
            align=WidgetAlign.NONE,
            name="ethernet_toggle_btn",
        )
        d.add_sel_widget(toggle_btn)

        # Build mute at x=0 first to learn its auto-computed width, then
        # reposition via set_box so its right edge sits at DIALOG_W - 8.
        # (Box.x0 setter leaves x1 alone — it shrinks rather than translates.)
        mute_btn = TextWidget(
            box=Box.xywh(0, btn_y, 0, 0),
            text=mute_label,
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
        mute_btn.set_box(Box.xywh(DIALOG_W - 8 - mute_w, btn_y, mute_w, mute_h))
        d.add_sel_widget(mute_btn)

        # Stash refs by role so re-renders can preserve selection (panel pop
        # blows away widget identity, so we track which role was selected).
        self._role_widgets = {"back": back_btn, "toggle": toggle_btn, "mute": mute_btn}

        # Restore selection from before the rebuild when possible, so periodic
        # ticks and unrelated actions (Mute) don't drag focus back to Toggle.
        restore_target = self._role_widgets.get(self._last_selected_role or "toggle", toggle_btn)
        d.sel_widget(restore_target)

        self._panel = d
        self._pstack.push_panel(d)
        d.refresh()

    def _show_disconnected_dialog(self) -> None:
        self._pstack.push_panel(MessageDialog(self._pstack, "Ethernet cable disconnected.", title="Wired Connection"))

    # ----- actions -----

    def _on_enable(self, _event: object = None, _widget: object = None) -> None:
        self._manager.start_service()
        # systemctl is fire-and-forget; the bg poll picks up the state flip
        # within POLL_INTERVAL_S and the next tick re-renders with "Disable".
        self._render()

    def _on_disable(self, _event: object = None, _widget: object = None) -> None:
        self._manager.stop_service()
        self._render()

    def _on_toggle_mute(self, _event: object = None, _widget: object = None) -> None:
        if self._mute.is_muted():
            self._mute.unmute()
        else:
            self._mute.mute()
        self._render()

    def _on_back(self, _event: object = None, _widget: object = None) -> None:
        if self._panel is not None:
            old = self._panel
            self._panel = None
            self._pstack.pop_panel(old)
