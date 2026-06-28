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
        # Refs to widgets that mutate in place — reset on every _render().
        # tick() updates the xrun rows via set_text(); the action handlers
        # update their own button label the same way. None of these paths
        # rebuild the dialog, so the buttons don't vanish under the user's
        # finger and the SPI blit stays a precise clip.
        self._xrun_widgets: list[TextWidget] = []
        self._toggle_btn: Optional[TextWidget] = None
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
        """Update the xrun counters while we're on top, without rebuilding
        the dialog. The rest of the rows and the buttons are static between
        state flips; mutating them via set_text() takes the per-widget
        dirty-rect path so the buttons stay put (no reblit under the user's
        finger, no full-screen redraw on the SPI bus)."""
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

        # Old widgets were just destroyed — drop our refs so tick() / actions
        # don't try to mutate zombies if a render races a poll.
        self._xrun_widgets = []
        self._toggle_btn = None
        self._mute_btn = None

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

        muted = self._mute.is_muted()
        toggle_label = "Disable" if active else "Enable"
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

        # Toggle sits to the right of back; constructed with the wider of the
        # two labels so the box is the same size in both states. Without
        # this, swapping "Enable"→"Disable" via set_text() would clip the
        # trailing "e" inside the original (narrower) box.
        assert back_btn.box
        toggle_x = back_btn.box.x0 + back_btn.box.width + 6
        toggle_btn = TextWidget(
            box=Box.xywh(toggle_x, btn_y, 0, 0),
            text="Disable",
            parent=d,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=self._on_toggle_service,
            align=WidgetAlign.NONE,
            name="ethernet_toggle_btn",
        )
        toggle_btn.set_text(toggle_label)
        d.add_sel_widget(toggle_btn)
        self._toggle_btn = toggle_btn

        # Mute button: same trick — size to fit "Unmute MOD" so a set_text
        # back to "Mute MOD" doesn't leave dead space at the right edge.
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

    def _on_toggle_service(self, _event: object = None, _widget: object = None) -> None:
        # Optimistic update: show the *new* state immediately, before the
        # background poll observes systemctl's effect. The bg poll's
        # notify_change() will re-render the dialog (full rebuild is needed
        # there anyway, because the row *set* changes when service_active
        # flips) and reconcile any drift.
        if self._manager.service_active:
            self._manager.stop_service()
            new_label = "Enable"
        else:
            self._manager.start_service()
            new_label = "Disable"
        if self._toggle_btn is not None:
            self._toggle_btn.set_text(new_label)

    def _on_toggle_mute(self, _event: object = None, _widget: object = None) -> None:
        if self._mute.is_muted():
            self._mute.unmute()
            new_label = "Mute MOD"
        else:
            self._mute.mute()
            new_label = "Unmute MOD"
        if self._mute_btn is not None:
            self._mute_btn.set_text(new_label)

    def _on_back(self, _event: object = None, _widget: object = None) -> None:
        if self._panel is not None:
            old = self._panel
            self._panel = None
            self._pstack.pop_panel(old)
