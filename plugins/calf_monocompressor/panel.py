from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec
from common.parameter import Symbol


class CalfMonoCompressorPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym=Symbol("threshold"),
        rat_sym=Symbol("ratio"),
        mak_sym=Symbol("makeup"),
        kn_sym=Symbol("knee"),
        in_audio_sym="in_l",
        out_audio_sym="out_l",
    )
