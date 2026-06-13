#!/usr/bin/env sh
# Run the layout analyser (build_layout_compress), wiring in lilv the same way
# run_emulator.sh does.
# Requires MOD Desktop running locally at http://127.0.0.1:18181 so plugin
# audio-port ordering can be resolved.

# Locate the lilv Python binding and shared library.
# Priority: pkg-config (Linux/macOS system install), then Homebrew.
_lilv_pypath=""
_lilv_libpath=""

if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists lilv-0 2>/dev/null; then
    _libdir=$(pkg-config --variable=libdir lilv-0)
    if [ -n "$_libdir" ]; then
        _lilv_libpath="$_libdir"
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
    case "$(uname -s)" in
        Darwin) export DYLD_LIBRARY_PATH="${_lilv_libpath}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" ;;
        *)      export LD_LIBRARY_PATH="${_lilv_libpath}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
    esac
fi

exec uv run python3 tools/analyze_layout.py "$@"
