from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec


class CapsCompressPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym="threshold",
        rat_sym="strength",
        mak_sym="gain",
        kn_sym=None,
        in_audio_sym="in",
        out_audio_sym="out",
    )
