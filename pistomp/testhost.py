import sys
import os
import time
import curses
import logging

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

    LOG_HEIGHT = 6

    def _init_curses(self):
        self.stdscr = curses.initscr()
        self.log_handler = None
        self.win = None
        self.log_win = None
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
        self.win = curses.newwin(self.maxy - self.LOG_HEIGHT - 2, 0, 0, 0)
        self.win.box()
        self.win.refresh()
        self.win.leaveok(True)
        self.win.idlok(True)
        self.win.nodelay(True)
        log_win = curses.newwin(self.LOG_HEIGHT, self.maxx, self.maxy - self.LOG_HEIGHT - 2, 0)
        self.log_win = log_win
        log_win.box()
        log_win.refresh()
        log_win.scrollok(True)
        log_win.idlok(True)
        log_win.keypad(True)
        log_win.leaveok(True)
        log_win.setscrreg(1, self.LOG_HEIGHT-2)
        log_win.move(1, 1)
        self.log_handler = CursesLogHandler(log_win)
        formatter = logging.Formatter(' %(asctime) -25s - %(name) -15s - %(levelname) -10s - %(message)s')
        formatterDisplay = logging.Formatter('  %(asctime)-8s|%(name)-12s|%(levelname)-6s|%(message)-s', '%H:%M:%S')
        self.log_handler.setFormatter(formatterDisplay)
        logger = logging.getLogger()
        logger.addHandler(self.log_handler)
        logger.setLevel(logging.DEBUG)

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
 
    def __init__(self, homedir = None):
        self.hardware = None
        self.homedir = homedir
        self.stdscr = None
        self.encval = 0
        self.encsw = '--'
        self.enclast = 0
        self.dirty = False
        try:
            self._init_curses()
        except:
            if self.stdscr is not None:
                self._cleanup_curses()
            raise

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
        self._update_line(line, str(data), curses.A_REVERSE)

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
            
    def init_display(self):
        # Clear screen
        self.win.clear()
        self.win.box()

        self.lines = [ (None, None) ]
        if len(self.hardware.footswitches) > 0:
            self.lines.append((self._disp_title, 'Switches'))
            self.lines.append((self._disp_footswitches, None))
        self.lines.append((self._disp_title, 'Encoder'))
        self.lines.append((self._disp_encoder, None))

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

    def poll_controls(self):
        k = self.win.getch()
        if k > 0:
            # Do things...
            pass
        if self.hardware is not None:
            self.hardware.poll_controls()
            if self.enclast > 0 and (time.monotonic_ns() - self.enclast) > 1000000000:
                self.encsw = '--'
                self.dirty = True
                self.enclast = 0
            if self.dirty:
                self.dirty = False
                self.refresh()

