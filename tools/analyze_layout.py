#!/usr/bin/env python3
"""Analyse pedalboard grid layouts against the real layout pipeline.

Loads one or more .pedalboard bundles via the same lilv + MOD-Desktop path
the device uses, runs modalapi.layout.build_layout_compress, and reports
metrics + an ASCII render of the grid.

Run via ./analyze_layout.sh (sets up lilv on PYTHONPATH/DYLD_LIBRARY_PATH).
Requires MOD Desktop running at http://127.0.0.1:18181 to resolve plugin
audio-port ordering.

Usage:
    ./analyze_layout.sh <bundle.pedalboard> [more.pedalboard ...]
    ./analyze_layout.sh --all            # every board in the MOD Desktop dir
    ./analyze_layout.sh --all --summary  # one-line metrics row per board
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Keep the repo root importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import ImageColor, ImageFont  # noqa: E402

from modalapi.layout import (  # noqa: E402
    Layout,
    build_layout_compress,
    layout_cost,
    occupied_cells,
)
from modalapi.pedalboard import Pedalboard  # noqa: E402
from uilib.box import Box  # noqa: E402

# Render through the real device stack so PNGs are pixel-faithful to the LCD.
from uilib.gridpanel import (  # noqa: E402
    CHANNEL,
    ROW_GAP,
    TILE_H,
    TILE_W,
    GridPanel,
)
from uilib.panel import Panel, PanelStack  # noqa: E402
from uilib.text import TextWidget  # noqa: E402

MOD_ROOT_URI = "http://127.0.0.1:18181/"
# Boards live in two places: factory/GSYNTH bundles ship inside the app, user
# boards land in ~/Documents. --all scans both.
MOD_PEDALBOARD_DIRS = (
    Path("/Applications/MOD Desktop.app/Contents/Resources/pedalboards"),
    Path.home() / "Documents" / "MOD Desktop" / "pedalboards",
)
RENDER_DIR = Path(__file__).resolve().parent / "renders"

# Visible LCD grid band (see lcd320x240.draw_plugins): 320w x 130h.
VIEWPORT_W, VIEWPORT_H = 320, 130
COL_PITCH = TILE_W + CHANNEL
ROW_PITCH = TILE_H + ROW_GAP


@dataclass
class Metrics:
    title: str
    n_plugins: int
    cols: int
    rows: int
    parallelism: int  # max plugin tiles in any single column (layer)
    dummies: int  # waypoint cells inserted for multi-column edges
    plugin_cells: int
    total_cells: int

    @property
    def empty_cells(self) -> int:
        return self.total_cells - self.plugin_cells

    @property
    def empty_pct(self) -> float:
        return 100.0 * self.empty_cells / self.total_cells if self.total_cells else 0.0

    @property
    def px_w(self) -> int:
        return max(0, self.cols * COL_PITCH - CHANNEL)

    @property
    def px_h(self) -> int:
        return max(0, self.rows * ROW_PITCH - ROW_GAP)

    @property
    def h_screens(self) -> float:
        return self.px_w / VIEWPORT_W

    @property
    def v_screens(self) -> float:
        return self.px_h / VIEWPORT_H


def compute_metrics(title: str, n_plugins: int, layout: Layout) -> Metrics:
    plugin_cells = dummies = 0
    parallelism = 0
    for col in layout.cols:
        col_plugins = sum(1 for n in col if n is not None and n.kind == "plugin")
        parallelism = max(parallelism, col_plugins)
        plugin_cells += col_plugins
        dummies += sum(1 for n in col if n is not None and n.kind == "dummy")
    return Metrics(
        title=title,
        n_plugins=n_plugins,
        cols=layout.n_cols,
        rows=layout.n_rows,
        parallelism=parallelism,
        dummies=dummies,
        plugin_cells=plugin_cells,
        total_cells=layout.n_cols * layout.n_rows,
    )


def ascii_grid(layout: Layout, cell_w: int = 10) -> str:
    """Row-major textual render of the column-major grid.
    Plugin tiles show a truncated id; dummies show '·'; holes are blank."""
    rows, cols = layout.n_rows, layout.n_cols
    lines = []
    for r in range(rows):
        cells = []
        for c in range(cols):
            node = layout.cols[c][r] if r < len(layout.cols[c]) else None
            if node is None:
                cells.append(" " * cell_w)
            elif node.kind == "dummy":
                cells.append("·".ljust(cell_w))
            else:
                cells.append(node.id[: cell_w - 1].ljust(cell_w))
        lines.append("|" + "|".join(cells) + "|")
    sep = "+" + "+".join(["-" * cell_w] * cols) + "+"
    out = [sep]
    for ln in lines:
        out.append(ln)
        out.append(sep)
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# PNG render — drive the real device stack (PanelStack + GridPanel + tile
# widgets) and capture the composited LCD image. Tile coloring and wire
# routing are exactly what the device draws; we own no drawing code here.
# --------------------------------------------------------------------------- #

MARGIN = 8

# Mirror of lcd320x240.Lcd's tile palette so the analyzer's tiles match the
# device pixel-for-pixel (the Lcd ctor needs SPI/GPIO, so we can't reuse it).
_BACKGROUND = (0, 0, 0)
_FOREGROUND = (255, 255, 255)
_DEFAULT_PLUGIN_COLOR = "Silver"
_CATEGORY_COLOR_MAP = {
    "Delay": "MediumVioletRed",
    "Distortion": "Lime",
    "Dynamics": "OrangeRed",
    "Filter": (205, 133, 40),
    "Generator": "Indigo",
    "Midiutility": "Gray",
    "Modulator": (50, 50, 255),
    "Reverb": (20, 160, 255),
    "Simulator": "SaddleBrown",
    "Spacial": "Gray",
    "Spectral": "Red",
    "Utility": "Gray",
}
_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_PLUGIN_FONT = ImageFont.truetype(str(_FONTS_DIR / "DejaVuSans.ttf"), 20)
_PLUGIN_LABEL_LENGTH = 7


class _CaptureLcd:
    """Minimal LcdBase: PanelStack composites into an image and hands it to
    update(); we keep a copy so the render can be saved."""

    def __init__(self, size: tuple[int, int]) -> None:
        self._size = size
        self.image = None

    def dimensions(self) -> tuple[int, int]:
        return self._size

    def default_format(self) -> str:
        return "RGB"

    def update(self, image, box=None) -> None:
        self.image = image.copy()


def _get_plugin_color(plugin):
    category = getattr(plugin, "category", None)
    if not category:
        return _DEFAULT_PLUGIN_COLOR
    c = _CATEGORY_COLOR_MAP.get(category, _DEFAULT_PLUGIN_COLOR)
    if isinstance(c, tuple):
        return c
    try:
        return ImageColor.getrgb(c)
    except ValueError:
        return _FOREGROUND


def _shorten(label: str, width: int) -> str:
    while label and _PLUGIN_FONT.getbbox(label)[2] > width:
        label = label[:-1]
    return label


def _color_tile(tile, plugin) -> None:
    # Same branch as lcd320x240.color_plugin().
    color = _get_plugin_color(plugin)
    if plugin.is_bypassed():
        tile.set_outline(1, color)
        tile.set_background(_BACKGROUND)
        tile.set_foreground(_FOREGROUND)
    else:
        tile.set_outline(2, _BACKGROUND)
        tile.set_background(color)
        tile.set_foreground(_BACKGROUND)


def count_violations(layout: Layout) -> int:
    """Through-plugin wires: dummy waypoints the DP had to drop onto a plugin
    cell because the crossed column had no gap (invariant 1 broken)."""
    occ = occupied_cells(layout)
    bad = {n.id for e in layout.edges for n in (e.src, e.dst) if n.kind == "dummy" and (n.layer, n.row) in occ}
    return len(bad)


def render_png(layout: Layout, plugins_by_id: dict, path: Path) -> None:
    """Render the layout exactly as the device would: build the real
    GridPanel inside a PanelStack and save the composited image."""
    grid_w = max(1, layout.n_cols * COL_PITCH - CHANNEL)
    grid_h = max(1, layout.n_rows * ROW_PITCH - ROW_GAP)
    w, h = grid_w + 2 * MARGIN, grid_h + 2 * MARGIN

    lcd = _CaptureLcd((w, h))
    pstack = PanelStack(lcd, image_format="RGB", use_dimming=False)
    host = Panel(box=Box.xywh(0, 0, w, h))
    pstack.push_panel(host, refresh=False)

    def tile_factory(node, box, parent):
        plugin = plugins_by_id[node.id]
        label = plugin.instance_id[:_PLUGIN_LABEL_LENGTH].lstrip("/").replace("_", "")
        label = _shorten(label, box.width)
        tile = TextWidget(box=box, text=label, font=_PLUGIN_FONT, outline_radius=5, parent=parent)
        _color_tile(tile, plugin)
        return tile

    # Whole grid in view (no scroll): box spans the full virtual extent.
    GridPanel(layout, tile_factory, box=Box.xywh(MARGIN, MARGIN, grid_w, grid_h), parent=host)
    # Render the panel into its backing image and composite up to the LCD
    # (mirrors lcd320x240.draw_plugins -> main_panel.refresh()).
    host.refresh()

    assert lcd.image is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    lcd.image.save(path)


def load_layout(bundle: Path, max_rows: int = 4) -> tuple[Pedalboard, Layout]:
    title = bundle.stem
    pb = Pedalboard(title, str(bundle), root_uri=MOD_ROOT_URI)
    pb.load_bundle(str(bundle), {})
    ids = [p.instance_id.lstrip("/") for p in pb.plugins]
    layout = build_layout_compress(ids, pb.connections, height_cap=max_rows)
    return pb, layout


def render_for(pb: Pedalboard, layout: Layout, stem: str) -> tuple[Path, int]:
    out = RENDER_DIR / f"{stem}.png"
    plugins_by_id = {p.instance_id.lstrip("/"): p for p in pb.plugins}
    render_png(layout, plugins_by_id, out)
    return out, count_violations(layout)


def print_full(bundle: Path, max_rows: int = 4, png: bool = True) -> Metrics:
    pb, layout = load_layout(bundle, max_rows)
    m = compute_metrics(bundle.stem, len(pb.plugins), layout)
    if png:
        out, violations = render_for(pb, layout, bundle.stem)
        note = f"  ({violations} through-plugin wires)" if violations else ""
        print(f"png: {out}{note}")
    print(f"\n=== {m.title} ===")
    print(
        f"plugins={m.n_plugins}  grid={m.cols}x{m.rows} (cols x rows)  "
        f"parallelism={m.parallelism}  dummies={m.dummies}  "
        f"cost={layout_cost(layout, max_rows):.3f}"
    )
    print(f"cells: {m.plugin_cells}/{m.total_cells} filled  empty={m.empty_pct:.0f}%")
    print(f"pixels: {m.px_w}x{m.px_h}  scroll: {m.h_screens:.2f} screens horiz, {m.v_screens:.2f} vert")
    print(ascii_grid(layout))
    return m


SUMMARY_HEADER = (
    f"{'pedalboard':24} {'plug':>4} {'cols':>4} {'rows':>4} "
    f"{'par':>3} {'dum':>3} {'empty%':>6} {'h-scr':>5} {'v-scr':>5}"
)


def summary_row(m: Metrics) -> str:
    return (
        f"{m.title[:24]:24} {m.n_plugins:>4} {m.cols:>4} {m.rows:>4} "
        f"{m.parallelism:>3} {m.dummies:>3} {m.empty_pct:>5.0f}% "
        f"{m.h_screens:>5.2f} {m.v_screens:>5.2f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundles", nargs="*", help="Pedalboard bundle paths")
    ap.add_argument("--all", action="store_true", help="Analyse every board in the MOD Desktop dirs")
    ap.add_argument("--summary", action="store_true", help="One metrics row per board, no ASCII grid")
    ap.add_argument("--max-rows", type=int, default=4, help="height_cap (default: 4)")
    ap.add_argument("--no-png", action="store_true", help=f"Skip writing PNG renders to {RENDER_DIR}")
    args = ap.parse_args()

    bundles: list[Path] = [Path(b) for b in args.bundles]
    if args.all:
        for d in MOD_PEDALBOARD_DIRS:
            bundles += sorted(d.glob("*.pedalboard"))
    if not bundles:
        ap.error("no bundles given (pass paths or --all)")

    metrics: list[Metrics] = []
    for b in bundles:
        if not b.exists():
            print(f"skip (missing): {b}", file=sys.stderr)
            continue
        try:
            if args.summary:
                pb, layout = load_layout(b, args.max_rows)
                if not args.no_png:
                    render_for(pb, layout, b.stem)
                metrics.append(compute_metrics(b.stem, len(pb.plugins), layout))
            else:
                metrics.append(print_full(b, args.max_rows, png=not args.no_png))
        except Exception as e:  # keep going across a batch
            print(f"FAILED {b.stem}: {e}", file=sys.stderr)

    if args.summary and metrics:
        print(SUMMARY_HEADER)
        print("-" * len(SUMMARY_HEADER))
        for m in sorted(metrics, key=lambda x: x.empty_pct, reverse=True):
            print(summary_row(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
