"""Connection domain model for parsed pedalboard graphs.

Pure logic — no lilv dependency — so it stays unit-testable. The lilv arc
walk that feeds into `build_connection` lives in `modalapi.pedalboard`.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

import common.token as Token
import common.util as util


HW_PORT_PREFIXES = ("capture_", "playback_", "serial_midi_", "midi_")


class EndpointKind(Enum):
    PLUGIN = "plugin"
    SOURCE = "source"  # capture_N (audio into the pedalboard)
    SINK = "sink"  # playback_N (audio out of the pedalboard)
    HW = "hw"  # other hardware ports (e.g. midi)


@dataclass(frozen=True)
class Endpoint:
    """One side of a connection. For plugins, ``id`` is the instance id
    (e.g. ``"ChorusI"``) and ``port_idx`` is the 0-based index within that
    plugin's audio in or out port list (TTL declaration order). For
    sources/sinks, ``id`` is the hardware port symbol and ``port_idx`` is 0.
    """

    kind: EndpointKind
    id: str
    port_symbol: str
    port_idx: int


@dataclass(frozen=True)
class Connection:
    src: Endpoint
    dst: Endpoint


def split_port_uri(port_uri: str, bundlepath: str) -> tuple[str, str]:
    """Strip bundle prefix and split a port URI into (endpoint_id, port_symbol).
    Examples:
        ".../bundle/ChorusI/out" -> ("ChorusI", "out")
        ".../bundle/capture_1"   -> ("capture_1", "")
    """
    rel = port_uri
    if "://" in rel:
        rel = rel.split("://", 1)[1]
    rel = urllib.parse.unquote(rel)
    bp = bundlepath.rstrip("/")
    if bp and bp in rel:
        rel = rel.split(bp, 1)[1].lstrip("/")
    if "/" in rel:
        endpoint_id, port_symbol = rel.split("/", 1)
        return endpoint_id, port_symbol
    return rel, ""


def classify_endpoint(endpoint_id: str) -> EndpointKind:
    if endpoint_id.startswith("capture_"):
        return EndpointKind.SOURCE
    if endpoint_id.startswith("playback_"):
        return EndpointKind.SINK
    if any(endpoint_id.startswith(p) for p in HW_PORT_PREFIXES):
        return EndpointKind.HW
    return EndpointKind.PLUGIN


def resolve_port_idx(
    kind: EndpointKind,
    endpoint_id: str,
    port_symbol: str,
    is_input: bool,
    plugin_info: Optional[dict],
) -> int:
    """Return the 0-based audio port index for ``port_symbol`` within the
    endpoint. For sources/sinks the suffix digit determines order
    (capture_1 -> 0, capture_2 -> 1). For plugins we look up the symbol in
    the plugin's TTL-ordered audio port list."""
    if kind in (EndpointKind.SOURCE, EndpointKind.SINK, EndpointKind.HW):
        digits = "".join(c for c in endpoint_id if c.isdigit())
        return max(0, int(digits) - 1) if digits else 0
    if plugin_info is None:
        return 0
    try:
        ports = plugin_info[Token.PORTS]["audio"]["input" if is_input else "output"]
    except (KeyError, TypeError):
        return 0
    for i, p in enumerate(ports):
        if util.DICT_GET(p, Token.SYMBOL) == port_symbol:
            return i
    return 0


def build_connection(
    tail_uri: str,
    head_uri: str,
    bundlepath: str,
    instance_to_info: dict[str, Optional[dict]],
) -> Connection:
    """Pure builder used by both the lilv arc walk and unit tests."""
    src_id, src_sym = split_port_uri(tail_uri, bundlepath)
    dst_id, dst_sym = split_port_uri(head_uri, bundlepath)
    src_kind = classify_endpoint(src_id)
    dst_kind = classify_endpoint(dst_id)
    src = Endpoint(
        kind=src_kind,
        id=src_id,
        port_symbol=src_sym,
        port_idx=resolve_port_idx(src_kind, src_id, src_sym, False, instance_to_info.get(src_id)),
    )
    dst = Endpoint(
        kind=dst_kind,
        id=dst_id,
        port_symbol=dst_sym,
        port_idx=resolve_port_idx(dst_kind, dst_id, dst_sym, True, instance_to_info.get(dst_id)),
    )
    return Connection(src=src, dst=dst)


def audio_connections(connections: Iterable[Connection]) -> list[Connection]:
    """Filter to audio-only connections (drop midi/HW ports)."""
    audio = {EndpointKind.PLUGIN, EndpointKind.SOURCE, EndpointKind.SINK}
    return [c for c in connections if c.src.kind in audio and c.dst.kind in audio]
