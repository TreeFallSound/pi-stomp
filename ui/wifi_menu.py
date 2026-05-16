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

import time
from typing import TYPE_CHECKING, Callable, NotRequired, Optional, Protocol, TypedDict, cast

from PIL import ImageFont

import common.util as util
from modalapi.wifi import (
    ConnectSavedCmd,
    ConnectScannedCmd,
    DisconnectCmd,
    ForgetCmd,
    ReplacePskCmd,
    SavedConnection,
    ScanCmd,
    ScannedNetwork,
    ToggleHotspotCmd,
    WifiManager,
    WifiStatus,
    parse_nmcli_error,
)
from uilib import (
    Box,
    Config,
    Dialog,
    FontWithGlyphs,
    InputEvent,
    LetterSelector,
    MessageDialog,
    PillGlyph,
    RoundedPanel,
    SignalBarsGlyph,
    TextWidget,
    WidgetAlign,
)
from uilib.menu import Menu

if TYPE_CHECKING:
    from pistomp.lcd320x240 import Lcd


class _WifiHost(Protocol):
    """The handler-side surface WifiMenu needs to do its job.

    The concrete handler (`modalapi.modhandler.ModHandler`) satisfies this structurally.
    """
    wifi_manager: WifiManager
    wifi_status: Optional[WifiStatus]


ACTIVE_GLYPH = '\u2714'    # ✔
PUBLIC_GLYPH = '\ue001'    # PUA sentinel — rendered as pill badge by FontWithGlyphs
SIGNAL_GLYPHS = ['\ue010', '\ue011', '\ue012', '\ue013', '\ue014']  # 0..4 bars
SEP = '\u00b7'             # ·
SPLIT = TextWidget.SPLIT_SEP  # left/right alignment marker for menu rows

class Row(TypedDict):
    """A single network line in the wifi menu — saved profile, in-range network, or both.

    `signal`, `security`, and `profile` are present but may be None (e.g. saved-but-out-of-range
    has no signal/security; in-range-but-unsaved has no profile)."""
    ssid: str
    signal: Optional[int]
    security: Optional[str]
    saved: bool
    profile: Optional[SavedConnection]
    active: bool
    disambiguator: NotRequired[str]


PasswordCallback = Callable[[str], None]
MenuItem = tuple  # (label, callback, arg) or (label, callback, arg, is_active)


class _PassphraseEditor(RoundedPanel):
    """Single-panel passphrase entry that opens directly with the letter selector.

    Skips the intermediate form dialog: Cancel dismisses cleanly; OK with a
    non-empty passphrase dismisses and calls on_submit.
    """

    def __init__(self, ssid: str, pstack, on_submit: PasswordCallback) -> None:
        self._pstack = pstack
        self._on_submit = on_submit
        self._curline = ''

        font = ImageFont.truetype("DejaVuSans.ttf", 18)
        box = Box(0, 0, 300, 80)
        box = box.centre(pstack.box)
        super().__init__(box=box, parent=pstack, auto_destroy=True)
        self.set_outline(2, (255, 255, 255))

        TextWidget(box=Box.xywh(10, 8, 280, 0), text='Password for ' + ssid,
                   font=font, parent=self)
        self._edit = TextWidget(box=Box.xywh(10, 30, 280, 20),
                                text='\u2588', font=font, parent=self)
        self._edit.set_background((64, 64, 64))
        selector = LetterSelector(box=Box.xywh(10, 52, 280, 22), font=font,
                                  parent=self, action=self._on_letter)
        self.add_sel_widget(selector)
        pstack.push_panel(self)
        self.refresh()

    def _on_letter(self, event: InputEvent, data: object) -> None:
        if event == InputEvent.CANCEL:
            self._pstack.pop_panel(self)
            return
        if event == InputEvent.OK:
            if self._curline:
                self._pstack.pop_panel(self)
                self._on_submit(self._curline)
            return
        if event == InputEvent.CLEAR:
            self._curline = ''
        elif event == InputEvent.BACKSPACE:
            self._curline = self._curline[:-1]
        elif event == InputEvent.LETTER:
            self._curline += str(data)
        self._edit.set_text(self._curline + '\u2588')


def signal_bars(signal: int) -> str:
    levels = max(1, min(4, (signal + 12) // 25))
    return SIGNAL_GLYPHS[levels]


def format_age(ts: Optional[int]) -> Optional[str]:
    if not ts:
        return None
    age = max(0, int(time.time()) - int(ts))
    if age < 60:
        return "now"
    if age < 3600:
        return "%dm ago" % (age // 60)
    if age < 86400:
        return "%dh ago" % (age // 3600)
    return "%dd ago" % (age // 86400)


def is_open_network(security: Optional[str]) -> bool:
    return not security or security == '--'


def _make_badge_font(base_name: str = 'default') -> FontWithGlyphs:
    base = Config().get_font(base_name)
    assert base is not None, f"{base_name} font not configured"
    glyphs: dict[str, object] = {PUBLIC_GLYPH: PillGlyph('P')}
    for level, ch in enumerate(SIGNAL_GLYPHS):
        glyphs[ch] = SignalBarsGlyph(level)
    return FontWithGlyphs(base, glyphs)  # type: ignore[arg-type]


class WifiMenu:
    """The wifi panel: scan, join, edit and forget networks; toggle hotspot.

    Owned by Lcd, which exposes the panel stack and `draw_selection_menu`.
    Reads cached state from WifiManager; submits writes to its CommandQueue.
    """

    def __init__(self, lcd: 'Lcd') -> None:
        self.lcd: 'Lcd' = lcd
        self._root_menu: Optional['Menu'] = None
        self._cached_scanned: list[ScannedNetwork] = []

    @property
    def _host(self) -> _WifiHost:
        h = self.lcd.handler
        assert h is not None, "WifiMenu requires lcd.handler to be set"
        return cast(_WifiHost, h)

    @property
    def _wifi_manager(self) -> WifiManager:
        return self._host.wifi_manager

    @property
    def _wifi_status(self) -> WifiStatus:
        return self._host.wifi_status or {}

    @property
    def _saved_by_ssid(self) -> dict[str, list[SavedConnection]]:
        by_ssid: dict[str, list[SavedConnection]] = {}
        for c in self._wifi_manager.get_cached_saved():
            by_ssid.setdefault(c['ssid'], []).append(c)
        return by_ssid

    @property
    def _pstack(self):
        return self.lcd.pstack

    # ----- entry points -----

    def open(self, event: object = None, widget: object = None) -> None:
        self._render_root_menu()
        self._wifi_manager.queue.submit_scan(ScanCmd(), self._on_scan)

    def _on_scan(self, networks: list[ScannedNetwork]) -> None:
        if isinstance(networks, Exception):
            return
        self._cached_scanned = networks
        if self._root_menu is not None and self._pstack.current is self._root_menu:
            old = self._root_menu
            self._root_menu = None
            self._pstack.pop_panel(old)
            self._render_root_menu()

    def _render_root_menu(self) -> None:
        wifi_status = self._wifi_status
        hotspot_active = bool(util.DICT_GET(wifi_status, 'hotspot_active'))
        active_name = util.DICT_GET(wifi_status, 'connection')
        scanned = self._cached_scanned
        saved_by_ssid = self._saved_by_ssid
        scanned_ssids = {n['ssid'] for n in scanned}
        rows, nearby = self._build_rows(scanned, saved_by_ssid, scanned_ssids, active_name)
        title = self._title(wifi_status, active_name, scanned)
        items = self._build_items(rows, nearby, hotspot_active)
        self._root_menu = self.lcd.draw_selection_menu(
            items, title, dismiss_option=True,
            font=_make_badge_font())

    def notify_status_change(self) -> None:
        """Called by the handler after wifi_status is updated.

        Rebuilds the root menu in place so hotspot/active indicators stay
        current. No-op if the wifi menu isn't the top panel (don't disrupt
        password prompts, submenus, or unrelated UI).
        """
        if self._root_menu is None or self._pstack.current is not self._root_menu:
            return
        old = self._root_menu
        self._root_menu = None
        self._pstack.pop_panel(old)
        self._render_root_menu()
        self._wifi_manager.queue.submit_scan(ScanCmd(), self._on_scan)

    def toggle_hotspot(self, _: object = None) -> None:
        was_active = bool(util.DICT_GET(self._wifi_status, 'hotspot_active'))
        self._pstack.pop_panel(None)
        self._wifi_manager.queue.submit(ToggleHotspotCmd(was_active), self._on_toggle_done)

    def _on_toggle_done(self, err: Optional[bytes]) -> None:
        if isinstance(err, Exception):
            err = str(err).encode('utf-8')
        if err is not None:
            self._pstack.push_panel(
                MessageDialog(self._pstack, parse_nmcli_error(err), title="Couldn't reconnect"))

    # ----- list assembly -----

    def _build_rows(self,
                    scanned: list[ScannedNetwork],
                    saved_by_ssid: dict[str, list[SavedConnection]],
                    scanned_ssids: set[str],
                    active_name: Optional[str]) -> tuple[list[Row], list[Row]]:
        """Returns (visible_rows, nearby_unsaved)."""
        rows: list[Row] = []
        nearby: list[Row] = []

        for net in scanned:
            profiles = saved_by_ssid.get(net['ssid'], [])
            saved_profile = self._pick_profile(profiles, active_name)
            row: Row = {
                'ssid': net['ssid'],
                'signal': net['signal'],
                'security': net['security'],
                'saved': saved_profile is not None,
                'profile': saved_profile,
                'active': saved_profile is not None and saved_profile['name'] == active_name,
            }
            self._maybe_disambiguate(row, profiles)
            if saved_profile is not None:
                rows.append(row)
            else:
                nearby.append(row)
        rows.sort(key=lambda r: (not r['active'], -(r['signal'] or 0)))
        nearby.sort(key=lambda r: -(r['signal'] or 0))

        out_of_range: list[Row] = []
        for ssid, profiles in saved_by_ssid.items():
            if ssid in scanned_ssids:
                continue
            for profile in profiles:
                ooo_row: Row = {
                    'ssid': ssid,
                    'signal': None,
                    'security': None,
                    'saved': True,
                    'profile': profile,
                    'active': profile['name'] == active_name,
                }
                self._maybe_disambiguate(ooo_row, profiles)
                out_of_range.append(ooo_row)
        out_of_range.sort(key=lambda r: -(r['profile']['timestamp'] if r['profile'] else 0))
        rows.extend(out_of_range)
        return rows, nearby

    def _build_items(self, rows: list[Row], nearby: list[Row],
                     hotspot_active: bool) -> list[MenuItem]:
        items: list[MenuItem] = [(self._row_label(r), self._on_network_tap, r, None, self._on_network_long_tap) for r in rows]
        if nearby:
            items.append(("Nearby networks...", self._open_nearby_menu, nearby))
        items.append(("Join other network...", self._open_join_dialog, None))
        hotspot_label = "Disable Hotspot Mode" if hotspot_active else "Switch to Hotspot Mode"
        items.append((hotspot_label, self.toggle_hotspot, None))
        return items

    def _title(self, wifi_status: WifiStatus,
               active_name: Optional[str],
               scanned: list[ScannedNetwork]) -> str:
        if util.DICT_GET(wifi_status, 'hotspot_active'):
            return "WiFi " + SEP + " Hotspot"
        if active_name:
            ssid = util.DICT_GET(wifi_status, 'ssid') or active_name
            return "WiFi %s %s" % (SEP, ssid)
        return "WiFi " + SEP + " Disconnected"

    def _row_label(self, row: Row) -> str:
        ssid = row['ssid']
        disambiguator = row.get('disambiguator')
        badge = (' ' + PUBLIC_GLYPH) if (not row.get('saved') and is_open_network(row.get('security'))) else ''
        active_mark = (' ' + ACTIVE_GLYPH) if row.get('active') else ''
        left = ssid + (('  ' + disambiguator) if disambiguator else '') + badge + active_mark
        right = signal_bars(row['signal']) if row.get('signal') is not None else ''
        return left + SPLIT + right

    @staticmethod
    def _pick_profile(profiles: list[SavedConnection],
                      active_name: Optional[str]) -> Optional[SavedConnection]:
        if not profiles:
            return None
        for p in profiles:
            if p['name'] == active_name:
                return p
        return max(profiles, key=lambda p: p['timestamp'] or 0)

    @staticmethod
    def _maybe_disambiguate(row: Row, profiles: list[SavedConnection]) -> None:
        profile = row.get('profile')
        if row.get('saved') and len(profiles) > 1 and profile is not None:
            age = format_age(profile.get('timestamp'))
            if age:
                row['disambiguator'] = SEP + ' ' + age

    # ----- per-network actions -----

    def _on_network_tap(self, row: Row) -> None:
        """Root-menu row tap. Routes by row state:

            tap on saved+active     → Disconnect/Forget/Replace pw submenu
            tap on saved+non-active → connect_saved (no prompt — we have the PSK)
            tap on unsaved           → _connect_scanned_flow (stays in nearby on failure)
        """
        saved = row.get('saved')
        if saved:
            if row.get('active'):
                self._open_saved_submenu(row, include_disconnect=True)
                return
            self._connect_saved(row)
            return
        self._connect_scanned_flow(row)

    def _connect_scanned_flow(self, row: Row) -> None:
        """Connect to a scanned (unsaved) network. One attempt — if it fails,
        show the error. The user can re-try via the menu."""
        ssid = row['ssid']

        def attempt(psk: Optional[str]) -> None:
            self._pstack.pop_panel(None)
            self._wifi_manager.queue.submit(
                ConnectScannedCmd(ssid=ssid, psk=psk), self._on_op_done)

        if is_open_network(row.get('security')):
            attempt(None)
        else:
            self._open_password_prompt(ssid, attempt)

    def _on_network_long_tap(self, row: Row) -> None:
        """Long-press on a network row → saved-network submenu."""
        if row.get('saved'):
            self._open_saved_submenu(row, include_disconnect=bool(row.get('active')))

    def _open_saved_submenu(self, row: Row, include_disconnect: bool = False) -> None:
        items: list[MenuItem] = []
        if include_disconnect:
            items.append(("Disconnect", self._disconnect, row))
        items.append(("Replace password", self._open_replace_psk_dialog, row))
        items.append(("Forget", self._forget, row))
        self.lcd.draw_selection_menu(items, row['ssid'], dismiss_option=True)

    def _open_nearby_menu(self, nearby: list[Row]) -> None:
        items: list[MenuItem] = [(self._row_label(r), self._on_network_tap, r) for r in nearby]
        self.lcd.draw_selection_menu(items, "Nearby Networks", dismiss_option=True,
                                     font=_make_badge_font())

    def _on_op_done(self, err: Optional[bytes]) -> None:
        if isinstance(err, Exception):
            err = str(err).encode('utf-8')
        if err is not None:
            self._pstack.push_panel(
                MessageDialog(self._pstack, parse_nmcli_error(err), title="Couldn't connect"))

    def _connect_saved(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        self._pstack.pop_panel(None)
        self._wifi_manager.queue.submit(
            ConnectSavedCmd(name=profile['name'], ssid=row['ssid']),
            self._on_op_done)

    def _disconnect(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        self._pstack.pop_panel(None)
        self._wifi_manager.queue.submit(
            DisconnectCmd(name=profile['name'], ssid=row['ssid']),
            self._on_disconnect_done)

    def _on_disconnect_done(self, err: Optional[bytes]) -> None:
        if isinstance(err, Exception):
            err = str(err).encode('utf-8')
        if err is not None:
            self._pstack.push_panel(
                MessageDialog(self._pstack, parse_nmcli_error(err), title="Couldn't disconnect"))

    def _open_replace_psk_dialog(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        self._open_password_prompt(row['ssid'],
            lambda psk: self._submit_replace_psk(profile, row['ssid'], psk))

    def _submit_replace_psk(self, profile: SavedConnection, ssid: str, psk: str) -> None:
        self._pstack.pop_panel(None)
        self._wifi_manager.queue.submit(
            ReplacePskCmd(name=profile['name'], ssid=ssid, psk=psk),
            self._on_op_done)

    def _forget(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        self._wifi_manager.queue.submit(
            ForgetCmd(name=profile['name'], ssid=row['ssid']),
            self._on_forget_done)

    def _on_forget_done(self, err: Optional[bytes]) -> None:
        if isinstance(err, Exception):
            err = str(err).encode('utf-8')
        if err is not None:
            self._pstack.push_panel(
                MessageDialog(self._pstack, parse_nmcli_error(err), title="Error"))
            return
        self._pstack.pop_panel(None)
        if self._root_menu is not None:
            self._pstack.pop_panel(self._root_menu)
            self._root_menu = None
        self.open()

    # ----- dialogs -----

    def _open_password_prompt(self, ssid: str, on_submit: PasswordCallback) -> None:
        _PassphraseEditor(ssid, self._pstack, on_submit)

    def _open_join_dialog(self, _: object = None) -> None:
        d = Dialog(width=240, height=120, auto_destroy=True, title='Join other network')
        ssid_w = TextWidget(box=Box.xywh(0, 0, 190, 0), text='', prompt='SSID :', parent=d,
                            outline=1, sel_width=3, outline_radius=5,
                            align=WidgetAlign.NONE, name='ssid_field',
                            edit_message='WiFi SSID')
        d.add_sel_widget(ssid_w)
        pw_w = TextWidget(box=Box.xywh(0, 30, 169, 0), text='', prompt='Passwd :', parent=d,
                          outline=1, sel_width=3, outline_radius=5,
                          align=WidgetAlign.NONE, name='pw_field',
                          edit_message='Password')
        d.add_sel_widget(pw_w)

        cancel = TextWidget(box=Box.xywh(0, 90, 0, 0), text='Cancel', parent=d,
                            outline=1, sel_width=3, outline_radius=5,
                            action=lambda x, y: self._pstack.pop_panel(d),
                            align=WidgetAlign.NONE, name='cancel_btn')
        d.add_sel_widget(cancel)

        def submit(_event, _button):
            ssid = ssid_w.text
            psk = pw_w.text
            if not ssid:
                return
            self._pstack.pop_panel(d)
            self._wifi_manager.queue.submit(
                ConnectScannedCmd(ssid=ssid, psk=psk or None),
                self._on_op_done)

        ok = TextWidget(box=Box.xywh(80, 90, 0, 0), text='Ok', parent=d,
                        outline=1, sel_width=3, outline_radius=5,
                        action=submit, align=WidgetAlign.NONE, name='ok_btn')
        d.add_sel_widget(ok)
        self._pstack.push_panel(d)
        d.refresh()
