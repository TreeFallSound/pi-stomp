"""Column-major routing-aware grid panel.

Lays out a modalapi.layout.Layout into tiles on a Panel. Iteration order
is column-major (top-to-bottom within a column, then next column). Holes
and dummy nodes are not selectable. Horizontal scrolling is handled by
the ContainerWidget base class' built-in scroll-into-view mechanism.

Geometry follows the locked design parameters:
  - Tile size:      74 x 24
  - Channel gap:    7 px (asymmetric: 1 + 1 + 3 + 1 + 1)
  - Lane offsets:   1 (port 0) and 5 (port 1) within the 7px channel
  - Port y offsets: 8 (port 0) and 16 (port 1) within the 24h tile
"""

from __future__ import annotations

from typing import Callable, Optional

from modalapi.layout import Layout, LayoutEdge, LayoutNode
from uilib.box import Box
from uilib.container import ContainerWidget
from uilib.widget import Widget


TILE_W = 74
TILE_H = 28
CHANNEL = 7  # horizontal column gutter
ROW_GAP = 3  # vertical row gutter — no wires routed here, so chosen for visual breathing room
LANE_OFFSETS: tuple[int, int] = (2, 4)
PORT_OFFSETS_Y: tuple[int, int] = (8, 18)

# Default wire colors keyed on src_port (overridable via constructor).
DEFAULT_WIRE_COLORS: tuple[tuple[int, int, int], tuple[int, int, int]] = (
    (0, 200, 255),  # port 0 — cyan
    (255, 160, 0),  # port 1 — amber
)

TileFactory = Callable[[LayoutNode, Box, Widget], Widget]
"""(node, box, parent) -> Widget. The factory MUST construct the tile with
`parent` already wired (e.g. pass `parent=parent` to TextWidget). Attaching
later wipes any explicit color/font set on the widget because
`_setup_act_attrs` re-resolves inherited attributes from the parent."""


class GridPanel(ContainerWidget):
    """A scrollable column-major grid of LayoutNodes.

    The container's `box` defines the *visible* viewport (typically 320px
    wide); tiles are positioned in the panel's own virtual coordinate space
    which can extend well past the viewport. ContainerWidget's
    `_scroll_into_view` handles bringing offscreen tiles into view when
    selection moves onto them.

    Tiles are exposed to a host Panel's selection traversal via
    `sel_children()` in column-major order. Only "plugin" nodes get a
    widget — sources, sinks, dummies and holes are skipped, so the outer
    selection naturally jumps over empty cells.
    """

    def __init__(
        self,
        layout: Layout,
        tile_factory: TileFactory,
        box: Box,
        wire_colors: tuple[tuple[int, int, int], tuple[int, int, int]] = DEFAULT_WIRE_COLORS,
        bottom_inset: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(box=box, **kwargs)
        self.layout = layout
        self.wire_colors = wire_colors
        self.bottom_inset = bottom_inset
        self.tile_widgets: dict[str, Widget] = {}
        self.tile_order: list[Widget] = []  # column-major insertion order
        self._build(tile_factory)

    # ------------------------------------------------------------------ #
    # Geometry helpers (also used by the routing render pass).
    # ------------------------------------------------------------------ #

    @staticmethod
    def cell_xy(layer: int, row: int) -> tuple[int, int]:
        return ((TILE_W + CHANNEL) * layer, (TILE_H + ROW_GAP) * row)

    @classmethod
    def cell_box(cls, layer: int, row: int) -> Box:
        x, y = cls.cell_xy(layer, row)
        return Box.xywh(x, y, TILE_W, TILE_H)

    @classmethod
    def out_port_xy(cls, layer: int, row: int, port_idx: int) -> tuple[int, int]:
        """Right-edge attachment point for an output wire."""
        x, y = cls.cell_xy(layer, row)
        return (x + TILE_W, y + PORT_OFFSETS_Y[port_idx])

    @classmethod
    def in_port_xy(cls, layer: int, row: int, port_idx: int) -> tuple[int, int]:
        """Left-edge attachment point for an input wire."""
        x, y = cls.cell_xy(layer, row)
        return (x, y + PORT_OFFSETS_Y[port_idx])

    @classmethod
    def gutter_lane_x(cls, layer: int, port_idx: int) -> int:
        """X coord of the vertical lane in the gap to the right of `layer`."""
        return (TILE_W + CHANNEL) * layer + TILE_W + LANE_OFFSETS[port_idx]

    # ------------------------------------------------------------------ #
    # Build tiles from layout.
    # ------------------------------------------------------------------ #

    def _build(self, tile_factory: TileFactory) -> None:
        # Column-major insertion → outer Panel's flat traversal walks
        # top-to-bottom within a column, then jumps to the top of the next.
        for layer_idx, col in enumerate(self.layout.cols):
            for row_idx, node in enumerate(col):
                if node is None or node.kind != "plugin":
                    continue  # holes, sources, sinks, dummies: no tile widget
                box = self.cell_box(layer_idx, row_idx)
                widget = tile_factory(node, box, self)
                assert widget.parent is self, (
                    "tile_factory must attach the widget to the GridPanel "
                    "(pass parent=parent to the widget constructor)"
                )
                widget.selectable = True
                self.tile_widgets[node.id] = widget
                self.tile_order.append(widget)

    # ------------------------------------------------------------------ #
    # Selection: expose tiles to the parent panel via sel_children so the
    # outer flat traversal walks them column-major as if they were direct
    # entries in the parent's sel_list.
    # ------------------------------------------------------------------ #

    def sel_children(self):
        return list(self.tile_order)

    def _notify_detach(self, widget):
        """A tile detaching at runtime must be removed from tile_order and
        tile_widgets so the outer panel's flat sel traversal (which calls
        our sel_children()) stops yielding a detached widget."""
        if widget in self.tile_order:
            self.tile_order.remove(widget)
            for nid, w in list(self.tile_widgets.items()):
                if w is widget:
                    del self.tile_widgets[nid]
                    break

    # ------------------------------------------------------------------ #
    # Public API.
    # ------------------------------------------------------------------ #

    def widget_for(self, node_id: str) -> Optional[Widget]:
        return self.tile_widgets.get(node_id)

    def _viewport_size(self) -> tuple[int, int]:
        w, h = super()._viewport_size()
        return w, h - self.bottom_inset

    # ------------------------------------------------------------------ #
    # Routing render pass.
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clamp_port(idx: int) -> int:
        """Multi-channel plugins (e.g. an 8-in mixer) report port indices ≥ 2.
        We only have two visual lanes today; fold extras into the second one
        so rendering doesn't crash."""
        return 0 if idx <= 0 else 1

    def _edge_endpoints(self, edge: LayoutEdge) -> tuple[tuple[int, int], tuple[int, int], int]:
        """Resolve (src_xy, dst_xy, vertical_lane_x) for one column-spanning
        edge. Dummies use carried_src_port as both their in and out port.

        When the destination is a dummy, we anchor dst_xy at the *right* edge
        of the dummy cell so the segment crosses the whole cell. Otherwise
        each edge in a dummy chain would only touch the dummy's left edge,
        leaving the cell's width visually unconnected.
        """
        src, dst = edge.src, edge.dst
        src_y_idx = self._clamp_port(src.carried_src_port if src.kind == "dummy" else edge.src_port)
        dst_y_idx = self._clamp_port(dst.carried_src_port if dst.kind == "dummy" else edge.dst_port)
        lane_idx = self._clamp_port(edge.src_port)
        src_xy = self.out_port_xy(src.layer, src.row, src_y_idx)
        if dst.kind == "dummy":
            dst_xy = self.out_port_xy(dst.layer, dst.row, dst_y_idx)
        else:
            dst_xy = self.in_port_xy(dst.layer, dst.row, dst_y_idx)
        lane_x = self.gutter_lane_x(src.layer, lane_idx)
        return src_xy, dst_xy, lane_x

    def _draw_vertical_edge(self, draw, edge: LayoutEdge, ox: int, oy: int) -> None:
        """Serpentine neighbour (same column): draw a direct vertical line at
        the column's horizontal centre. The runs behind the src/dst tiles are
        hidden, so the visible wire sits in the row gap — and stacked chain
        links line up into one clean vertical spine. Stereo pairs nudge apart
        by port so the two wires don't coincide."""
        port = self._clamp_port(edge.src_port)
        x0, _ = self.cell_xy(edge.src.layer, 0)
        cx = x0 + TILE_W // 2 + (3 if port else 0)
        _, sy = self.cell_xy(edge.src.layer, edge.src.row)
        _, dy = self.cell_xy(edge.dst.layer, edge.dst.row)
        sy += TILE_H // 2
        dy += TILE_H // 2
        draw.line([(ox + cx, oy + sy), (ox + cx, oy + dy)], fill=self.wire_colors[port], width=1)

    def _draw(self, image, draw, real_box) -> None:
        """Draw the routing wires under any child tiles. Manhattan routing:
        out-stub right -> vertical in gutter at lane[src_port] -> in-stub
        right into dst. Vertical-only edges (same column) route in the
        right-hand gutter instead. Opaque so shared segments render cleanly
        regardless of draw order."""
        super()._draw(image, draw, real_box)
        ox, oy = real_box.topleft
        for edge in self.layout.edges:
            if edge.src.layer == edge.dst.layer:
                self._draw_vertical_edge(draw, edge, ox, oy)
                continue
            (sx, sy), (dx, dy), lane_x = self._edge_endpoints(edge)
            color = self.wire_colors[self._clamp_port(edge.src_port)]
            # Three segments. Coords are panel-local; offset by real_box origin.
            draw.line([(ox + sx, oy + sy), (ox + lane_x, oy + sy)], fill=color, width=1)
            draw.line([(ox + lane_x, oy + sy), (ox + lane_x, oy + dy)], fill=color, width=1)
            draw.line([(ox + lane_x, oy + dy), (ox + dx, oy + dy)], fill=color, width=1)
