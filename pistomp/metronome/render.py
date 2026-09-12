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

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types
import wave
from pathlib import Path

import numpy as np

_ROLLING = 1
_POSITION_BBT = 0x10


class _Position:
    """The part of ``jack_position_t`` that the process callback reads."""

    valid: int
    frame: int
    bar: int
    beat: int
    tick: float
    ticks_per_beat: float
    beats_per_bar: float
    beats_per_minute: float


class _Port:
    def __init__(self, frames: int) -> None:
        self.buf = np.zeros(frames, dtype=np.float32)

    def get_array(self) -> np.ndarray:
        return self.buf


class _Ports(list):
    def __init__(self, frames: int) -> None:
        super().__init__()
        self._frames = frames

    def register(self, name: str) -> _Port:
        port = _Port(self._frames)
        self.append(port)
        return port


class _FakeClient:
    """Runs the callback from ``activate()``, after the callback is registered."""

    def __init__(self, spec: RenderSpec) -> None:
        self.samplerate = spec.samplerate
        self.blocksize = spec.frames
        self.outports = _Ports(spec.frames)
        self._spec = spec
        self._callback = None
        self._frame = 0
        self.audio = np.zeros(0, dtype=np.float32)

    def set_process_callback(self, fn):
        self._callback = fn
        return fn

    def transport_query_struct(self) -> tuple[int, _Position]:
        spec = self._spec
        pos = _Position()
        pos.valid = _POSITION_BBT
        pos.frame = self._frame
        beats, bpm = spec.beats_at(self._frame)
        whole = int(beats)
        frac = beats - whole
        pos.bar = whole // spec.beats_per_bar + 1
        pos.beat = whole % spec.beats_per_bar + 1
        # A jack_position_t holds the tick as an int32. The value "float" for
        # --tick-mode models a master that does not round the tick. This hides
        # the error that the integer tick causes.
        pos.tick = frac * spec.ticks_per_beat
        if spec.tick_mode == "int":
            pos.tick = float(int(pos.tick))
        pos.ticks_per_beat = spec.ticks_per_beat
        pos.beats_per_bar = float(spec.beats_per_bar)
        pos.beats_per_minute = bpm
        return _ROLLING, pos

    def activate(self) -> None:
        callback = self._callback
        if callback is None:
            raise RuntimeError("process callback was never registered")
        spec = self._spec
        total = int(spec.duration_s * spec.samplerate)
        out = np.zeros(total, dtype=np.float32)
        frame = 0
        while frame + spec.frames <= total:
            self._frame = frame
            for port in self.outports:
                port.buf[:] = 0.0
            callback(spec.frames)
            out[frame : frame + spec.frames] = self.outports[0].buf
            frame += spec.frames
        self.audio = out

    def connect(self, source: str, dest: str) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def close(self) -> None:
        pass


class RenderSpec:
    def __init__(
        self,
        bpm: float,
        frames: int,
        beats_per_bar: int,
        duration_s: float,
        samplerate: int,
        ticks_per_beat: float,
        tick_mode: str,
        tempo_changes: list[tuple[float, float]] | None = None,
        grid_restarts: list[float] | None = None,
    ) -> None:
        self.bpm = bpm
        self.frames = frames
        self.beats_per_bar = beats_per_bar
        self.duration_s = duration_s
        self.samplerate = samplerate
        self.ticks_per_beat = ticks_per_beat
        self.tick_mode = tick_mode
        self._segments = self._build_segments(tempo_changes or [], grid_restarts or [])

    @property
    def samples_per_beat(self) -> float:
        return self.samplerate * 60.0 / self.bpm

    def _build_segments(
        self, tempo_changes: list[tuple[float, float]], grid_restarts: list[float]
    ) -> list[tuple[int, float, float]]:
        """Make the list of (start frame, beats at that frame, bpm).

        A tempo change keeps the beat phase. A grid restart sets the beat
        position back to zero. A real timebase master does the same.
        """
        events: list[tuple[int, str, float]] = []
        for at_s, new_bpm in tempo_changes:
            events.append((int(at_s * self.samplerate), "tempo", new_bpm))
        for at_s in grid_restarts:
            events.append((int(at_s * self.samplerate), "restart", 0.0))
        events.sort(key=lambda event: event[0])

        segments = [(0, 0.0, self.bpm)]
        for frame, kind, value in events:
            start, beats_at_start, bpm = segments[-1]
            beats = beats_at_start + (frame - start) * bpm / (self.samplerate * 60.0)
            if kind == "tempo":
                segments.append((frame, beats, value))
            else:
                segments.append((frame, 0.0, bpm))
        return segments

    def beats_at(self, frame: int) -> tuple[float, float]:
        """Give the beat position and the tempo at this frame."""
        start, beats_at_start, bpm = self._segments[0]
        for segment in self._segments:
            if segment[0] <= frame:
                start, beats_at_start, bpm = segment
            else:
                break
        return beats_at_start + (frame - start) * bpm / (self.samplerate * 60.0), bpm


def _fake_jack_module(spec: RenderSpec) -> tuple[types.ModuleType, list[_FakeClient]]:
    module = types.ModuleType("jack")
    made: list[_FakeClient] = []

    def client_factory(name: str, no_start_server: bool = False) -> _FakeClient:
        client = _FakeClient(spec)
        made.append(client)
        return client

    module.Client = client_factory  # pyright: ignore[reportAttributeAccessIssue]
    module.ROLLING = _ROLLING  # pyright: ignore[reportAttributeAccessIssue]
    module.POSITION_BBT = _POSITION_BBT  # pyright: ignore[reportAttributeAccessIssue]
    return module, made


def _load_entry_point(source: Path | None) -> types.ModuleType:
    if source is None:
        import pistomp.metronome.__main__ as entry

        return entry
    spec = importlib.util.spec_from_file_location("metronome_under_test", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(spec: RenderSpec, source: Path | None = None) -> np.ndarray:
    entry = _load_entry_point(source)

    fake, made = _fake_jack_module(spec)
    saved_modules = sys.modules.get("jack")
    saved_argv, saved_stdin = sys.argv, sys.stdin

    # main() waits in select() on stdin for a command. Send "stop" first. Then
    # main() exits through its own deactivate and close path.
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"stop\n")
    os.close(write_fd)

    sys.modules["jack"] = fake
    sys.argv = ["metronome", "enabled"]
    sys.stdin = os.fdopen(read_fd)
    try:
        entry.main()  # pyright: ignore[reportAttributeAccessIssue]
    finally:
        sys.stdin.close()
        sys.argv, sys.stdin = saved_argv, saved_stdin
        if saved_modules is None:
            del sys.modules["jack"]
        else:
            sys.modules["jack"] = saved_modules

    if not made:
        raise RuntimeError("no JACK client was opened")
    return made[0].audio


def write_wav(path: Path, audio: np.ndarray, samplerate: int) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(samplerate)
        handle.writeframes(pcm.tobytes())


def main() -> None:
    """Render a metronome WAV file for testing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", type=Path, default=Path("metronome.wav"))
    parser.add_argument("--bpm", type=float, default=120.0)
    parser.add_argument("--frames", type=int, default=256, help="JACK buffer size")
    parser.add_argument("--beats-per-bar", type=int, default=4)
    parser.add_argument("--duration", type=float, default=8.5, help="seconds")
    parser.add_argument("--samplerate", type=int, default=48000)
    parser.add_argument("--ticks-per-beat", type=float, default=1920.0)
    parser.add_argument("--tick-mode", choices=("int", "float"), default="int")
    parser.add_argument(
        "--source", type=Path, default=None, help="render this copy of __main__.py in place of the installed one"
    )
    parser.add_argument(
        "--tempo-change",
        action="append",
        default=[],
        metavar="SEC:BPM",
        help="change the tempo at this time. The beat phase stays continuous",
    )
    parser.add_argument(
        "--restart-grid",
        action="append",
        default=[],
        type=float,
        metavar="SEC",
        help="set the beat position back to bar 1 beat 1 at this time",
    )
    args = parser.parse_args()

    tempo_changes = []
    for item in args.tempo_change:
        at_s, _, new_bpm = item.partition(":")
        tempo_changes.append((float(at_s), float(new_bpm)))

    spec = RenderSpec(
        args.bpm,
        args.frames,
        args.beats_per_bar,
        args.duration,
        args.samplerate,
        args.ticks_per_beat,
        args.tick_mode,
        tempo_changes,
        args.restart_grid,
    )
    audio = render(spec, args.source)
    write_wav(args.out, audio, args.samplerate)

    peak = float(np.abs(audio).max())
    clipped = int(np.count_nonzero(np.abs(audio) >= 1.0))
    print(
        f"{args.out}: {args.bpm} bpm, {args.frames} frames, tick={args.tick_mode} → peak={peak:.4f} clipped={clipped}"
    )


if __name__ == "__main__":
    main()
