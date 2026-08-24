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

"""Live compressor gain-reduction meter, backed by a JACK subprocess.

A ``GrMeterClient`` spawns ``python -m pistomp.compmeter``, which opens a JACK
client, taps the compressor instance's input and output audio ports, and writes
a small telemetry frame (input dB, output dB, derived gain reduction dB) into
shared memory. The panel reads it lock-free on the LCD tick — same pattern as
``pistomp.tuner``.

Gain reduction is derived from the audio, not the plugin's ``gr`` output port:
``GR ≈ in_db + makeup_db − out_db`` (clamped ≥ 0), since the compressor's output
is ``input · comp_gain · makeup``. It is a metering approximation, not exact.
"""
