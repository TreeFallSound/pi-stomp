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

from PIL import Image

from uilib.image import ImageWidget


class AnimatedImageWidget(ImageWidget):
    """ImageWidget that can also cycle through a pre-loaded set of frames.

    Externally driven via tick() — no internal timer. tick() on a stopped widget
    or on a widget with no frames is a no-op, so callers can poll blindly.

    ticks_per_frame controls how many tick() calls a frame stays on screen for.
    """

    def __init__(self, static_path, frame_paths=(), ticks_per_frame=1, **kwargs):
        super().__init__(static_path, **kwargs)
        self._frames = [Image.open(p) for p in frame_paths]
        if self._frames:
            base = self.image.size
            for p, f in zip(frame_paths, self._frames):
                if f.size != base:
                    raise ValueError(
                        f"AnimatedImageWidget frame {p} size {f.size} does not match static image size {base}"
                    )
        if ticks_per_frame < 1:
            raise ValueError("ticks_per_frame must be >= 1")
        self._ticks_per_frame = ticks_per_frame
        self._frame_idx = 0
        self._tick_count = 0
        self._playing = False

    def play(self):
        if self._playing:
            return
        self._playing = True
        self._frame_idx = 0
        self._tick_count = 0

    def stop(self, static_path):
        """Stop animating and show static_path. Caller-supplied because the
        right resolved frame is a domain decision."""
        self._playing = False
        self.replace_img(static_path)

    def tick(self):
        if not self._playing or not self._frames:
            return
        self._tick_count += 1
        if self._tick_count < self._ticks_per_frame:
            return
        self._tick_count = 0
        self._frame_idx = (self._frame_idx + 1) % len(self._frames)
        self.image = self._frames[self._frame_idx]
        self.refresh()

    @property
    def is_playing(self):
        return self._playing
