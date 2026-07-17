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
    q_is_bw_oct: bool = False
    "Q values are actually bandwidth (octaves) for this band, so display differently."


@dataclass(frozen=True)
class GraphicBandSpec:
    name: str
    freq_hz: float
    gain_sym: Symbol
    color: tuple[int, int, int]
    gain_min: float = -18.0
    gain_max: float = 18.0
