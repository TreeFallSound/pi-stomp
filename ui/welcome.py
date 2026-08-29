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

import os
import time

import pygame
import qrcode
import qrcode.constants

from uilib.box import Box
from uilib.config import Config
from uilib.image import ImageWidget
from uilib.misc import get_text_size, TextHAlign
from uilib.panel import Panel
from uilib.text import Button, TextWidget
import common.token as Token

_W, _H = 320, 240
BTN_GAP, BTN_H = 2, 28
_BTN_Y = _H - BTN_H - BTN_GAP
_BOX = 160
_LEFT_X = 10
_QR_SZ = 140
_BOX_Y = (_BTN_Y - BTN_GAP - _BOX) // 2
_LOGO_Y = _BOX_Y + 8
_QR_X = _W - _QR_SZ - 4
_QR_Y = _BOX_Y + (_BOX - _QR_SZ) // 2 + 10
_BG = (255, 255, 255)
_FG = (48, 48, 48)
_QR_COLOUR = (0, 0, 0)
_LIGHT = (120, 120, 120)
_DISABLED = (170, 170, 170)
_RESTORE_POLL_S = 1.0
QR_TEXT = "treefallsound.github.io/pistomp-manual/"


def _make_qr_surface() -> pygame.Surface:
    qr = qrcode.QRCode(box_size=4, border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(QR_TEXT)
    qr.make(fit=True)
    from PIL import Image as PILImage

    img: PILImage.Image = qr.make_image(fill_color=_QR_COLOUR, back_color=_BG)  # pyright: ignore[reportAssignmentType]
    return pygame.image.frombuffer(img.tobytes(), img.size, "RGB")


class WelcomePanel(Panel):
    def __init__(self, handler):
        super().__init__(
            box=Box.xywh(0, 0, _W, _H),
            auto_destroy=True,
            no_dim=True,
            opaque=True,
            persist_on_board_change=True,
            bkgnd_color=_BG,
            fgnd_color=_FG,
            sel_color=(255, 0, 0),
        )
        self._handler = handler

        cfg = Config()
        btn_font = cfg.get_font("default")
        _, btn_text_h = get_text_size("Start", btn_font)
        btn_v_margin = max(0, (BTN_H - btn_text_h) // 2)
        btn_w = (320 - 4 * BTN_GAP) // 3

        # Left box: TFS logo, pi-Stomp logo, version
        imagedir = os.path.join(handler.homedir, "images")
        ImageWidget(
            os.path.join(imagedir, "treefallsound-logo.png"), box=Box.xywh(_LEFT_X, _LOGO_Y, _BOX, 78), parent=self
        )
        ImageWidget(
            os.path.join(imagedir, "pistomp-logo.png"), box=Box.xywh(_LEFT_X, _LOGO_Y + 80, _BOX, 56), parent=self
        )
        TextWidget(
            box=Box.xywh(_LEFT_X + 80, _LOGO_Y + 112, 52, 14),
            text=f"v{handler.software_version or ''}",
            font=cfg.get_font("tiny"),
            fgnd_color=_LIGHT,
            outline=0,
            sel_width=0,
            parent=self,
        )

        # Right box: QR code
        ImageWidget(_make_qr_surface(), box=Box.xywh(_QR_X, _QR_Y, _QR_SZ, _QR_SZ), parent=self)
        TextWidget(
            box=Box.xywh(_QR_X, _QR_Y - 8, _QR_SZ, 16),
            text="USER GUIDE",
            font=cfg.get_font("tiny"),
            fgnd_color=_FG,
            text_halign=TextHAlign.CENTRE,
            outline=0,
            sel_width=0,
            parent=self,
        )

        # Bottom row: Start | Restore | Setup...
        self._btn_start = Button(
            box=Box.xywh(BTN_GAP, _BTN_Y, btn_w, BTN_H),
            text="Start",
            font=btn_font,
            v_margin=btn_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_start(),
        )
        self._btn_restore = Button(
            box=Box.xywh(BTN_GAP * 2 + btn_w, _BTN_Y, btn_w, BTN_H),
            text="Restore",
            font=btn_font,
            v_margin=btn_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_restore(),
        )
        self._btn_setup = Button(
            box=Box.xywh(BTN_GAP * 3 + btn_w * 2, _BTN_Y, btn_w, BTN_H),
            text="Setup\n...",
            font=btn_font,
            v_margin=btn_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_setup(),
        )

        self.add_sel_widget(self._btn_start)
        self.add_sel_widget(self._btn_restore)
        self.add_sel_widget(self._btn_setup)

        self._restore_enabled = True
        self._restore_checked_at = 0.0
        self._sync_restore()

    def tick(self) -> None:
        # Nothing tells us that a drive appeared. The user plugs one in while this
        # panel is on screen, thus poll.
        if time.monotonic() - self._restore_checked_at >= _RESTORE_POLL_S:
            self._sync_restore()

    def _sync_restore(self) -> None:
        self._restore_checked_at = time.monotonic()
        enabled = self._handler.usb_restore_available
        if enabled == self._restore_enabled:
            return
        self._restore_enabled = enabled
        self._btn_restore.set_foreground(_FG if enabled else _DISABLED)
        if enabled:
            # Remove and re-add Setup to keep NAV in left-to-right button order.
            self.del_sel_widget(self._btn_setup)
            self.add_sel_widget(self._btn_restore)
            self.add_sel_widget(self._btn_setup)
        else:
            self.del_sel_widget(self._btn_restore)

    def _on_start(self):
        self._handler.settings.set_setting(Token.WELCOME_SEEN, True)
        self._handler.lcd.pstack.pop_panel(self)

    def _on_restore(self):
        self._handler.user_restore_data(None, on_success=self._on_restore_success)

    def _on_restore_success(self):
        self._handler.settings.load_settings()
        self._handler.settings.set_setting(Token.WELCOME_SEEN, True)
        self._handler.lcd.pstack.pop_panel(self)

    def _on_setup(self):
        if self._handler.recovery_available:
            self._handler.settings.set_setting(Token.WELCOME_SEEN, True)
            self._handler.system_menu_recovery_mode(None)
        else:
            self._handler.lcd.draw_message_dialog("Recovery not available")
