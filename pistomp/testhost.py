import sys
import os
import time
import curses
import logging
import alsaaudio as alsa
import numpy as np

from pistomp.handler import Handler
from pistomp.hardware import Hardware

class CursesLogHandler(logging.Handler):
    def __init__(self, screen):
        logging.Handler.__init__(self)
        self.screen = screen

    def emit(self, record):
        try:
            msg = self.format(record)
            screen = self.screen
            fs = "\n %s"
            screen.addstr(fs % msg)
            screen.clrtoeol()
            screen.box()
            screen.refresh()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            raise
        
class Testhost(Handler):

    LOG_HEIGHT = 8
    VU_GREEN = 1
    VU_YELLOW = 2
    VU_RED = 3
    LINE_BLUE = 4

    def _init_curses(self):
        self.log_handler = None
        self.win = None
        self.log_win = None
        curses.setupterm(term='xterm')
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.use_default_colors()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        self.stdscr.nodelay(True)
        self.stdscr.idlok(True)
        self.stdscr.clear()
        self.stdscr.refresh()
        try:
            curses.curs_set(0)
        except:
            pass
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.win = curses.newwin(self.maxy - self.LOG_HEIGHT - 1, 0, 0, 0)
        self.win.box()
        self.win.refresh()
        self.win.leaveok(True)
        self.win.idlok(True)
        self.win.nodelay(True)
        log_win = curses.newwin(self.LOG_HEIGHT, self.maxx, self.maxy - self.LOG_HEIGHT - 1, 0)
        self.log_win = log_win
        log_win.box()
        log_win.refresh()
        log_win.scrollok(True)
        log_win.idlok(True)
        log_win.keypad(True)
        log_win.leaveok(True)
        log_win.setscrreg(1, self.LOG_HEIGHT-1)
        log_win.move(1, 1)
        self.log_handler = CursesLogHandler(log_win)
        formatter = logging.Formatter(' %(asctime) -25s - %(name) -15s - %(levelname) -10s - %(message)s')
        formatterDisplay = logging.Formatter('  %(asctime)-8s|%(name)-12s|%(levelname)-6s|%(message)-s', '%H:%M:%S')
        self.log_handler.setFormatter(formatterDisplay)
        logger = logging.getLogger()
        logger.addHandler(self.log_handler)
        logger.setLevel(logging.DEBUG)
        curses.init_pair(self.VU_GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(self.VU_YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.VU_RED, curses.COLOR_RED, -1)
        curses.init_pair(self.LINE_BLUE, curses.COLOR_BLUE, -1)
        logging.info("Colors:" + str(curses.has_colors()))

    def _cleanup_curses(self):
        lh = self.log_handler
        self.log_handler = None
        if lh is not None:
            logger = logging.getLogger()
            logger.removeHandler(lh)
            del lh
        if self.log_win is not None:
            del self.log_win
        if self.win is not None:
            del self.win
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()
        self.stdscr = None

    def _init_audio(self):
        cidx = self.audiocard.card_index
        self.audio_in = ain = alsa.PCM(alsa.PCM_CAPTURE, alsa.PCM_NORMAL, cardindex=cidx)
        self.audio_out = aout = alsa.PCM(alsa.PCM_PLAYBACK, alsa.PCM_NORMAL, cardindex=cidx)
        ain.setchannels(2)
        ain.setrate(44100)
        ain.setformat(alsa.PCM_FORMAT_S16_LE)
        ain.setperiodsize(1024)
        aout.setchannels(2)
        aout.setrate(44100)
        aout.setformat(alsa.PCM_FORMAT_S16_LE)
        aout.setperiodsize(1024)

    def __init__(self, audiocard = None, homedir = None):
        self.hardware = None
        self.homedir = homedir
        self.audiocard = audiocard
        self.stdscr = None
        self.encval = 0
        self.encsw = '--'
        self.enclast = 0
        self.dirty = False
        self.audio_in = None
        self.audio_out = None
        self.lpeak = 0
        self.rpeak = 0
        try:
            self._init_curses()
        except:
            if self.stdscr is not None:
                self._cleanup_curses()
            raise
        if self.audiocard is not None:
            try:
                self._init_audio()
            except Exception as e:
                logging.error("Failed to init audio:" + str(e))
                if self.audio_in is not None:
                    del self.audio_in
                if self.audio_out is not None:
                    del self.audio_out
                self.audiocard = None
                self.audio_in = None
                self.audio_out = None

    def cleanup(self):
        if self.stdscr is not None:
            self._cleanup_curses()

    def __del__(self):
        self.cleanup()

    def _update_line(self, l, *args):
        self.win.move(l,1)
        self.win.clrtoeol()
        self.win.addstr(l, 1, *args)

    def _disp_title(self, line, data):
        self.win.attrset(curses.color_pair(self.LINE_BLUE))
        self.win.hline(line, 1, curses.ACS_HLINE, self.maxx - 2)
        self.win.addstr(line, 4, str(data))
        self.win.attrset(0)

    def _disp_footswitches(self, line, data):
        disp = ""        
        for sw in self.hardware.footswitches:
            if sw.enabled:
                disp += "ON  "
            else:
                disp += "OFF "
            self._update_line(line, disp)

    def _disp_encoder(self, line, data):
        disp = str(self.encval) + ' ' + str(self.encsw)
        self._update_line(line, disp)
            
    def _disp_capture_volume(self, line, data):
        vol = self.audiocard.get_parameter(self.audiocard.CAPTURE_VOLUME)
        disp = 'Capture volume: ' + str(vol) + ' [+]/[-]'
        self._update_line(line, disp)

    def _disp_vu(self, line, data):
        label, channel = data
        self.win.hline(l, self.maxx - 2)
        self.win.addstr(l, 1, label + '  |')
        if channel == 0:
            peak = self.lpeak
        else:
            peak = self.rpeak
        peak = int(peak * 20 / 32768)
        # Random scale, FIX this if you understand audio :-)
        # probably need some log here..
        self.win.attrset(curses.color_pair(self.VU_GREEN))
        self.win.hline(line, 5, curses.ACS_BLOCK, min(peak, 10))
        if (peak > 10):
            self.win.attrset(curses.color_pair(self.VU_YELLOW))
            self.win.hline(line, 15, curses.ACS_BLOCK, min(peak - 10, 15))
        if (peak > 15):
            self.win.attrset(curses.color_pair(self.VU_RED))
            self.win.hline(line, 20, curses.ACS_BLOCK, min(peak - 15, 20))
        self.win.attrset(0)
        self.win.addch(line, 25, '|')

    def _add_line(self, func, args = None):
        l = len(self.lines)
        self.lines.append((func, args))
        return l

    def _add_title(self, label):
        return self._add_line(self._disp_title, label)

    def init_display(self):
        # Clear screen
        self.win.clear()
        self.win.box()

        self.lines = [ (None, None) ]
        if len(self.hardware.footswitches) > 0:
            self._add_title('Switches')
            self._add_line(self._disp_footswitches)
        self._add_title('Encoder')
        self._add_line(self._disp_encoder)
        if self.audiocard is not None:
            self._add_title('Audio')
            self._add_line(self._disp_capture_volume)
            self.vu_left = self._add_line(self._disp_vu, ('L', 0))
            self.vu_right = self._add_line(self._disp_vu, ('R', 1))

    def refresh(self):
        if self.hardware is None:
            return

        for idx, line in enumerate(self.lines):
            func, data = line
            if func is not None:
                func(idx, data)

        # Refresh the screene
        self.win.box()
        self.win.refresh()

    def universal_encoder_select(self, direction):
        self.encval += direction
        self.dirty = True

    def universal_encoder_sw(self, value):
        self.encsw = value
        self.enclast = time.monotonic_ns()
        self.dirty = True

    def update_lcd_fs(self, bypass_change = False):
        self.dirty = True

    def add_hardware(self, hardware):
        self.hardware = hardware
        self.init_display()
        self.refresh()

    def add_lcd(self, lcd):
        self.lcd = lcd

    def _key_quit(self, key):
        raise KeyboardInterrupt

    def _key_input_gain(self, key):
        if key == '+':
            chg = 0.25
        else:
            chg = -0.25
        vol = self.audiocard.get_parameter(self.audiocard.CAPTURE_VOLUME)
        self.audiocard.set_parameter(self.audiocard.CAPTURE_VOLUME, vol + chg)
        self.dirty = True

    def _handle_key(self, key):
        key_map = { 'q' : self._key_quit,
                    '+' : self._key_input_gain,
                    '-' : self._key_input_gain,
                    }
        if key in key_map:
            key_map[key](key)

    def poll_controls(self):
        k = self.win.getch()
        if k > 0:
            self._handle_key(k)
        if self.hardware is not None:
            self.hardware.poll_controls()
            if self.enclast > 0 and (time.monotonic_ns() - self.enclast) > 1000000000:
                self.encsw = '--'
                self.dirty = True
                self.enclast = 0

        if self.audiocard is not None:
            l,data = self.audio_in.read()
            if l > 0:
                npd = np.frombuffer(data, dtype=np.int16)
                d_left = npd[0::2]
                d_right = npd[1::2]
                # Ideally look for peak to peak but ...
                self.lpeak = np.amax(d_left)
                self.rpeak = np.amax(d_right)
                if not self.dirty:
                    func, data = self.lines[self.vu_left]
                    func(self.vu_left, data)
                    func, data = self.lines[self.vu_right]
                    func(self.vu_right, data)

        if self.dirty:
            self.dirty = False
            self.refresh()
