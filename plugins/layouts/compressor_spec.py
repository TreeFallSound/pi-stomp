from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ArcSpec:
    symbol: str
    label: str
    color: tuple[int, int, int]
    display_fn: Callable[[float], str]


@dataclass(frozen=True)
class CompressorSpec:
    thr_sym: str
    rat_sym: str
    mak_sym: str
    kn_sym: str | None = None
    in_audio_sym: str = "lv2_audio_in_1"
    out_audio_sym: str = "lv2_audio_out_1"


def build_arc_specs(spec: CompressorSpec) -> tuple[ArcSpec, ...]:
    arcs = [
        ArcSpec(spec.thr_sym, "THRESH", (255, 180, 80), lambda v: f"{v:+.0f}"),
        ArcSpec(spec.rat_sym, "RATIO", (130, 220, 110), lambda v: f"{v:.1f}:1"),
    ]
    if spec.kn_sym is not None:
        arcs.append(ArcSpec(spec.kn_sym, "KNEE", (110, 200, 230), lambda v: f"{v:.1f}"))
    arcs.append(ArcSpec(spec.mak_sym, "MAKEUP", (210, 130, 230), lambda v: f"+{v:.0f}"))
    return tuple(arcs)


_ARC_CENTERS_4: tuple[tuple[int, int], ...] = ((41, 34), (95, 76), (41, 118), (95, 160))
_ARC_CENTERS_3: tuple[tuple[int, int], ...] = ((41, 34), (95, 97), (41, 160))


def arc_centers_for(n: int) -> tuple[tuple[int, int], ...]:
    return _ARC_CENTERS_3 if n == 3 else _ARC_CENTERS_4
