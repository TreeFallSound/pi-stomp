# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-Stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Modal progress panel for USB backup and restore.

  ┌───────────────────────────────────────────────┐
  │ Backing up                                    │
  │ STAGE_LEFT                                    │
  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░   │
  │  0:52                                  -2:14  │
  │ 268MB / 344MB                                 │
  │                                    [ Cancel ] │
  └───────────────────────────────────────────────┘

A backup cancels cleanly — the script builds a temp archive and renames it,
so the previous good backup survives. A restore unzips over data/ in place and
therefore offers no cancel; a half-restored tree cannot be undone.
"""

import os
import time

from uilib.box import Box
from uilib.config import Config
from uilib.label import Label
from uilib.panel import Panel
from uilib.misc import get_text_size
from uilib.progress_bar import STEEL_LABELS, STEEL_STOPS, ProgressBarWidget
from uilib.text import Button

from pistomp.input.event import ControllerEvent

from modalapi.archive import ArchiveJob, JobState

_W, _H = 320, 240
_BTN_W, _BTN_H, _BTN_GAP, _BTN_PAD = 92, 28, 6, 14
_BTN_Y = _H - _BTN_H - _BTN_GAP
_BAR_Y = 72
_BAR_H = 88
_MARGIN = 12
_FILE_Y = _BAR_Y + _BAR_H + 2
_STATUS_Y = _FILE_Y + 18

_FG = (235, 235, 235)
_DIM = (150, 150, 150)
_FILE = (120, 145, 165)
_ERR = (230, 90, 80)
_OK = (110, 205, 120)

# Below this the ETA is noise — a few small .ttl files land before the first model.
_ETA_MIN_PROGRESS = 0.03


def _mb(num_bytes: int) -> str:
    return f"{num_bytes / 1_000_000:.0f}MB"


def _ellipsize(text: str, font, max_w: int) -> str:
    if get_text_size(text, font)[0] <= max_w:
        return text
    while text and get_text_size(text + "…", font)[0] > max_w:
        text = text[:-1]
    return text + "…"


class ArchiveProgressPanel(Panel):
    def __init__(
        self,
        *,
        title: str,
        noun: str,
        subtitle: str,
        job: ArchiveJob,
        on_dismiss,
        cancellable: bool,
        done_label: str = "Close",
    ) -> None:
        super().__init__(
            box=Box.xywh(0, 0, _W, _H),
            auto_destroy=True,
            no_dim=True,
            opaque=True,
            persist_on_board_change=True,
            bkgnd_color=(0, 0, 0),
            fgnd_color=_FG,
        )
        self._job = job
        self._on_dismiss = on_dismiss
        self._cancellable = cancellable
        self._done_label = done_label
        self._noun = noun
        self._started = time.monotonic()
        self._last_state = JobState.RUNNING

        cfg = Config()
        font = cfg.get_font("default")
        title_font = cfg.get_font("default_title")
        small = cfg.get_font("small")

        self._title_lbl = Label(_MARGIN, 16, title_font, parent=self)
        self._title_lbl.set_text(title, _FG)
        self._sub_lbl = Label(_MARGIN, 44, small, parent=self)
        self._sub_lbl.set_text(_ellipsize(subtitle, small, _W - 2 * _MARGIN), _DIM)

        self._bar = ProgressBarWidget(
            box=Box.xywh(0, _BAR_Y, _W, _BAR_H),
            total_seconds=0.0,
            font=font,
            caption_font=small,
            parent=self,
            stops=STEEL_STOPS,
            label_colors=STEEL_LABELS,
        )

        self._file_font = small
        self._file_lbl = Label(_MARGIN, _FILE_Y, small, parent=self)
        self._status_lbl = Label(_MARGIN, _STATUS_Y, small, parent=self)
        self._status_lbl.set_text(f"0MB / {_mb(job.total_bytes)}", _DIM)

        labels = ["Close", done_label] + (["Cancel"] if cancellable else [])
        btn_w = max(_BTN_W, max(get_text_size(t, font)[0] for t in labels) + 2 * _BTN_PAD)
        self._btn = Button(
            box=Box.xywh((_W - btn_w) // 2, _BTN_Y, btn_w, _BTN_H),
            text="Cancel" if cancellable else "",
            font=font,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_button(),
        )
        self._btn.visible = cancellable
        if cancellable:
            self.add_sel_widget(self._btn)

    def on_event(self, event: ControllerEvent) -> bool:
        # Panel.handle resolves NAV before consulting on_event, so the axiom holds:
        # everything reaching here is a footswitch/knob, and a bypass toggle or board
        # change while unzip rewrites data/ would race the restore. Swallow until done.
        return self._job.state is JobState.RUNNING

    def _open_editor_for_selection(self) -> bool:
        # NAV click with nothing selected (restore, mid-run): the click was aimed at
        # this panel's empty selection, not at the board hidden behind it.
        return self._job.state is JobState.RUNNING

    @property
    def job_state(self) -> JobState:
        return self._job.state

    def _on_button(self) -> None:
        if self._job.state is JobState.RUNNING:
            self._job.cancel()
            self._title_lbl.set_text("Cancelling…", _DIM)
            return
        self._on_dismiss()

    def _finish(self, state: JobState) -> None:
        self._bar.set_done() if state is JobState.DONE else self._bar.freeze()
        self._file_lbl.set_text("", _FILE)
        if state is JobState.DONE:
            self._title_lbl.set_text(f"{self._noun} complete", _OK)
            self._status_lbl.set_text(f"{_mb(self._job.total_bytes)} processed", _DIM)
        elif state is JobState.CANCELLED:
            self._title_lbl.set_text(f"{self._noun} cancelled", _DIM)
            self._status_lbl.set_text("Previous backup left intact", _DIM)
        else:
            self._title_lbl.set_text(f"{self._noun} failed", _ERR)
            self._status_lbl.set_text(self._job.error.splitlines()[-1][:44] if self._job.error else "", _ERR)

        self._btn.set_text(self._done_label if state is JobState.DONE else "Close")
        if not self._btn.visible:
            self._btn.visible = True
            self.add_sel_widget(self._btn)
        self.refresh()

    def tick(self) -> None:
        state = self._job.state
        if state is not self._last_state:
            self._last_state = state
            if state is not JobState.RUNNING:
                self._finish(state)
            return
        if state is not JobState.RUNNING:
            return

        p = self._job.progress()
        elapsed = time.monotonic() - self._started
        if p >= _ETA_MIN_PROGRESS:
            self._bar.set_total(elapsed / p)
        self._bar.set_progress(p)
        self._status_lbl.set_text(f"{_mb(self._job.done_bytes)} / {_mb(self._job.total_bytes)}", _DIM)
        entry = self._job.current_entry
        if entry:
            self._file_lbl.set_text(_ellipsize(os.path.basename(entry), self._file_font, _W - 2 * _MARGIN), _FILE)
