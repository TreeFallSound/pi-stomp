#!/usr/bin/env sh
# Launch the pi-stomp emulator, wiring in lilv if available outside the venv.

# Locate the lilv Python binding and shared library.
# Priority: pkg-config (Linux/macOS system install), then Homebrew.
_lilv_pypath=""
_lilv_libpath=""

if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists lilv-0 2>/dev/null; then
    _libdir=$(pkg-config --variable=libdir lilv-0)
    if [ -n "$_libdir" ]; then
        _lilv_libpath="$_libdir"
        # Look for a Python binding in the same prefix
        _prefix=$(pkg-config --variable=prefix lilv-0)
        for _pydir in "$_prefix"/lib/python*/site-packages; do
            if [ -f "$_pydir/lilv.py" ]; then
                _lilv_pypath="$_pydir"
                break
            fi
        done
    fi
fi

# Homebrew fallback (macOS)
if [ -z "$_lilv_pypath" ] && command -v brew >/dev/null 2>&1; then
    _brew_prefix=$(brew --prefix lilv 2>/dev/null)
    if [ -n "$_brew_prefix" ]; then
        _lilv_libpath="$_brew_prefix/lib"
        for _pydir in "$_brew_prefix"/lib/python*/site-packages; do
            if [ -f "$_pydir/lilv.py" ]; then
                _lilv_pypath="$_pydir"
                break
            fi
        done
    fi
fi

if [ -n "$_lilv_pypath" ]; then
    export PYTHONPATH="${_lilv_pypath}${PYTHONPATH:+:$PYTHONPATH}"
fi
if [ -n "$_lilv_libpath" ]; then
    # macOS uses DYLD_LIBRARY_PATH; Linux uses LD_LIBRARY_PATH
    case "$(uname -s)" in
        Darwin) export DYLD_LIBRARY_PATH="${_lilv_libpath}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" ;;
        *)      export LD_LIBRARY_PATH="${_lilv_libpath}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
    esac
fi

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
