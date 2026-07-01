from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec


class AdvancedCompressorPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym="THRES",
        rat_sym="RATIO",
        mak_sym="MAKEUP",
        kn_sym="KNEE",
        in_audio_sym="Input_L",
        out_audio_sym="Output_L",
    )
