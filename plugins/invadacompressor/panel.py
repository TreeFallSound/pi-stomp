"""Invada compressor (mono/stereo): no knee port, and threshold/ratio/gain are named differently."""

from __future__ import annotations

from plugins.acomp.panel import AcompPanel, CompressorSpec


class InvadaCompressorPanel(AcompPanel):
    SPEC = CompressorSpec(
        thr_sym="threshold",
        rat_sym="ratio",
        mak_sym="gain",
        kn_sym=None,
        in_audio_sym="in",
        out_audio_sym="out",
    )
