"""Layout pipeline for the routing-aware pedalboard grid.

Takes a flat list of plugins + parsed Connections (from modalapi.pedalboard)
and produces a Layout: a 2D column-major grid (with holes) and a normalised
edge list where every edge spans exactly one column.

Algorithm (column-compression DP):
  1. Build a DAG over endpoints (plugins + capture/playback hardware ports).
  2. Longest-path layering: each node's column = longest path from any source.
  3. Insert dummy nodes for edges spanning >1 column so every edge is local.
  4. Barycentric sweeps to order rows within each layer (~4 passes,
     alternating direction) to reduce crossings.
  5. Merge contiguous layers into columns via a cut-point DP that minimises
     routing violations while keeping the grid within the viewport.
  6. Assign integer rows; pad columns with None to form a rectangular grid.
"""

from __future__ import annotations

import logging

from collections import defaultdict, deque
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


# --------------------------------------------------------------------------- #
# Heuristic (shared with the analysis tooling).
# --------------------------------------------------------------------------- #


def empty_fraction(layout: Layout) -> float:
    """Fraction of the bounding-box cells that are NOT plugin tiles (gaps +
    dummies). 0.0 == perfectly packed."""
    total = layout.n_cols * layout.n_rows
    if total == 0:
        return 0.0
    filled = sum(1 for col in layout.cols for n in col if n is not None and n.kind == "plugin")
    return (total - filled) / total


# --------------------------------------------------------------------------- #
# Invariant-1 router (the feasibility oracle).
#
# Routing model: horizontal runs travel through a row's *cells* and may only
# cross GAP cells; vertical moves / turns happen in the column gutters and are
# free. So a wire is a monotone staircase: slide vertically (free), step right
# only into a gap cell (or the destination). Leftward steps are banned
# (invariant 2). Consequence: an edge is unroutable iff some column it must
# cross is fully packed — gaps are the routing medium.
# --------------------------------------------------------------------------- #


def occupied_cells(layout: Layout) -> set[tuple[int, int]]:
    return {
        (c, r) for c, col in enumerate(layout.cols) for r, n in enumerate(col) if n is not None and n.kind == "plugin"
    }


def route_edge(
    layout: Layout, edge: LayoutEdge, occupied: Optional[set[tuple[int, int]]] = None
) -> Optional[list[tuple[int, int]]]:
    """Shortest invariant-1-legal staircase from src to dst as a list of cells,
    or None if no legal route exists. Vertical moves are free (gutters); a
    rightward move is allowed only into a gap cell or the destination."""
    if occupied is None:
        occupied = occupied_cells(layout)
    src = (edge.src.layer, edge.src.row)
    dst = (edge.dst.layer, edge.dst.row)
    if src == dst:
        return [src]

    n_rows = layout.n_rows
    prev: dict[tuple[int, int], Optional[tuple[int, int]]] = {src: None}
    q = deque([src])
    while q:
        c, r = q.popleft()
        if (c, r) == dst:
            path = [(c, r)]
            cur = prev[(c, r)]
            while cur is not None:
                path.append(cur)
                cur = prev[cur]
            return path[::-1]
        nbrs: list[tuple[int, int]] = []
        if r > 0:
            nbrs.append((c, r - 1))  # vertical: free
        if r < n_rows - 1:
            nbrs.append((c, r + 1))  # vertical: free
        if c < dst[0]:  # rightward only, not past dst
            right = (c + 1, r)
            if right == dst or right not in occupied:
                nbrs.append(right)
        for nb in nbrs:
            if nb not in prev:
                prev[nb] = (c, r)
                q.append(nb)
    return None


def routing_violations(layout: Layout) -> int:
    """Count edges with no invariant-1-legal route under the current placement.

    Cross-column edges are blocked by a fully-packed column they must cross
    (`route_edge`). Within-column edges (span 0, produced by column compression)
    have no gutter to travel in yet, so they're blocked when an occupied tile
    sits strictly between their endpoint rows — a wire through an intervening
    plugin. Once the renderer gutter-routes within-column skips, this clause
    can relax to a lane-pressure cost."""
    occ = occupied_cells(layout)
    n = 0
    for e in layout.edges:
        if e.src.layer == e.dst.layer:
            c = e.src.layer
            lo, hi = sorted((e.src.row, e.dst.row))
            if any((c, r) in occ for r in range(lo + 1, hi)):
                n += 1
            continue
        if route_edge(layout, e, occ) is None:
            n += 1
    return n


def layout_cost(
    layout: Layout,
    height_cap: int = 4,
    viewport_cols: int = 4,
    width_penalty: float = 10.0,
    over_penalty: float = 10.0,
    row_weight: float = 0.1,
    infeasible_penalty: float = 1000.0,
    span_weight: float = 0.05,
) -> float:
    """Heuristic the search minimises.

    - **Infeasibility** (edges with no invariant-1 route) dominates: an illegal
      layout is never preferred to a legal one.
    - **Overflow** is the primary legal objective: only columns beyond the
      `viewport_cols`-wide screen — and rows beyond `height_cap` — cost. Width
      *within* the viewport is free, so a chain that already fits (e.g. 4x1) is
      never folded narrower-and-taller just to shed columns.
    - **Rows** carry a mild weight so, among layouts that fit the viewport
      width, the search fills columns before wrapping (4x2 beats 2x4) and a
      short chain stays a flat row rather than a tall stack.
    - **Span** of multi-column edges is mildly penalised, since each crossed
      column must keep a gap to stay routable — short edges need fewer gaps.
    - `empty_fraction` (< 1) breaks remaining ties toward the denser layout.
    """
    width_over = max(0, layout.n_cols - viewport_cols)
    height_over = max(0, layout.n_rows - height_cap)
    span = sum(max(0, e.dst.layer - e.src.layer - 1) for e in layout.edges)
    return (
        width_penalty * width_over
        + over_penalty * height_over
        + row_weight * layout.n_rows
        + empty_fraction(layout)
        + infeasible_penalty * routing_violations(layout)
        + span_weight * span
    )


def _route_dp_edges(layout: Layout) -> None:
    """Split each multi-column edge into single-column hops through dummy
    waypoints placed in gap cells, so the gutter renderer draws *around*
    plugins instead of hiding the wire behind them. Single-column and
    vertical (span-0) edges are left untouched.

    Mutates ``layout.edges`` in place. Dummies live only on the edges, not in
    ``layout.cols`` — they don't render as tiles or count as occupied cells.
    A column with no gap leaves its dummy on a plugin cell (the unavoidable
    through-plugin case the heuristic is trying to avoid); the analyzer's
    violation count detects exactly that.
    """
    occ = occupied_cells(layout)
    n_rows = layout.n_rows
    routed: list[LayoutEdge] = []
    dummy_n = 0
    for e in layout.edges:
        span = e.dst.layer - e.src.layer
        if span <= 1:
            routed.append(e)
            continue
        prev, prev_row = e.src, e.src.row
        for c in range(e.src.layer + 1, e.dst.layer):
            # Aim at the straight-line interpolation; snap to the nearest gap
            # (tie-break toward the previous hop's row for a tidier staircase).
            ideal = round(e.src.row + (c - e.src.layer) / span * (e.dst.row - e.src.row))
            gaps = [r for r in range(n_rows) if (c, r) not in occ]
            row = min(gaps, key=lambda r: (abs(r - ideal), abs(r - prev_row))) if gaps else ideal
            dummy_n += 1
            d = LayoutNode(id=f"__dpdummy_{dummy_n}", kind="dummy", layer=c, row=row, carried_src_port=e.src_port)
            routed.append(LayoutEdge(prev, d, e.src_port, e.src_port))
            prev, prev_row = d, row
        routed.append(LayoutEdge(prev, e.dst, e.src_port, e.dst_port))
    layout.edges = routed


# --------------------------------------------------------------------------- #
# Alternative layout: column-compression DP (preserves parallel rows).
#
# The serpentine fold flattens the DAG to a line and wraps it, destroying the
# parallel-branch rows that make a clean narrow grid possible. Instead, keep the
# layered (Sugiyama) structure and *merge contiguous layers* into columns until
# the grid fits the viewport. Merges are order-preserving, so left->right flow
# (invariant 2) holds by construction.
#
# Enumerating every contiguous partition is 2^(L-1) — fine for L=6 (Doom), but a
# 48-plugin board has L~17 and 65k partitions, each rebuilt and re-routed: it
# hangs. Two facts collapse it to a polynomial DP:
#   * A merged column packs densely (rows 0..h-1, no interior gaps), so a
#     within-column edge is a routing violation IFF its endpoints aren't on
#     adjacent rows — a local, precomputable per-interval quantity.
#   * Width and within-column violations are additive over columns; column count
#     drives the width penalty; the grid's row count is the *max* column height.
# So: fix a global vertical order (the uncompressed barycentric rows), bound the
# max column height H, and run an O(L^3) cut-point DP minimising
# violations + width over a range of H. ~L reconstructions, scored by the real
# layout_cost. Runs in milliseconds on a Pi.
# --------------------------------------------------------------------------- #


def _compress_intervals(
    plugin_layers: dict[str, int],
    ys: dict[str, int],
    edges: list[tuple[str, str]],
    n_layers: int,
) -> tuple[list[list[int]], list[list[int]]]:
    """Precompute, for every layer interval [j, i), the merged column's height
    and its within-column routing-violation count. A column orders its plugins
    by (y, layer) and packs them densely, so an inside edge violates iff its
    endpoints land >1 row apart in that order."""
    by_layer: dict[int, list[str]] = defaultdict(list)
    for pid, layer in plugin_layers.items():
        by_layer[layer].append(pid)

    height = [[0] * (n_layers + 1) for _ in range(n_layers + 1)]
    viol = [[0] * (n_layers + 1) for _ in range(n_layers + 1)]
    for j in range(n_layers):
        members: list[str] = []
        for i in range(j + 1, n_layers + 1):
            members += by_layer[i - 1]
            pos = {pid: r for r, pid in enumerate(sorted(members, key=lambda p: (ys[p], plugin_layers[p])))}
            height[j][i] = len(members)
            viol[j][i] = sum(
                1 for a, b in edges if a in pos and b in pos and abs(pos[a] - pos[b]) > 1
            )
    return height, viol


def _best_cuts(
    height: list[list[int]],
    viol: list[list[int]],
    n_layers: int,
    viewport_cols: int,
    max_height: int,
    infeasible_penalty: float,
    width_penalty: float,
) -> Optional[list[tuple[int, int]]]:
    """Cut-point DP: partition [0, n_layers) into columns each no taller than
    `max_height`, minimising infeasible_penalty*within-violations +
    width_penalty*columns-over-viewport. Returns the column intervals, or None
    if no column can satisfy the height bound."""
    INF = float("inf")
    # dp[i][k]: min violation-cost to cover layers [0, i) with exactly k columns.
    dp = [[INF] * (n_layers + 1) for _ in range(n_layers + 1)]
    par = [[-1] * (n_layers + 1) for _ in range(n_layers + 1)]
    dp[0][0] = 0.0
    for i in range(1, n_layers + 1):
        for j in range(i):
            if height[j][i] > max_height:
                continue
            step = infeasible_penalty * viol[j][i]
            for k in range(1, i + 1):
                if dp[j][k - 1] + step < dp[i][k]:
                    dp[i][k] = dp[j][k - 1] + step
                    par[i][k] = j

    best_k, best_total = -1, INF
    for k in range(1, n_layers + 1):
        if dp[n_layers][k] == INF:
            continue
        total = dp[n_layers][k] + width_penalty * max(0, k - viewport_cols)
        if total < best_total:
            best_k, best_total = k, total
    if best_k < 0:
        return None

    cuts: list[tuple[int, int]] = []
    i, k = n_layers, best_k
    while k > 0:
        j = par[i][k]
        cuts.append((j, i))
        i, k = j, k - 1
    cuts.reverse()
    return cuts


def _build_from_cuts(
    plugin_layers: dict[str, int],
    ys: dict[str, int],
    connections: Iterable[Connection],
    cuts: list[tuple[int, int]],
) -> Layout:
    """Build a Layout from a column partition. Each column packs its plugins
    densely in (y, layer) order; multi-column edges are dummy-routed through gap
    cells so the gutter renderer draws around tiles."""
    col_of_layer: dict[int, int] = {}
    for ci, (j, i) in enumerate(cuts):
        for layer in range(j, i):
            col_of_layer[layer] = ci

    by_col: dict[int, list[str]] = defaultdict(list)
    for pid, layer in plugin_layers.items():
        by_col[col_of_layer[layer]].append(pid)

    n_cols = len(cuts)
    n_rows = max((len(v) for v in by_col.values()), default=0)
    nodes: dict[str, LayoutNode] = {}
    cols: list[list[Optional[LayoutNode]]] = [[None] * n_rows for _ in range(n_cols)]
    for ci in range(n_cols):
        for r, pid in enumerate(sorted(by_col[ci], key=lambda p: (ys[p], plugin_layers[p]))):
            node = LayoutNode(id=pid, kind="plugin", layer=ci, row=r)
            nodes[pid] = node
            cols[ci][r] = node

    edges: list[LayoutEdge] = []
    seen: set[tuple[str, str, int, int]] = set()
    for c in audio_connections(connections):
        src, dst = nodes.get(c.src.id), nodes.get(c.dst.id)
        if src is None or dst is None:
            continue
        key = (src.id, dst.id, c.src.port_idx, c.dst.port_idx)
        if key in seen:
            continue
        seen.add(key)
        edges.append(LayoutEdge(src, dst, c.src.port_idx, c.dst.port_idx))

    layout = Layout(cols=cols, edges=edges)
    _route_dp_edges(layout)  # split multi-column edges through gap cells
    return layout


def build_layout_compress(
    plugin_instance_ids: Iterable[str],
    connections: Iterable[Connection],
    height_cap: int = 4,
    viewport_cols: int = 4,
) -> Layout:
    """Layered layout compressed by merging adjacent columns. A cut-point DP
    finds, for each max column height, the partition minimising routing
    violations and width-over-viewport; the candidate with the lowest real
    layout_cost wins. Stays <= viewport wide when feasible and only spills past
    it to avoid running a wire through a plugin. A board that already fits keeps
    its layered structure."""
    # Uncompressed layered pass fixes each plugin's layer and a stable vertical
    # order (barycentric row) that merges preserve.
    base_nodes = build_nodes(plugin_instance_ids, connections)
    longest_path_layers(base_nodes, connections)
    nodes, base_edges = insert_dummies(base_nodes, connections)
    barycentric_order(nodes, base_edges)

    plugins = {nid: n for nid, n in nodes.items() if n.kind == "plugin"}
    if not plugins:
        return Layout()
    used = sorted({n.layer for n in plugins.values()})
    remap = {old: i for i, old in enumerate(used)}
    plugin_layers = {pid: remap[n.layer] for pid, n in plugins.items()}
    ys = {pid: n.row for pid, n in plugins.items()}
    n_layers = len(used)

    real_edges: list[tuple[str, str]] = []
    seen_e: set[tuple[str, str]] = set()
    for c in audio_connections(connections):
        s, d = c.src.id, c.dst.id
        if s in plugins and d in plugins and s != d and (s, d) not in seen_e:
            seen_e.add((s, d))
            real_edges.append((s, d))

    height, viol = _compress_intervals(plugin_layers, ys, real_edges, n_layers)
    min_h = max((height[layer][layer + 1] for layer in range(n_layers)), default=0)
    max_h = height[0][n_layers]  # everything in one column

    best: Optional[Layout] = None
    best_cost = float("inf")
    seen_cuts: set[tuple[tuple[int, int], ...]] = set()
    for h in range(min_h, max_h + 1):
        cuts = _best_cuts(height, viol, n_layers, viewport_cols, h, 1000.0, 10.0)
        if cuts is None or tuple(cuts) in seen_cuts:
            continue
        seen_cuts.add(tuple(cuts))
        layout = _build_from_cuts(plugin_layers, ys, connections, cuts)
        cost = layout_cost(layout, height_cap, viewport_cols=viewport_cols)
        if cost < best_cost:
            best, best_cost = layout, cost
    assert best is not None
    return best
