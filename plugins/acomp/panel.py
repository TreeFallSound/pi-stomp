from __future__ import annotations

from plugins.compressor_base import CompressorPanel, CompressorSpec


class AcompPanel(CompressorPanel):
    SPEC = CompressorSpec(thr_sym="thr", rat_sym="rat", mak_sym="mak", kn_sym="kn")
