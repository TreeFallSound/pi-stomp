#!/usr/bin/env sh
# Run the layout analyser (build_layout_compress).
# Requires MOD Desktop running locally at http://127.0.0.1:18181: bundles are
# parsed by its /pedalboard/info, and plugin audio-port ordering resolved there.

exec uv run python3 tools/analyze_layout.py "$@"
