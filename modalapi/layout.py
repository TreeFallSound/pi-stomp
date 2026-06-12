"""Layout pipeline for the routing-aware pedalboard grid.

Takes a flat list of plugins + parsed Connections (from modalapi.pedalboard)
and produces a Layout: a 2D column-major grid (with holes) and a normalised
edge list where every edge spans exactly one column.

Algorithm (Sugiyama-lite):
  1. Build a DAG over endpoints (plugins + capture/playback hardware ports).
  2. Longest-path layering: each node's column = longest path from any source.
  3. Insert dummy nodes for edges spanning >1 column so every edge is local.
  4. Barycentric sweeps to order rows within each layer (~4 passes,
     alternating direction) to reduce crossings.
  5. Assign integer rows; pad columns with None to form a rectangular grid.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from modalapi.connections import Connection, EndpointKind, audio_connections

NodeKind = Literal["plugin", "source", "sink", "dummy"]


@dataclass
class LayoutNode:
    """A cell in the grid. Plugin nodes carry the plugin instance id;
    source/sink carry the hardware port id (e.g. "capture_1"); dummies
    are anonymous waypoints that propagate an edge's src_port through a
    column."""

    id: str
    kind: NodeKind
    layer: int = -1
    row: int = -1
    # For dummies: which output port of the *original* source plugin this
    # dummy is carrying — preserves colour & lane assignment downstream.
    carried_src_port: int = 0


@dataclass(frozen=True)
class LayoutEdge:
    """A single-column-span edge. After dummy insertion, src.layer + 1 ==
    dst.layer always holds."""

    src: LayoutNode
    dst: LayoutNode
    src_port: int  # 0 or 1 — drives colour and lane
    dst_port: int  # 0 or 1 — drives y attachment on dst


@dataclass
class Layout:
    cols: list[list[Optional[LayoutNode]]] = field(default_factory=list)
    edges: list[LayoutEdge] = field(default_factory=list)

    @property
    def n_cols(self) -> int:
        return len(self.cols)

    @property
    def n_rows(self) -> int:
        return max((len(c) for c in self.cols), default=0)


# --------------------------------------------------------------------------- #
# Pipeline steps (pure, testable in isolation).
# --------------------------------------------------------------------------- #


def _kind_of(endpoint_kind: EndpointKind) -> NodeKind:
    match endpoint_kind:
        case EndpointKind.PLUGIN:
            return "plugin"
        case EndpointKind.SOURCE:
            return "source"
        case EndpointKind.SINK:
            return "sink"
        case _:
            raise ValueError(f"Cannot map {endpoint_kind} to a layout NodeKind")


def build_nodes(
    plugin_instance_ids: Iterable[str],
    connections: Iterable[Connection],
) -> dict[str, LayoutNode]:
    """Create one LayoutNode per plugin + per source/sink id appearing in
    the audio connections. Plugins with no connections still appear."""
    nodes: dict[str, LayoutNode] = {}
    for pid in plugin_instance_ids:
        norm = pid.lstrip("/")
        if norm:
            nodes[norm] = LayoutNode(id=norm, kind="plugin")
    for c in audio_connections(connections):
        for ep in (c.src, c.dst):
            if ep.id in nodes:
                continue
            nodes[ep.id] = LayoutNode(id=ep.id, kind=_kind_of(ep.kind))
    return nodes


def longest_path_layers(
    nodes: dict[str, LayoutNode],
    connections: Iterable[Connection],
) -> None:
    """Assign `layer` to every node via longest-path layering. Sources pin
    to layer 0; sinks pin to max_layer after the forward pass."""
    audio = audio_connections(connections)
    preds: dict[str, list[str]] = {nid: [] for nid in nodes}
    succs: dict[str, list[str]] = {nid: [] for nid in nodes}
    for c in audio:
        if c.src.id in nodes and c.dst.id in nodes:
            preds[c.dst.id].append(c.src.id)
            succs[c.src.id].append(c.dst.id)

    # Iterative longest-path on a DAG. LV2 pedalboard graphs are acyclic by
    # construction, so longest path ≤ N nodes — bound the loop accordingly
    # so a parser bug can't hang the UI thread.
    for n in nodes.values():
        n.layer = 0
    for _ in range(len(nodes) + 1):
        changed = False
        for nid, n in nodes.items():
            if not preds[nid]:
                continue
            new_layer = max(nodes[p].layer for p in preds[nid]) + 1
            if new_layer != n.layer:
                n.layer = new_layer
                changed = True
        if not changed:
            break
    else:
        logging.warning("layout.longest_path_layers: graph appears cyclic; rendering with partial assignment")

    # Pin sinks to the rightmost layer.
    max_layer = max((n.layer for n in nodes.values()), default=0)
    for n in nodes.values():
        if n.kind == "sink":
            n.layer = max_layer
    # If a sink is now further right than any predecessor produces, the
    # predecessors' layer is already correct (forward pass dominated).


def insert_dummies(
    nodes: dict[str, LayoutNode],
    connections: Iterable[Connection],
) -> tuple[dict[str, LayoutNode], list[LayoutEdge]]:
    """For each audio edge whose endpoints span >1 column, insert dummy
    LayoutNodes in the intermediate columns. Returns (nodes_with_dummies,
    layout_edges) where every LayoutEdge spans exactly one column."""
    out_nodes = dict(nodes)
    edges: list[LayoutEdge] = []
    dummy_counter = 0
    for c in audio_connections(connections):
        if c.src.id not in nodes or c.dst.id not in nodes:
            continue
        src_node = out_nodes[c.src.id]
        dst_node = out_nodes[c.dst.id]
        span = dst_node.layer - src_node.layer
        if span <= 0:
            # Skip back-edges and self-loops — shouldn't exist in a DAG
            # but be defensive.
            continue
        if span == 1:
            edges.append(LayoutEdge(src_node, dst_node, c.src.port_idx, c.dst.port_idx))
            continue
        # Insert dummies in each intermediate layer
        prev = src_node
        for offset in range(1, span):
            dummy_counter += 1
            d = LayoutNode(
                id=f"__dummy_{dummy_counter}",
                kind="dummy",
                layer=src_node.layer + offset,
                carried_src_port=c.src.port_idx,
            )
            out_nodes[d.id] = d
            edges.append(LayoutEdge(prev, d, c.src.port_idx, c.src.port_idx))
            prev = d
        edges.append(LayoutEdge(prev, dst_node, c.src.port_idx, c.dst.port_idx))
    return out_nodes, edges


def _layer_groups(nodes: dict[str, LayoutNode]) -> list[list[LayoutNode]]:
    if not nodes:
        return []
    max_layer = max(n.layer for n in nodes.values())
    groups: list[list[LayoutNode]] = [[] for _ in range(max_layer + 1)]
    for n in nodes.values():
        groups[n.layer].append(n)
    return groups


def barycentric_order(
    nodes: dict[str, LayoutNode],
    edges: list[LayoutEdge],
    sweeps: int = 4,
) -> None:
    """Assign integer `row` to each node, minimising edge crossings via a
    standard barycentric heuristic. Mutates node.row in place."""
    groups = _layer_groups(nodes)

    # Initial row = order of first appearance within the layer.
    for layer in groups:
        for i, n in enumerate(layer):
            n.row = i

    preds: dict[str, list[LayoutNode]] = {nid: [] for nid in nodes}
    succs: dict[str, list[LayoutNode]] = {nid: [] for nid in nodes}
    for e in edges:
        succs[e.src.id].append(e.dst)
        preds[e.dst.id].append(e.src)

    def sort_by(neighbors_of: dict[str, list[LayoutNode]], layer: list[LayoutNode]) -> None:
        def barycentre(n: LayoutNode) -> float:
            ns = neighbors_of[n.id]
            return sum(x.row for x in ns) / len(ns) if ns else n.row

        layer.sort(key=barycentre)
        for i, n in enumerate(layer):
            n.row = i

    for sweep in range(sweeps):
        if sweep % 2 == 0:
            # Left -> right: order each layer by its predecessors' rows.
            for layer in groups[1:]:
                sort_by(preds, layer)
        else:
            # Right -> left: order each layer by its successors' rows.
            for layer in reversed(groups[:-1]):
                sort_by(succs, layer)


def _compact_hw_only_columns(
    nodes: dict[str, LayoutNode],
    edges: list[LayoutEdge],
) -> tuple[dict[str, LayoutNode], list[LayoutEdge]]:
    """Drop all source/sink nodes (and any column they leave empty) and
    renumber remaining layers contiguously. Edges touching dropped nodes are
    removed — wires from capture/to playback aren't visualised today; the
    leftmost plugin's input port already implies "audio in", same for outputs.

    We drop hw nodes *unconditionally*, not just hw-only columns: a leaf
    plugin pinned at layer 0 alongside capture nodes would otherwise leave
    a phantom row where a wire emanates from an invisible source cell.
    """
    kept_nodes = {nid: n for nid, n in nodes.items() if n.kind in ("plugin", "dummy")}
    groups = _layer_groups(kept_nodes)
    keep_layers = [i for i, g in enumerate(groups) if g]
    old_to_new = {old: new for new, old in enumerate(keep_layers)}
    for n in kept_nodes.values():
        n.layer = old_to_new[n.layer]
    kept_edges = [e for e in edges if e.src.id in kept_nodes and e.dst.id in kept_nodes]
    return kept_nodes, kept_edges


def build_layout(
    plugin_instance_ids: Iterable[str],
    connections: Iterable[Connection],
) -> Layout:
    """End-to-end: plugins + connections → Layout."""
    base_nodes = build_nodes(plugin_instance_ids, connections)
    longest_path_layers(base_nodes, connections)
    nodes, edges = insert_dummies(base_nodes, connections)
    barycentric_order(nodes, edges)
    nodes, edges = _compact_hw_only_columns(nodes, edges)
    # Re-pack rows after dropping hardware-only layers so each layer starts at row 0.
    for layer in _layer_groups(nodes):
        layer.sort(key=lambda n: n.row)
        for i, n in enumerate(layer):
            n.row = i

    groups = _layer_groups(nodes)
    n_rows = max((len(g) for g in groups), default=0)
    cols: list[list[Optional[LayoutNode]]] = []
    for layer in groups:
        col: list[Optional[LayoutNode]] = [None] * n_rows
        for n in layer:
            col[n.row] = n
        cols.append(col)
    return Layout(cols=cols, edges=edges)
