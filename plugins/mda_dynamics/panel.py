from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec
from common.parameter import Symbol


class MdaDynamicsPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym=Symbol("thresh"),
        rat_sym=Symbol("ratio"),
        mak_sym=Symbol("output"),
        kn_sym=None,
        in_audio_sym="left_in",
        out_audio_sym="left_out",
    )
