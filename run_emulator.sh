#!/usr/bin/env sh

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

# Launch the pi-stomp emulator.

# Optional first argument: v2 / v3 (default: v3)
_version="${1:-v3}"
case "$_version" in
    v2|v3) shift ;;
    *) _version="v3" ;;
esac

# MOD Desktop runs its own JACK server named "mod-desktop" rather than the
# system default. JACK2's C library reads JACK_DEFAULT_SERVER automatically,
# so this covers both the tuner and the NAM capture client with no code changes.
export JACK_DEFAULT_SERVER="${JACK_DEFAULT_SERVER:-mod-desktop}"

# pygame runs in headless mode by default; set an appropriate video driver
# for the current platform so we can see the emulator.
case "$(uname -s)" in
    Darwin) export SDL_VIDEODRIVER="cocoa" ;;
    Linux)  export SDL_VIDEODRIVER="x11" ;;
    *)      export SDL_VIDEODRIVER="windib" ;;
esac

exec uv run python3 modalapistomp.py --host "emulator_${_version}" "$@"
