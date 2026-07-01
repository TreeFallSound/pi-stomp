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
from modalapi.plugin_customization import PluginExtraData


@dataclass
class MockPlugin:
    instance_id: str
    category: str = "Distortion"
    has_footswitch: bool = False
    bypassed: bool = False
    controllers: list = field(default_factory=list)
    uri: str | None = None
    extra_data: PluginExtraData | None = None

    @property
    def display_name(self) -> str:
        return self.instance_id.replace("_", "")

    @property
    def subtitle(self) -> str | None:
        return None

    @property
    def tile_active_color(self) -> tuple[int, int, int] | None:
        return None

    @property
    def tile_border(self):
        return None

    @property
    def panel_cls(self):
        return None

    @property
    def intercept_shortpress(self) -> bool:
        return False

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


def tall_parallel() -> MockPedalboard:
    """Five parallel lanes of varying depth coalescing into x42-eq.
    Five rows in col 0 exercises footswitch-panel occlusion; shorter lanes
    skip ahead via dummies, producing vertical segments in the merge gutters.

    Lane 1 (depth 3): Gate → Amp → Cab ────────────────────────┐
    Lane 2 (depth 2): Comp → Drive ──────────(dummy)───────────┤
    Lane 3 (depth 2): EQ   → Delay ──────────(dummy)───────────┤→ x42-eq → playback
    Lane 4 (depth 1): Reverb ────────────────(dummies)─────────┤
    Lane 5 (depth 1): Chorus ────────────────(dummies)─────────┘
    """
    plugins = [
        MockPlugin("gate", "Dynamics", has_footswitch=True),
        MockPlugin("amp", "Amplifier", has_footswitch=True),
        MockPlugin("cab", "Utility"),
        MockPlugin("comp", "Dynamics", has_footswitch=True),
        MockPlugin("drive", "Distortion", has_footswitch=True),
        MockPlugin("eq", "EQ"),
        MockPlugin("delay", "Delay", has_footswitch=True),
        MockPlugin("reverb", "Reverb", has_footswitch=True),
        MockPlugin("chorus", "Modulator", has_footswitch=True),
        MockPlugin("x42-eq", "EQ"),
    ]
    conns = [
        # Lane 1 (depth 3)
        Connection(src=_source_ep(1), dst=_plugin_ep("gate")),
        Connection(src=_plugin_ep("gate"), dst=_plugin_ep("amp")),
        Connection(src=_plugin_ep("amp"), dst=_plugin_ep("cab")),
        Connection(src=_plugin_ep("cab"), dst=_plugin_ep("x42-eq")),
        # Lane 2 (depth 2)
        Connection(src=_source_ep(1), dst=_plugin_ep("comp")),
        Connection(src=_plugin_ep("comp"), dst=_plugin_ep("drive")),
        Connection(src=_plugin_ep("drive"), dst=_plugin_ep("x42-eq")),
        # Lane 3 (depth 2)
        Connection(src=_source_ep(1), dst=_plugin_ep("eq")),
        Connection(src=_plugin_ep("eq"), dst=_plugin_ep("delay")),
        Connection(src=_plugin_ep("delay"), dst=_plugin_ep("x42-eq")),
        # Lane 4 (depth 1)
        Connection(src=_source_ep(1), dst=_plugin_ep("reverb")),
        Connection(src=_plugin_ep("reverb"), dst=_plugin_ep("x42-eq")),
        # Lane 5 (depth 1)
        Connection(src=_source_ep(1), dst=_plugin_ep("chorus")),
        Connection(src=_plugin_ep("chorus"), dst=_plugin_ep("x42-eq")),
        # Output
        Connection(src=_plugin_ep("x42-eq"), dst=_sink_ep(1)),
        Connection(src=_plugin_ep("x42-eq"), dst=_sink_ep(2)),
    ]
    return MockPedalboard(title="Tall Parallel", plugins=plugins, connections=conns)


def stereo_chain() -> MockPedalboard:
    """Full stereo signal through three plugins — both lanes occupied in every gutter:

    capture_1 → EQ(0) → Comp(0) → Limit(0) → playback_1
    capture_2 → EQ(1) → Comp(1) → Limit(1) → playback_2
    """
    plugins = [
        MockPlugin("eq", "EQ", has_footswitch=True),
        MockPlugin("comp", "Dynamics", has_footswitch=True),
        MockPlugin("limit", "Dynamics"),
    ]
    conns = [
        Connection(src=_source_ep(1), dst=_plugin_ep("eq")),
        Connection(src=_source_ep(2), dst=_plugin_ep("eq", 1)),
        Connection(src=_plugin_ep("eq"), dst=_plugin_ep("comp")),
        Connection(src=_plugin_ep("eq", 1), dst=_plugin_ep("comp", 1)),
        Connection(src=_plugin_ep("comp"), dst=_plugin_ep("limit")),
        Connection(src=_plugin_ep("comp", 1), dst=_plugin_ep("limit", 1)),
        Connection(src=_plugin_ep("limit"), dst=_sink_ep(1)),
        Connection(src=_plugin_ep("limit", 1), dst=_sink_ep(2)),
    ]
    return MockPedalboard(title="Stereo Chain", plugins=plugins, connections=conns)


def split_merge() -> MockPedalboard:
    """A splitter plugin fans out to two parallel processors that merge back.
    This is the minimal topology that produces vertical wire segments.

    capture → Split(0) → Delay(0) → Merge(0) → playback_1
              Split(1) → Reverb(0) → Merge(1) → playback_2

    Gutter 0: two-lane (port 0 straight, port 1 drops to row 1).
    Gutter 1: single-lane centered (both sources on port 0, rises from row 1 back to row 0).
    """
    plugins = [
        MockPlugin("split", "Utility"),
        MockPlugin("delay", "Delay", has_footswitch=True),
        MockPlugin("reverb", "Reverb", has_footswitch=True),
        MockPlugin("merge", "Utility"),
    ]
    conns = [
        Connection(src=_source_ep(1), dst=_plugin_ep("split")),
        Connection(src=_plugin_ep("split"), dst=_plugin_ep("delay")),
        Connection(src=_plugin_ep("split", 1), dst=_plugin_ep("reverb")),
        Connection(src=_plugin_ep("delay"), dst=_plugin_ep("merge")),
        Connection(src=_plugin_ep("reverb"), dst=_plugin_ep("merge", 1)),
        Connection(src=_plugin_ep("merge"), dst=_sink_ep(1)),
        Connection(src=_plugin_ep("merge", 1), dst=_sink_ep(2)),
    ]
    return MockPedalboard(title="Split Merge", plugins=plugins, connections=conns)


def parallel_beths() -> MockPedalboard:
    """7-plugin parallel rig: 3 lanes of depth 3/2/1 + shared MixEQ merger.

    Each lane feeds a common MixEQ before the outputs.  The varying lane
    depths exercise dummy-node insertion (col2 and col3 need bridge segments
    for the shorter lanes) and barycentric row tie-breaking.

    Layout:
    capture_1 ──┬── Comp → Amp → Delay ──┐
                ├── OD → Chorus           ──┤→ MixEQ → playback_{1,2}
                └── Gate                  ──┘
    """
    # (instance_id, category, has_footswitch, bypassed)
    _LANES: list[list[tuple[str, str, bool, bool]]] = [
        # Lane A – Clean (depth 3)
        [("Comp", "Dynamics", True, False), ("Amp", "Amplifier", True, False), ("Delay", "Delay", True, False)],
        # Lane B – Crunch (depth 2; Chorus bypassed)
        [("OD", "Distortion", True, False), ("Chorus", "Modulator", True, True)],
        # Lane C – Gate only (depth 1)
        [("Gate", "Dynamics", False, False)],
    ]

    lane_plugins: list[list[MockPlugin]] = [
        [MockPlugin(iid, cat, fs, byp) for iid, cat, fs, byp in lane] for lane in _LANES
    ]
    mix_eq = MockPlugin("MixEQ", "EQ", False, False)
    all_plugins: list[MockPlugin] = [p for lane in lane_plugins for p in lane] + [mix_eq]
    assert len(all_plugins) == 7, f"expected 7, got {len(all_plugins)}"

    conns: list[Connection] = []
    for lane in lane_plugins:
        ids = [p.instance_id for p in lane]
        conns.append(Connection(src=_source_ep(1), dst=_plugin_ep(ids[0])))
        for a, b in zip(ids, ids[1:]):
            conns.append(Connection(src=_plugin_ep(a), dst=_plugin_ep(b)))
        conns.append(Connection(src=_plugin_ep(ids[-1]), dst=_plugin_ep("MixEQ")))
    conns.append(Connection(src=_plugin_ep("MixEQ"), dst=_sink_ep(1)))
    conns.append(Connection(src=_plugin_ep("MixEQ"), dst=_sink_ep(2)))

    return MockPedalboard(title="Parallel Beths", plugins=all_plugins, connections=conns)


REGISTRY: dict[str, Callable[[], MockPedalboard]] = {
    "blank": blank,
    "linear": linear_chain,
    "parallel": parallel_branches,
    "tall_parallel": tall_parallel,
    "stereo_chain": stereo_chain,
    "split_merge": split_merge,
    "parallel_beths": parallel_beths,
}
