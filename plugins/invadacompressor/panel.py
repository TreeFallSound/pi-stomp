from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec
from common.parameter import Symbol


class InvadaCompressorPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym=Symbol("threshold"),
        rat_sym=Symbol("ratio"),
        mak_sym=Symbol("gain"),
        kn_sym=None,
        in_audio_sym="in",
        out_audio_sym="out",
    )
