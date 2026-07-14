from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec
from common.parameter import Symbol


class AdvancedCompressorPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym=Symbol("THRES"),
        rat_sym=Symbol("RATIO"),
        mak_sym=Symbol("MAKEUP"),
        kn_sym=Symbol("KNEE"),
        in_audio_sym="Input_L",
        out_audio_sym="Output_L",
    )
