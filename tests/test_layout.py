"""Tests for the routing layout pipeline (modalapi.layout)."""

from modalapi.layout import (
    build_layout,
    build_nodes,
    insert_dummies,
    longest_path_layers,
)
from modalapi.connections import Connection, Endpoint, EndpointKind


def _ep(kind: EndpointKind, id_: str, port_idx: int = 0) -> Endpoint:
    return Endpoint(kind=kind, id=id_, port_symbol="", port_idx=port_idx)


def _conn(
    src_id: str,
    dst_id: str,
    src_kind: EndpointKind = EndpointKind.PLUGIN,
    dst_kind: EndpointKind = EndpointKind.PLUGIN,
    src_port: int = 0,
    dst_port: int = 0,
) -> Connection:
    return Connection(src=_ep(src_kind, src_id, src_port), dst=_ep(dst_kind, dst_id, dst_port))


# --------------------------------------------------------------------------- #
# Linear chain: capture_1 -> A -> B -> C -> playback_1
# --------------------------------------------------------------------------- #


def test_linear_chain_layering() -> None:
    conns = [
        _conn("capture_1", "A", EndpointKind.SOURCE, EndpointKind.PLUGIN),
        _conn("A", "B"),
        _conn("B", "C"),
        _conn("C", "playback_1", EndpointKind.PLUGIN, EndpointKind.SINK),
    ]
    nodes = build_nodes(["A", "B", "C"], conns)
    longest_path_layers(nodes, conns)
    assert nodes["capture_1"].layer == 0
    assert nodes["A"].layer == 1
    assert nodes["B"].layer == 2
    assert nodes["C"].layer == 3
    assert nodes["playback_1"].layer == 4


def test_linear_chain_full_layout_has_no_dummies() -> None:
    conns = [
        _conn("capture_1", "A", EndpointKind.SOURCE, EndpointKind.PLUGIN),
        _conn("A", "B"),
        _conn("B", "playback_1", EndpointKind.PLUGIN, EndpointKind.SINK),
    ]
    layout = build_layout(["A", "B"], conns)
    # Hardware-only columns (capture_1, playback_1) are compacted out.
    assert layout.n_cols == 2
    assert layout.n_rows == 1
    assert all(c[0] is not None for c in layout.cols)
    assert not any(n.kind == "dummy" for n in (c[0] for c in layout.cols) if n)


# --------------------------------------------------------------------------- #
# Skip-layer edge needs dummies.
# --------------------------------------------------------------------------- #


def test_skip_layer_edge_inserts_dummies() -> None:
    # A bypass that jumps two columns: A -> D, plus A -> B -> C -> D
    conns = [
        _conn("A", "B"),
        _conn("B", "C"),
        _conn("C", "D"),
        _conn("A", "D"),  # spans 3 columns
    ]
    nodes = build_nodes(["A", "B", "C", "D"], conns)
    longest_path_layers(nodes, conns)
    assert nodes["A"].layer == 0
    assert nodes["D"].layer == 3
    expanded, edges = insert_dummies(nodes, conns)
    dummies = [n for n in expanded.values() if n.kind == "dummy"]
    assert len(dummies) == 2  # two intermediate columns
    # Every edge spans exactly one layer
    for e in edges:
        assert e.dst.layer - e.src.layer == 1


# --------------------------------------------------------------------------- #
# 2-in/2-out: stereo plugin propagates port_idx through chain.
# --------------------------------------------------------------------------- #


def test_stereo_ports_preserved_in_edges() -> None:
    # Insert a plugin on each side of S so the stereo edges stay between
    # plugins (HW-only columns are compacted away).
    conns = [
        _conn("In", "S", src_port=0, dst_port=0),
        _conn("In", "S", src_port=1, dst_port=1),
        _conn("S", "Out", src_port=0, dst_port=0),
        _conn("S", "Out", src_port=1, dst_port=1),
    ]
    layout = build_layout(["In", "S", "Out"], conns)
    out_edges = [e for e in layout.edges if e.src.id == "S"]
    assert {(e.src_port, e.dst_port) for e in out_edges} == {(0, 0), (1, 1)}
    in_edges = [e for e in layout.edges if e.dst.id == "S"]
    assert {(e.src_port, e.dst_port) for e in in_edges} == {(0, 0), (1, 1)}


def test_dummy_carries_src_port_for_colour() -> None:
    # A's OUT1 jumps two columns to D — dummy must carry src_port=1
    conns = [
        _conn("A", "B"),
        _conn("B", "C"),
        _conn("C", "D"),
        _conn("A", "D", src_port=1, dst_port=1),
    ]
    nodes = build_nodes(["A", "B", "C", "D"], conns)
    longest_path_layers(nodes, conns)
    expanded, edges = insert_dummies(nodes, conns)
    dummies = [n for n in expanded.values() if n.kind == "dummy"]
    assert dummies and all(d.carried_src_port == 1 for d in dummies)
    # Every edge in the dummy chain must propagate src_port=1
    chain = [e for e in edges if e.src.kind == "dummy" or e.dst.kind == "dummy"]
    assert chain and all(e.src_port == 1 for e in chain)


# --------------------------------------------------------------------------- #
# Branch + merge: ordering should keep rows distinct.
# --------------------------------------------------------------------------- #


def test_parallel_branches_get_distinct_rows() -> None:
    conns = [
        _conn("capture_1", "A", EndpointKind.SOURCE, EndpointKind.PLUGIN),
        _conn("capture_1", "B", EndpointKind.SOURCE, EndpointKind.PLUGIN),
        _conn("A", "M"),
        _conn("B", "M"),
        _conn("M", "playback_1", EndpointKind.PLUGIN, EndpointKind.SINK),
    ]
    layout = build_layout(["A", "B", "M"], conns)
    # A and B are in the same column with distinct rows
    col_idx = next(i for i, c in enumerate(layout.cols) if any(n and n.id == "A" for n in c))
    rows = sorted(n.row for n in layout.cols[col_idx] if n and n.kind == "plugin")
    assert rows == [0, 1]


def test_isolated_plugin_still_appears() -> None:
    """Plugin with no audio connections must not be lost from the layout."""
    layout = build_layout(["Orphan"], [])
    flat = [n for c in layout.cols for n in c if n]
    assert any(n.id == "Orphan" for n in flat)


# --------------------------------------------------------------------------- #
# Grid structure: holes become explicit Nones.
# --------------------------------------------------------------------------- #


def test_grid_is_rectangular_with_none_holes() -> None:
    conns = [
        _conn("capture_1", "A", EndpointKind.SOURCE, EndpointKind.PLUGIN),
        _conn("capture_1", "B", EndpointKind.SOURCE, EndpointKind.PLUGIN),
        _conn("A", "M"),
        _conn("B", "M"),
    ]
    layout = build_layout(["A", "B", "M"], conns)
    assert layout.n_rows >= 2
    # All columns padded to n_rows
    assert all(len(c) == layout.n_rows for c in layout.cols)
    # At least one None should exist (M's column has 1 plugin in a 2-row grid)
    flattened = [n for c in layout.cols for n in c]
    assert None in flattened
