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

import common.util as util
from modalapi.wifi import (
    SavedConnection,
    ScannedNetwork,
    WifiManager,
    WifiStatus,
    parse_nmcli_error,
)
from uilib import (
    Box,
    Dialog,
    MessageDialog,
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

    def system_toggle_hotspot(self) -> None: ...


SIGNAL_FILLED = '\u25ae'   # ▮
SIGNAL_EMPTY = '\u25af'    # ▯
ACTIVE_GLYPH = '\u2714'    # ✔
SAVED_GLYPH  = '\u2022'    # •
HOTSPOT_ON = '\u25cf'      # ●
HOTSPOT_OFF = '\u25cb'     # ○
SEP = '\u00b7'             # ·
SPLIT = TextWidget.SPLIT_SEP  # left/right alignment marker for menu rows

OUT_OF_RANGE_CAP = 2


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


ConnectFn = Callable[[], Optional[bytes]]
PasswordCallback = Callable[[str], None]
MenuItem = tuple  # (label, callback, arg) or (label, callback, arg, is_active)


def signal_bars(signal: int) -> str:
    levels = max(1, min(4, (signal + 12) // 25))
    return SIGNAL_FILLED * levels + SIGNAL_EMPTY * (4 - levels)


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


class WifiMenu:
    """The wifi panel: scan, join, edit and forget networks; toggle hotspot.

    Owned by Lcd, which exposes the panel stack and a few shared affordances
    (`draw_selection_menu`, `draw_info_message`). The menu is opened via `open()`,
    typically wired to the toolbar wifi icon.
    """

    def __init__(self, lcd: 'Lcd') -> None:
        self.lcd: 'Lcd' = lcd
        self._root_menu: Optional['Menu'] = None

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
    def _pstack(self):
        return self.lcd.pstack

    # ----- entry points -----

    def open(self, event: object = None, widget: object = None) -> None:
        wifi_status = self._wifi_status
        # If wifi_supported is missing the host hasn't seen a poll yet — assume
        # supported so we don't render a stale "Disconnected" surface during
        # the cold-start window.
        supported = util.DICT_GET(wifi_status, 'wifi_supported')
        if supported is None:
            supported = True
        hotspot_active = bool(util.DICT_GET(wifi_status, 'hotspot_active'))
        active_name = util.DICT_GET(wifi_status, 'connection')

        saved_by_ssid: dict[str, list[SavedConnection]] = {}
        for c in self._wifi_manager.list_connections():
            saved_by_ssid.setdefault(c['ssid'], []).append(c)

        scanned: list[ScannedNetwork] = []
        if supported and not hotspot_active:
            self.lcd.draw_info_message("scanning...", refresh=True)
            scanned = self._wifi_manager.scan_networks()
            self.lcd.draw_info_message("", refresh=True)
        scanned_ssids = {n['ssid'] for n in scanned}

        rows, extras, nearby = self._build_rows(scanned, saved_by_ssid, scanned_ssids, active_name)
        title = self._title(wifi_status, active_name, scanned)
        items = self._build_items(rows, extras, nearby, hotspot_active)
        self._root_menu = self.lcd.draw_selection_menu(items, title, dismiss_option=True)

    def toggle_hotspot(self, _: object = None) -> None:
        self._pstack.pop_panel(None)
        self.lcd.draw_info_message("connecting...", refresh=True)
        self._host.system_toggle_hotspot()
        self.lcd.draw_info_message("", refresh=True)

    # ----- list assembly -----

    def _build_rows(self,
                    scanned: list[ScannedNetwork],
                    saved_by_ssid: dict[str, list[SavedConnection]],
                    scanned_ssids: set[str],
                    active_name: Optional[str]) -> tuple[list[Row], list[Row], list[Row]]:
        """Returns (visible_rows, extras_for_more_submenu, nearby_unsaved)."""
        rows: list[Row] = []
        nearby: list[Row] = []

        # Split in-range scan results into saved (shown in main list) and
        # unsaved (shown in "Other networks nearby..." submenu).
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

        # Saved profiles not visible in scan, sorted by recency.
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

        extras: list[Row] = []
        if len(out_of_range) > OUT_OF_RANGE_CAP:
            rows.extend(out_of_range[:OUT_OF_RANGE_CAP])
            extras = out_of_range[OUT_OF_RANGE_CAP:]
        else:
            rows.extend(out_of_range)
        return rows, extras, nearby

    def _build_items(self, rows: list[Row], extras: list[Row], nearby: list[Row],
                     hotspot_active: bool) -> list[MenuItem]:
        items: list[MenuItem] = [(self._row_label(r), self._on_network_tap, r, None, self._on_network_long_tap) for r in rows]
        if extras:
            items.append(("More saved...", self._open_more_saved, extras))
        if nearby:
            items.append(("Nearby networks...", self._open_nearby_menu, nearby))
        items.append(("Join other network...", self._open_join_dialog, None))
        items.append((
            "Hotspot Mode" + SPLIT + (HOTSPOT_ON if hotspot_active else HOTSPOT_OFF),
            self.toggle_hotspot, None))
        return items

    def _title(self, wifi_status: WifiStatus,
               active_name: Optional[str],
               scanned: list[ScannedNetwork]) -> str:
        if util.DICT_GET(wifi_status, 'hotspot_active'):
            return "WiFi " + SEP + " Hotspot"
        if active_name:
            ssid = util.DICT_GET(wifi_status, 'ssid') or active_name
            for net in scanned:
                if net['in_use'] or net['ssid'] == ssid:
                    return "WiFi %s %s %s" % (SEP, ssid, signal_bars(net['signal']))
            return "WiFi %s %s" % (SEP, ssid)
        return "WiFi " + SEP + " Disconnected"

    def _row_label(self, row: Row) -> str:
        ssid = row['ssid']
        if row.get('active'):
            prefix = ACTIVE_GLYPH + ' '
        elif row.get('saved'):
            prefix = SAVED_GLYPH + ' '
        else:
            prefix = ''
        disambiguator = row.get('disambiguator')
        left = prefix + ssid + (('  ' + disambiguator) if disambiguator else '')
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
            tap on unsaved+open     → connect_scanned
            tap on unsaved+secured  → password prompt → connect_scanned
        """
        saved = row.get('saved')
        if saved:
            if row.get('active'):
                self._open_saved_submenu(row, include_disconnect=True)
                return
            self._connect_saved(row)
            return
        if is_open_network(row.get('security')):
            self._connect_with_feedback(
                lambda: self._wifi_manager.connect_scanned(row['ssid']),
                row['ssid'])
            return
        self._open_password_prompt(row['ssid'],
            lambda psk: self._connect_with_feedback(
                lambda: self._wifi_manager.connect_scanned(row['ssid'], psk),
                row['ssid']))

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
        self.lcd.draw_selection_menu(items, "Nearby Networks", dismiss_option=True)

    def _open_more_saved(self, extras: list[Row]) -> None:
        items: list[MenuItem] = [(self._row_label(r), self._on_network_tap, r, None, self._on_network_long_tap) for r in extras]
        self.lcd.draw_selection_menu(items, "Saved Networks", dismiss_option=True)

    def _connect_saved(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        name = profile['name']
        ssid = row['ssid']
        self._pstack.pop_panel(None)
        self.lcd.draw_info_message("connecting to %s..." % ssid, refresh=True)
        err = self._wifi_manager.connect_saved(name)
        self.lcd.draw_info_message("", refresh=True)
        if err is None:
            return
        # macOS-style: if the saved PSK is wrong, prompt for a new one and
        # retry via replace_psk (which validates by reactivating).
        reason = parse_nmcli_error(err)
        if 'auth failed' in reason or 'wrong password' in reason:
            self._open_password_prompt(ssid,
                lambda psk: self._connect_with_feedback(
                    lambda: self._wifi_manager.replace_psk(name, psk),
                    ssid))
            return
        self._pstack.push_panel(
            MessageDialog(self._pstack, reason, title="Couldn't connect"))

    def _disconnect(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        self._pstack.pop_panel(None)
        err = self._wifi_manager.disconnect(profile['name'])
        if err is not None:
            self._pstack.push_panel(
                MessageDialog(self._pstack, parse_nmcli_error(err), title="Couldn't disconnect"))

    def _connect_with_feedback(self, connect_fn: ConnectFn, ssid: str) -> None:
        self._pstack.pop_panel(None)
        self.lcd.draw_info_message("connecting to %s..." % ssid, refresh=True)
        err = connect_fn()
        self.lcd.draw_info_message("", refresh=True)
        if err is None:
            return
        self._pstack.push_panel(
            MessageDialog(self._pstack, parse_nmcli_error(err), title="Couldn't connect"))

    def _open_replace_psk_dialog(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        self._open_password_prompt(row['ssid'],
            lambda psk: self._connect_with_feedback(
                lambda: self._wifi_manager.replace_psk(profile['name'], psk),
                row['ssid']))

    def _forget(self, row: Row) -> None:
        profile = row['profile']
        assert profile is not None
        result = self._wifi_manager.delete_connection(profile['name'])
        if result is not None:
            self._pstack.push_panel(
                MessageDialog(self._pstack, parse_nmcli_error(result), title="Error"))
            return
        self._pstack.pop_panel(None)
        if self._root_menu is not None:
            self._pstack.pop_panel(self._root_menu)
        self.open()

    # ----- dialogs -----

    def _open_password_prompt(self, ssid: str, on_submit: PasswordCallback) -> None:
        d = Dialog(width=240, height=110, auto_destroy=True, title='Password for %s' % ssid)
        pw = TextWidget(box=Box.xywh(0, 0, 169, 0), text='', prompt='Passwd :', parent=d,
                        outline=1, sel_width=3, outline_radius=5,
                        align=WidgetAlign.NONE, name='pw_field',
                        edit_message='Password')
        d.add_sel_widget(pw)
        cancel = TextWidget(box=Box.xywh(0, 60, 0, 0), text='Cancel', parent=d,
                            outline=1, sel_width=3, outline_radius=5,
                            action=lambda x, y: self._pstack.pop_panel(d),
                            align=WidgetAlign.NONE, name='cancel_btn')
        d.add_sel_widget(cancel)

        def submit(_event, _button):
            psk = pw.text
            if not psk:
                return
            self._pstack.pop_panel(d)
            on_submit(psk)

        ok = TextWidget(box=Box.xywh(80, 60, 0, 0), text='Ok', parent=d,
                        outline=1, sel_width=3, outline_radius=5,
                        action=submit, align=WidgetAlign.NONE, name='ok_btn')
        d.add_sel_widget(ok)
        self._pstack.push_panel(d)
        d.refresh()

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
            self._connect_with_feedback(
                lambda: self._wifi_manager.connect_scanned(ssid, psk or None),
                ssid)

        ok = TextWidget(box=Box.xywh(80, 90, 0, 0), text='Ok', parent=d,
                        outline=1, sel_width=3, outline_radius=5,
                        action=submit, align=WidgetAlign.NONE, name='ok_btn')
        d.add_sel_widget(ok)
        self._pstack.push_panel(d)
        d.refresh()
