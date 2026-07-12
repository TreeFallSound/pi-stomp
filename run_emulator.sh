#!/usr/bin/env sh
# Launch the pi-stomp emulator.

# Optional first argument: v1 / v2 / v3 (default: v3)
_version="${1:-v3}"
case "$_version" in
    v1|v2|v3) shift ;;
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
