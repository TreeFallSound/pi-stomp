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

"""Read a 24-bit / 48 kHz / mono WAV file into a float32 numpy array.

The NAM reamp file (T3K-sweep-v3.wav) is 24-bit mono 48 kHz. stdlib `wave` has no
int24 dtype, so we read the raw bytes and sign-extend manually:

    bytes (-1, 3) → pad 4th sign-extension byte → view as little-endian int32
    → scale by 1/2**31 → float32

This keeps numpy and stdlib wave as the only dependencies (both already
runtime deps).
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt


def wav_duration(path: Path | str) -> float:
    """Return the duration in seconds of *path* without loading samples."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"WAV file not found: {path}")
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def load_wav_float32(path: Path | str) -> npt.NDArray[np.float32]:
    """Load a 24-bit / 48 kHz / mono WAV file and return float32 samples."""
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 3:
            raise ValueError(f"{path}: expected 24-bit (sampwidth=3), got {wf.getsampwidth()}")
        if wf.getnchannels() != 1:
            raise ValueError(f"{path}: expected mono (1 channel), got {wf.getnchannels()}")
        if wf.getframerate() != 48000:
            raise ValueError(f"{path}: expected 48000 Hz, got {wf.getframerate()}")
        raw = wf.readframes(wf.getnframes())

    buf = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
    n = len(buf)
    padded = np.zeros((n, 4), dtype=np.uint8)
    padded[:, 1:] = buf
    int32 = padded.view(np.dtype("<i4")).reshape(-1)
    return (int32.astype(np.float32)) / np.float32(2**31)
