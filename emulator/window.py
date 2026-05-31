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

"""EmulatorWindow — pygame window that shows the 320×240 LCD (2× scaled)
alongside clickable representations of the physical controls.

Layout (total 940 × 500):
  ┌────────────────────────┬────────────────────────┐
  │  LCD 640×480 (2×)      │  Controls panel 300px  │
  └────────────────────────┴────────────────────────┘

Keyboard shortcuts (availability depends on hardware version)
  ← / →          nav encoder left / right
  Enter / Space  nav encoder press (click)
  L              nav encoder long-press
  1 / 2 / 3 / 4  footswitch 1 / 2 / 3 / 4
  Q / W          tweak enc 1 left / right   E = press
  A / S          tweak enc 2 left / right   D = press
  Z / X          volume enc left / right
  ↑ / ↓          expression pedal +/-
  Esc            quit
"""

import os
import pygame
import pygame._freetype as _freetype
import pistomp.switchstate as switchstate

_FONTS_DIR  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
_FONT_MONO      = os.path.join(_FONTS_DIR, "DejaVuSansMono.ttf")
_FONT_MONO_BOLD = os.path.join(_FONTS_DIR, "DejaVuSansMono-Bold.ttf")


class _FTFont:
    """Wraps pygame._freetype.Font to match the pygame.font.Font render API."""

    def __init__(self, path, size):
        self._ft = _freetype.Font(path, size)

    def render(self, text, antialias, color):
        surf, _ = self._ft.render(text, color)
        return surf

# ---- dimensions (per-instance; these module-level values are defaults) ------
CTRL_W          = 300
_TARGET_H       = 480   # desired display area height — scale is computed to match

# ---- colours ----------------------------------------------------------------
BG              = (30, 30, 30)
PANEL_BG        = (45, 45, 45)
BTN_IDLE        = (80, 80, 80)
BTN_HOVER       = (120, 120, 120)
BTN_ACTIVE      = (200, 200, 200)
FS_ON           = (0, 200, 80)
FS_OFF          = (80, 80, 80)
TEXT_COLOR      = (220, 220, 220)
DIM_TEXT        = (130, 130, 130)
SLIDER_BG       = (60, 60, 60)
SLIDER_FG       = (0, 160, 200)


class _Label:
    """Non-interactive text drawn on the controls panel."""

    def __init__(self, pos, text, font, color=DIM_TEXT):
        self._surf = font.render(text, True, color)
        self._pos = pos

    def draw(self, surf):
        surf.blit(self._surf, self._pos)


class _Btn:
    """Simple clickable rectangle."""

    def __init__(self, rect, label, action, font):
        self.rect   = pygame.Rect(rect)
        self.label  = label
        self.action = action
        self.font   = font
        self._hover = False

    def draw(self, surf, active=False):
        color = BTN_ACTIVE if active else (BTN_HOVER if self._hover else BTN_IDLE)
        pygame.draw.rect(surf, color, self.rect, border_radius=4)
        text = self.font.render(self.label, True, (0, 0, 0) if active else TEXT_COLOR)
        tr = text.get_rect(center=self.rect.center)
        surf.blit(text, tr)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.action()


class EmulatorWindow:

    def __init__(self, hardware):
        self.hw = hardware
        self.running = True

        lcd_w = hardware.lcd_pygame.width
        lcd_h = hardware.lcd_pygame.height
        scale = max(1, _TARGET_H // lcd_h)
        self.lcd_disp_w = lcd_w * scale
        self.lcd_disp_h = lcd_h * scale
        self.win_w = self.lcd_disp_w + CTRL_W
        self.win_h = self.lcd_disp_h
        self.ctrl_x = self.lcd_disp_w + 10

        self.screen = pygame.display.set_mode((self.win_w, self.win_h))
        pygame.key.set_repeat(300, 50)
        version_label = getattr(hardware, 'VERSION_LABEL', '')
        title = "pi-Stomp Emulator (%s)" % version_label if version_label else "pi-Stomp Emulator"
        pygame.display.set_caption(title)

        self.font_sm  = _FTFont(_FONT_MONO,      13)
        self.font_med = _FTFont(_FONT_MONO_BOLD, 15)
        self.font_hdr = _FTFont(_FONT_MONO_BOLD, 14)

        self._exp_value = 64   # 0-127 MIDI value for expression pedal
        self._exp_dragging = False

        self._buttons: list[_Btn] = []
        self._fs_btns: list[tuple[_Btn, int]] = []
        self._labels: list[_Label] = []
        self._build_ui()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_ui(self):
        y = 15
        bw, bh = 60, 30   # default button size

        # --- Footswitches ----------------------------------------------------
        num_fs = len(self.hw.footswitches)
        fs_spacing = min(68, (CTRL_W - 20) // max(num_fs, 1))
        for i, fs in enumerate(self.hw.footswitches):
            x = self.ctrl_x + 5 + i * fs_spacing
            idx = i
            btn = _Btn((x, y, 56, 46),
                       "FS%d" % (i + 1),
                       lambda fs=fs: fs.press(),
                       self.font_med)
            self._buttons.append(btn)
            self._fs_btns.append((btn, idx))

        y += 60

        # --- Encoders --------------------------------------------------------
        enc_y = y
        for enc in self.hw.encoders:
            label = self._enc_label(enc)
            enc_y = self._add_encoder_row(enc, label, enc_y)
            enc_y += 8

        self._exp_slider_y = enc_y + 10
        self._exp_slider_rect = pygame.Rect(
            self.ctrl_x + 5, self._exp_slider_y + 16, CTRL_W - 20, 12)

    def _enc_label(self, enc):
        if hasattr(enc, 'midi_CC') and enc.midi_CC is not None:
            return "Enc %s (CC%d)" % (enc.id, enc.midi_CC)
        if getattr(enc, 'type', None) == 'VOLUME':
            return "Vol (enc %s)" % enc.id
        if getattr(enc, 'label', None) is not None:
            return enc.label
        return "Nav"

    def _add_encoder_row(self, enc, label, y):
        self._labels.append(_Label((self.ctrl_x + 5, y), label, self.font_sm))
        y += 15

        bw, bh = 38, 28
        has_press = getattr(enc, 'press_callback', None) is not None

        left_x  = self.ctrl_x + 5
        mid_x   = left_x + bw + 4
        right_x = mid_x + (bw + 4 if has_press else 0)

        self._buttons.append(_Btn(
            (left_x, y, bw, bh), "◄",
            lambda e=enc: e.step(-1), self.font_med))

        if has_press:
            self._buttons.append(_Btn(
                (mid_x, y, bw, bh), "●",
                lambda e=enc: e.press(switchstate.Value.RELEASED),
                self.font_med))
            self._buttons.append(_Btn(
                (right_x, y, bw, bh), "►",
                lambda e=enc: e.step(1), self.font_med))
        else:
            self._buttons.append(_Btn(
                (mid_x, y, bw, bh), "►",
                lambda e=enc: e.step(1), self.font_med))

        return y + bh + 2

    # -------------------------------------------------------------------------
    # Main loop integration
    # -------------------------------------------------------------------------

    def process_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt

            for btn in self._buttons:
                btn.handle_event(event)

            if event.type == pygame.KEYDOWN:
                self._handle_key(event.key, event.mod)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self._exp_slider_rect.collidepoint(event.pos):
                    self._exp_dragging = True
                    self._update_exp_from_mouse(event.pos[0])

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._exp_dragging = False

            if event.type == pygame.MOUSEMOTION and self._exp_dragging:
                self._update_exp_from_mouse(event.pos[0])

    def render(self):
        self.screen.fill(BG)

        # LCD (scaled 2×)
        self.hw.lcd_pygame.blit_scaled(self.screen, pygame.Rect(0, 0, self.lcd_disp_w, self.lcd_disp_h))

        # Controls panel background
        panel_rect = pygame.Rect(self.lcd_disp_w, 0, CTRL_W, self.win_h)
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)

        # Footswitch state colours
        for btn, idx in self._fs_btns:
            fs = self.hw.footswitches[idx]
            color = FS_ON if fs.toggled else FS_OFF
            pygame.draw.rect(self.screen, color, btn.rect, border_radius=4)
            lbl = fs.get_display_label() or ("FS%d" % (idx + 1))
            text = self.font_med.render(lbl[:6], True, TEXT_COLOR)
            tr = text.get_rect(center=btn.rect.center)
            self.screen.blit(text, tr)

        # All other buttons and encoder header labels
        fs_btn_set = {id(b) for b, _ in self._fs_btns}
        for btn in self._buttons:
            if id(btn) not in fs_btn_set:
                btn.draw(self.screen)
        for lbl in self._labels:
            lbl.draw(self.screen)

        # Expression pedal
        if self.hw.analog_controls:
            self._draw_exp_slider()

        # Keyboard hints (bottom of panel) — only show what's wired up
        hints = ["← → nav  Enter=click  L=long"]
        num_fs = len(self.hw.footswitches)
        if num_fs:
            hints.append("1-%d footswitches" % num_fs)
        tweak = getattr(self.hw, 'tweak_encoders', [])
        vol   = getattr(self.hw, 'volume_encoder', None)
        if len(tweak) >= 1:
            hints.append("Q/W enc1  E=press")
        if len(tweak) >= 2:
            hints[-1] += "  A/S enc2  D=press"
        if vol is not None:
            hints.append("Z/X vol enc")
        if self.hw.analog_controls:
            hints.append("↑↓ expr pedal   Esc=quit")
        else:
            hints.append("Esc=quit")

        hy = self.win_h - len(hints) * 16 - 5
        for h in hints:
            surf = self.font_sm.render(h, True, DIM_TEXT)
            self.screen.blit(surf, (self.ctrl_x + 4, hy))
            hy += 16

        pygame.display.flip()

    def _draw_exp_slider(self):
        ctrl = self.hw.analog_controls[0]
        y = self._exp_slider_y
        lbl = self.font_sm.render("Expr (CC%s)" % ctrl.midi_CC, True, DIM_TEXT)
        self.screen.blit(lbl, (self.ctrl_x + 5, y))

        r = self._exp_slider_rect
        pygame.draw.rect(self.screen, SLIDER_BG, r, border_radius=4)
        fill_w = int(r.width * self._exp_value / 127)
        if fill_w > 0:
            pygame.draw.rect(self.screen, SLIDER_FG,
                             (r.x, r.y, fill_w, r.height), border_radius=4)
        tx = r.x + fill_w
        pygame.draw.circle(self.screen, TEXT_COLOR, (tx, r.centery), 7)

    # -------------------------------------------------------------------------
    # Input handling
    # -------------------------------------------------------------------------

    def _handle_key(self, key, mod):
        nav = getattr(self.hw, 'nav_encoder', None)
        tweak = getattr(self.hw, 'tweak_encoders', [])
        vol   = getattr(self.hw, 'volume_encoder', None)

        if key == pygame.K_ESCAPE:
            raise KeyboardInterrupt

        # Nav encoder
        elif key == pygame.K_LEFT and nav:
            nav.step(-1)
        elif key == pygame.K_RIGHT and nav:
            nav.step(1)
        elif key in (pygame.K_RETURN, pygame.K_SPACE) and nav:
            nav.press(switchstate.Value.RELEASED)
        elif key == pygame.K_l and nav:
            nav.press(switchstate.Value.LONGPRESSED)

        # Footswitches
        elif key in (pygame.K_1, pygame.K_KP1):
            self._press_fs(0)
        elif key in (pygame.K_2, pygame.K_KP2):
            self._press_fs(1)
        elif key in (pygame.K_3, pygame.K_KP3):
            self._press_fs(2)
        elif key in (pygame.K_4, pygame.K_KP4):
            self._press_fs(3)

        # Tweak encoder 1
        elif key == pygame.K_q and len(tweak) >= 1:
            tweak[0].step(-1)
        elif key == pygame.K_w and len(tweak) >= 1:
            tweak[0].step(1)
        elif key == pygame.K_e and len(tweak) >= 1:
            tweak[0].press(switchstate.Value.RELEASED)

        # Tweak encoder 2
        elif key == pygame.K_a and len(tweak) >= 2:
            tweak[1].step(-1)
        elif key == pygame.K_s and len(tweak) >= 2:
            tweak[1].step(1)
        elif key == pygame.K_d and len(tweak) >= 2:
            tweak[1].press(switchstate.Value.RELEASED)

        # Volume encoder
        elif key == pygame.K_z and vol:
            vol.step(-1)
        elif key == pygame.K_x and vol:
            vol.step(1)

        # Expression pedal
        elif key == pygame.K_UP:
            self._nudge_exp(5)
        elif key == pygame.K_DOWN:
            self._nudge_exp(-5)

    def _press_fs(self, index):
        if index < len(self.hw.footswitches):
            self.hw.footswitches[index].press()

    def _nudge_exp(self, delta):
        if not self.hw.analog_controls:
            return
        self._exp_value = max(0, min(127, self._exp_value + delta))
        ctrl = self.hw.analog_controls[0]
        ctrl.set_value(self._exp_value)
        ctrl.send_midi(self._exp_value)

    def _update_exp_from_mouse(self, mouse_x):
        r = self._exp_slider_rect
        ratio = (mouse_x - r.x) / r.width
        self._exp_value = int(max(0.0, min(1.0, ratio)) * 127)
        if self.hw.analog_controls:
            ctrl = self.hw.analog_controls[0]
            ctrl.set_value(self._exp_value)
            ctrl.send_midi(self._exp_value)
