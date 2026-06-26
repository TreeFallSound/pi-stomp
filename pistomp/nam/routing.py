"""Save and restore JACK connections on the FX-loop ports.

When a NAM capture starts, we snapshot the existing connections on
system:playback_2 (FX send) and system:capture_2 (FX return), disconnect
them, wire our player/recorder instead, then restore the original connections
when done. Routing is always restored in a try/finally, so a crash or board
change never leaves the user's audio broken.

Pattern mirrors modalapi/jack_mute.py.
"""

from __future__ import annotations

import subprocess
import logging

# Default FX-loop JACK port names. Override via settings if different hardware.
FX_SEND_PORT = "system:playback_2"  # JACK input: we drive audio into the pedal
FX_RETURN_PORT = "system:capture_2"  # JACK output: pedal's output comes back here

# Monitoring: FX return → main output so the user can hear the amp while capturing.
MONITOR_OUT_PORT = "system:playback_1"

# Saved connections: list of (src_port, dst_port) pairs for jack_connect
Saved = list[tuple[str, str]]


def snapshot(
    send_port: str = FX_SEND_PORT,
    return_port: str = FX_RETURN_PORT,
) -> Saved:
    """Return the current (src, dst) connection pairs for the FX-loop ports."""
    # playback_2 is a JACK input: listed connections are its source (output) ports
    send_srcs = _lsp_connections(send_port)
    # capture_2 is a JACK output: listed connections are its destination (input) ports
    return_dsts = _lsp_connections(return_port)
    return [(s, send_port) for s in send_srcs] + [(return_port, d) for d in return_dsts]


def clear(
    send_port: str = FX_SEND_PORT,
    return_port: str = FX_RETURN_PORT,
) -> None:
    """Disconnect all connections on the FX-loop ports."""
    for src in _lsp_connections(send_port):
        _run("jack_disconnect", src, send_port)
    for dst in _lsp_connections(return_port):
        _run("jack_disconnect", return_port, dst)


def restore(saved: Saved) -> None:
    """Reconnect the saved (src, dst) pairs."""
    for src, dst in saved:
        _run("jack_connect", src, dst)


def _lsp_connections(port: str) -> list[str]:
    """Return ports connected to/from *port* via jack_lsp -c."""
    try:
        out = subprocess.check_output(["jack_lsp", "-c", port], stderr=subprocess.DEVNULL, text=True, timeout=2.0)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logging.warning("jack_lsp failed for %s: %s", port, exc)
        return []
    # Output format: port name on its own line, connections indented below it.
    return [line.strip() for line in out.splitlines() if line.startswith((" ", "\t"))]


def connect_monitor(
    return_port: str = FX_RETURN_PORT,
    monitor_out: str = MONITOR_OUT_PORT,
) -> None:
    """Connect the FX return to the main output so the user can hear the amp."""
    _run("jack_connect", return_port, monitor_out)


def disconnect_monitor(
    return_port: str = FX_RETURN_PORT,
    monitor_out: str = MONITOR_OUT_PORT,
) -> None:
    """Remove the FX return → main output monitoring connection."""
    _run("jack_disconnect", return_port, monitor_out)


def _run(tool: str, src: str, dst: str) -> None:
    try:
        subprocess.call([tool, src, dst], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logging.warning("%s %s %s failed: %s", tool, src, dst, exc)
