from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec


class MdaDynamicsPanel(CompressorPanel):
    SPEC = CompressorSpec(
        thr_sym="thresh",
        rat_sym="ratio",
        mak_sym="output",
        kn_sym=None,
        in_audio_sym="left_in",
        out_audio_sym="left_out",
    )
