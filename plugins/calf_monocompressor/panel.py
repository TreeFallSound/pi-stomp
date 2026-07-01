from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec


class CalfMonoCompressorPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym="threshold",
        rat_sym="ratio",
        mak_sym="makeup",
        kn_sym="knee",
        in_audio_sym="in_l",
        out_audio_sym="out_l",
    )
