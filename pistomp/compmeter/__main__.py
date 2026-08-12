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

"""Compressor GR-meter subprocess entry point.

Usage: python -m pistomp.compmeter <shm_name> <in_port> <out_port> <source_spec> <makeup_db>
  shm_name     : POSIX SHM name created by the parent
  in_port      : JACK output port carrying the compressor input, e.g. "effect_3:in_1"
  out_port     : JACK output port carrying the compressor output, e.g. "effect_3:out_1"
  source_spec  : "jack" (tap the ports) or "tone[:gain_db]" (synthesised, for tests)
  makeup_db    : initial makeup gain, subtracted when deriving GR

Reads control lines on stdin: "makeup <db>" updates the makeup gain; "stop" exits.
Exits 0 on clean stop, 3 on error.
"""

from __future__ import annotations

import ctypes
import select
import signal
import sys

from pistomp.compmeter.engine import GrEngine
from pistomp.compmeter.source import build_source
from pistomp.process_client import attach_shm


class _GrFrame(ctypes.Structure):
    _fields_ = [
        ("seq", ctypes.c_uint32),
        ("valid", ctypes.c_uint32),
        ("in_db", ctypes.c_float),
        ("out_db", ctypes.c_float),
        ("gr_db", ctypes.c_float),
        ("_pad", ctypes.c_uint32),
        ("ts", ctypes.c_double),
    ]


_running = True


def _on_sigterm(sig, frame) -> None:
    global _running
    _running = False


def main() -> None:
    if len(sys.argv) < 6:
        print(f"Usage: {sys.argv[0]} <shm_name> <in_port> <out_port> <source_spec> <makeup_db>", file=sys.stderr)
        sys.exit(3)

    shm_name, in_port, out_port, source_spec, makeup = sys.argv[1:6]
    signal.signal(signal.SIGTERM, _on_sigterm)

    shm = attach_shm(shm_name)
    assert shm.buf is not None
    frame = _GrFrame.from_buffer(shm.buf)

    source = build_source(source_spec, in_port, out_port, name="pistomp-compmeter")
    engine = GrEngine(source, makeup_db=float(makeup))

    try:
        try:
            engine.start()
            while _running:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist:
                    line = sys.stdin.readline()
                    if not line or line.strip() == "stop":
                        break
                    if line.startswith("makeup "):
                        try:
                            engine.set_makeup(float(line.split(None, 1)[1]))
                        except (ValueError, IndexError):
                            pass

                reading = engine.get_reading()
                frame.seq += 1
                if reading is None:
                    frame.valid = 0
                else:
                    frame.in_db = reading.in_db
                    frame.out_db = reading.out_db
                    frame.gr_db = reading.gr_db
                    frame.ts = reading.ts
                    frame.valid = 1 if reading.valid else 0
                frame.seq += 1
        finally:
            engine.stop()
    finally:
        del frame
        shm.close()


if __name__ == "__main__":
    main()
