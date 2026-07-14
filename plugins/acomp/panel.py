from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec
from common.parameter import Symbol


class AcompPanel(CompressorPanel):
    SPEC = CompressorSpec(thr_sym=Symbol("thr"), rat_sym=Symbol("rat"), mak_sym=Symbol("mak"), kn_sym=Symbol("kn"))
