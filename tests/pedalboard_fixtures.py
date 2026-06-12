"""Pedalboard fixtures for tests that need realistic plugin graphs.

The default lcd mocks use empty connection lists, which makes the routing-
aware GridPanel collapse every plugin into column 0. Tests that want to
exercise multi-column layouts, parallel branches, or stereo splits opt into
one of the topologies here.

Each helper returns a `MockPedalboard` exposing the duck-typed attributes
used by `lcd320x240.draw_plugins`: `title`, `plugins` (with `instance_id`,
`is_bypassed()`, `category`, `has_footswitch`, `controllers`), and
`connections` (a list of `modalapi.connections.Connection`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from modalapi.connections import Connection, Endpoint, EndpointKind


@dataclass
class MockPlugin:
    instance_id: str
    category: str = "Distortion"
    has_footswitch: bool = False
    bypassed: bool = False
    controllers: list = field(default_factory=list)

    def is_bypassed(self) -> bool:
        return self.bypassed


@dataclass
class MockPedalboard:
    title: str
    plugins: list[MockPlugin]
    connections: list[Connection]


# --------------------------------------------------------------------------- #
# Connection helpers.
# --------------------------------------------------------------------------- #


def _plugin_ep(pid: str, port_idx: int = 0) -> Endpoint:
    return Endpoint(kind=EndpointKind.PLUGIN, id=pid, port_symbol="", port_idx=port_idx)


def _source_ep(idx: int = 1) -> Endpoint:
    return Endpoint(kind=EndpointKind.SOURCE, id=f"capture_{idx}", port_symbol="", port_idx=idx - 1)


def _sink_ep(idx: int = 1) -> Endpoint:
    return Endpoint(kind=EndpointKind.SINK, id=f"playback_{idx}", port_symbol="", port_idx=idx - 1)


def _mono_chain(plugin_ids: list[str]) -> list[Connection]:
    """capture_1 → p0 → p1 → … → pN → playback_1 (+ playback_2 from last)."""
    if not plugin_ids:
        return [Connection(src=_source_ep(1), dst=_sink_ep(1))]
    edges = [Connection(src=_source_ep(1), dst=_plugin_ep(plugin_ids[0]))]
    for a, b in zip(plugin_ids, plugin_ids[1:]):
        edges.append(Connection(src=_plugin_ep(a), dst=_plugin_ep(b)))
    edges.append(Connection(src=_plugin_ep(plugin_ids[-1]), dst=_sink_ep(1)))
    edges.append(Connection(src=_plugin_ep(plugin_ids[-1]), dst=_sink_ep(2)))
    return edges


# --------------------------------------------------------------------------- #
# Topologies.
# --------------------------------------------------------------------------- #


def blank() -> MockPedalboard:
    """No plugins. GridPanel renders only source/sink (which are hidden)."""
    return MockPedalboard(title="Blank", plugins=[], connections=[])


def linear_chain() -> MockPedalboard:
    """Classic serial chain: distort → delay → reverb → chorus."""
    plugins = [
        MockPlugin("distortion", "Distortion", has_footswitch=True),
        MockPlugin("delay", "Delay", has_footswitch=True),
        MockPlugin("reverb", "Reverb", has_footswitch=True, bypassed=True),
        MockPlugin("chorus", "Modulator", has_footswitch=False),
    ]
    return MockPedalboard(
        title="Rock Rig",
        plugins=plugins,
        connections=_mono_chain([p.instance_id for p in plugins]),
    )


def parallel_branches() -> MockPedalboard:
    """Splitter feeds two parallel chains that merge at the output:

        capture_1 ─┬─ A ─ B ─┐
                   └─ C ─ D ─┴─ playback_{1,2}
    """
    plugins = [
        MockPlugin("A", "Filter"),
        MockPlugin("B", "Delay"),
        MockPlugin("C", "Filter"),
        MockPlugin("D", "Reverb"),
    ]
    conns = [
        Connection(src=_source_ep(1), dst=_plugin_ep("A")),
        Connection(src=_source_ep(1), dst=_plugin_ep("C")),
        Connection(src=_plugin_ep("A"), dst=_plugin_ep("B")),
        Connection(src=_plugin_ep("C"), dst=_plugin_ep("D")),
        Connection(src=_plugin_ep("B"), dst=_sink_ep(1)),
        Connection(src=_plugin_ep("D"), dst=_sink_ep(2)),
    ]
    return MockPedalboard(title="Parallel", plugins=plugins, connections=conns)


def stereo_split() -> MockPedalboard:
    """Stereo plugin S sends OUT1 → playback_1 and OUT2 → playback_2."""
    plugins = [MockPlugin("S", "Utility")]
    conns = [
        Connection(src=_source_ep(1), dst=_plugin_ep("S")),
        Connection(src=Endpoint(EndpointKind.PLUGIN, "S", "", 0), dst=_sink_ep(1)),
        Connection(src=Endpoint(EndpointKind.PLUGIN, "S", "", 1), dst=_sink_ep(2)),
    ]
    return MockPedalboard(title="Stereo", plugins=plugins, connections=conns)


REGISTRY: dict[str, Callable[[], MockPedalboard]] = {
    "blank": blank,
    "linear": linear_chain,
    "parallel": parallel_branches,
    "stereo": stereo_split,
}
