"""Shared type definitions for EQ panel band specifications.

BandSpec / GraphicBandSpec are static schemas describing what controls exist
for each band. BandParams / GraphicBandParams are runtime values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


BandKind = Literal["peak", "shelf", "hp", "lp"]


@dataclass(frozen=True)
class BandSpec:
    name: str
    kind: BandKind
    enable_sym: str | None
    freq_sym: str
    q_sym: str | None
    gain_sym: str | None
    shelf_side: Literal["low", "high"] | None
    freq_min: float
    freq_max: float
    q_min: float
    q_max: float
    color: tuple[int, int, int]
    gain_min: float = -18.0
    gain_max: float = 18.0


@dataclass(frozen=True)
class GraphicBandSpec:
    name: str
    freq_hz: float
    gain_sym: str
    color: tuple[int, int, int]
    gain_min: float = -18.0
    gain_max: float = 18.0
