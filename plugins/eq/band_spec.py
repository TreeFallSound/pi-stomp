"""Shared type definitions for EQ panel band specifications.

BandSpec / GraphicBandSpec are static schemas describing what controls exist
for each band. BandParams / GraphicBandParams are runtime values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from common.parameter import Symbol


BandKind = Literal["peak", "shelf", "hp", "lp"]
FilterTopology = Literal["rbj", "regalia_mitra"]

# How a band's width port encodes its value. Every member has an exact
# conversion to true Q in `filters.as_q` — that map, not the band's kind, is
# what the curve and the readout consult. Two members name a specific
# plugin's encoding because that is what they are; the alternative is a
# default that silently mis-renders the ports it doesn't fit.
#   q               — true RBJ Q (Calf EQ5)
#   bw_oct          — bandwidth in octaves (fil4, distaq, ZamEQ2, TAP EQ/BW)
#   x42_shelf_slope — fil4's shelf-width port; src/lv2.c:280
#   rkr_code        — rakarrack's -64..63 integer code; src/EQ.C:173
QUnits = Literal["q", "bw_oct", "x42_shelf_slope", "rkr_code"]


@dataclass(frozen=True)
class BandSpec:
    name: str
    kind: BandKind
    enable_sym: Symbol | None
    freq_sym: Symbol
    q_sym: Symbol | None
    gain_sym: Symbol | None
    shelf_side: Literal["low", "high"] | None
    freq_min: float
    freq_max: float
    q_min: float
    q_max: float
    color: tuple[int, int, int]
    gain_min: float = -18.0
    gain_max: float = 18.0
    filter_topology: FilterTopology = "rbj"
    q_units: QUnits | None = None
    "How q_sym's port encodes width. None only when the band has no q_sym."

    def __post_init__(self) -> None:
        if (self.q_sym is None) != (self.q_units is None):
            raise ValueError(f"{self.name}: q_sym and q_units must be declared together")


@dataclass(frozen=True)
class GraphicBandSpec:
    name: str
    freq_hz: float
    gain_sym: Symbol
    color: tuple[int, int, int]
    gain_min: float = -18.0
    gain_max: float = 18.0
