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

"""Metronome subprocess entry point.

Spawned by MetronomeClient as ``python -m pistomp.metronome [enabled]``.

Connects to JACK as ``pistomp-metronome``, registers stereo output ports,
and adds click audio directly to ``system:playback_1/2`` (JACK summing
means the existing mod-monitor→playback link is untouched).

Transport sync: reads BBT from ``jack_transport_query`` in the process
callback.

stdin control (one command per line):
    enable   — start clicking
    disable  — silence output (stay connected, write zeros)
    stop     — deactivate and exit
"""

from __future__ import annotations

import math
import select
import signal
import sys

import numpy as np

# ── click parameters ─────────────────────────────────────────────────────────

_CLICK_DECAY_S = 0.060  # envelope length; 5τ ≈ e^-5 → effectively silent
_CLICK_VOL_ACCENT = 0.80  # downbeat (beat 1 of bar)
_CLICK_VOL_NORMAL = 0.55  # all other beats
_CLICK_HZ_ACCENT = 1000.0
_CLICK_HZ_NORMAL = 700.0

# ── mutable state — written by main thread, read by RT callback ───────────────
# CPython bool assignment is atomic under the GIL; no lock needed here.

_running = True
_enabled = False


def _sigterm(_sig, _frame) -> None:
    global _running
    _running = False


def _precompute_click(sample_rate: int, hz: float, volume: float, decay_s: float) -> np.ndarray:
    """Decaying sine burst as float32: vol·sin(2π·hz·t)·exp(-t/τ), τ = decay_s/5."""
    n = int(decay_s * sample_rate)
    t = np.arange(n, dtype=np.float64) / sample_rate
    wave = volume * np.sin(2.0 * np.pi * hz * t) * np.exp(-t / (decay_s / 5.0))
    return wave.astype(np.float32)


def main() -> None:
    global _running, _enabled

    import jack  # type: ignore[import-untyped]

    if len(sys.argv) >= 2 and sys.argv[1] == "enabled":
        _enabled = True

    signal.signal(signal.SIGTERM, _sigterm)

    try:
        client = jack.Client("pistomp-metronome", no_start_server=True)
    except Exception as e:
        print(f"metronome: JACK open failed: {e}", file=sys.stderr)
        sys.exit(1)

    sr: int = client.samplerate
    accent = _precompute_click(sr, _CLICK_HZ_ACCENT, _CLICK_VOL_ACCENT, _CLICK_DECAY_S)
    normal = _precompute_click(sr, _CLICK_HZ_NORMAL, _CLICK_VOL_NORMAL, _CLICK_DECAY_S)

    # Capture constants into the closure — avoids repeated attribute lookups in the RT path.
    ROLLING = jack.ROLLING
    POSITION_BBT = jack.POSITION_BBT

    out_L = client.outports.register("out_L")
    out_R = client.outports.register("out_R")

    # The click state. The callback keeps this state between calls.
    # A dict lets the closure change the values without `nonlocal` or `global`.
    # wave: the array that plays now, or None.
    # pos: the count of samples that went to the output.
    # beat: the index of the last beat that made a click.
    # origin: the frame of beat 0 of this tempo segment. None means no lock.
    cs: dict = {"wave": None, "pos": 0, "beat": -1, "origin": None, "bpm": 0.0, "bpb": 0}

    @client.set_process_callback
    def process(frames: int) -> None:
        buf_L = out_L.get_array()  # pyright: ignore[reportAttributeAccessIssue]
        buf_R = out_R.get_array()  # pyright: ignore[reportAttributeAccessIssue]
        buf_L[:] = 0.0
        buf_R[:] = 0.0

        if not _enabled:
            cs["wave"] = None
            cs["origin"] = None
            return

        state, pos = client.transport_query_struct()
        if state != ROLLING:
            cs["wave"] = None
            cs["origin"] = None
            return
        if not (pos.valid & POSITION_BBT):
            cs["wave"] = None
            cs["origin"] = None
            return

        bpm: float = pos.beats_per_minute
        if bpm <= 0.0:
            return

        bpb: int = max(1, int(pos.beats_per_bar))
        tpb: float = float(pos.ticks_per_beat) or 1920.0
        spb: float = sr * 60.0 / bpm  # samples per beat
        frame: int = int(pos.frame)

        # Step 1. Continue the click that started in an earlier buffer.
        c_wave = cs["wave"]
        c_pos: int = cs["pos"]
        if c_wave is not None and c_pos < len(c_wave):
            n = min(len(c_wave) - c_pos, frames)
            buf_L[:n] += c_wave[c_pos : c_pos + n]
            buf_R[:n] += c_wave[c_pos : c_pos + n]
            cs["pos"] = c_pos + n

        # Step 2. Find the beat grid.
        # JACK gives the tick as an integer. One tick is 12.5 samples at
        # 120 bpm with 1920 ticks in a beat. Thus one read of the BBT data
        # gives the position of the grid to 12.5 samples only.
        # The integer tick makes an estimate late. It never makes an estimate
        # early. Keep the smallest estimate. The smallest estimate moves to the
        # correct origin, with an error of less than one sample.
        elapsed: float = (int(pos.bar) - 1) * bpb + (int(pos.beat) - 1) + float(pos.tick) / tpb
        estimate: float = frame - elapsed * spb

        origin = cs["origin"]
        # An estimate more than one tick after the origin means the transport
        # master moved the grid. A tap tempo that starts the beat again does
        # this, as well as seeking. A new tempo or a new meter also ends the segment.
        if origin is None or bpm != cs["bpm"] or bpb != cs["bpb"] or estimate > origin + spb / tpb + 1.0:
            origin = estimate
            cs["bpm"] = bpm
            cs["bpb"] = bpb
            cs["beat"] = math.ceil((frame - origin) / spb) - 1
        elif estimate < origin:
            origin = estimate
        cs["origin"] = origin

        # Step 3. Play each beat that starts in this buffer.
        index: int = cs["beat"] + 1
        while True:
            onset = round(origin + index * spb) - frame
            if onset >= frames:
                break
            if onset < 0:
                onset = 0  # The origin moved back. Play the click now.
            new_wave = accent if index % bpb == 0 else normal
            n = min(len(new_wave), frames - onset)
            buf_L[onset : onset + n] += new_wave[:n]
            buf_R[onset : onset + n] += new_wave[:n]
            cs["wave"] = new_wave
            cs["pos"] = n
            cs["beat"] = index
            index += 1

    client.activate()
    try:
        client.connect("pistomp-metronome:out_L", "system:playback_1")
        client.connect("pistomp-metronome:out_R", "system:playback_2")
    except Exception as e:
        print(f"metronome: JACK connect failed: {e}", file=sys.stderr)

    try:
        while _running:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                line = sys.stdin.readline()
                if not line or line.strip() == "stop":
                    break
                cmd = line.strip()
                if cmd == "enable":
                    _enabled = True
                elif cmd == "disable":
                    _enabled = False
    finally:
        client.deactivate()
        client.close()


if __name__ == "__main__":
    main()
