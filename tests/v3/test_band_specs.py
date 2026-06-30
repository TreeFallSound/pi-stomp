"""Unit tests for band spec definitions across all EQ plugin packages.

Validates that every plugin's ``BAND_SPECS`` tuple has the expected number of
bands, correct symbol names, valid frequency/gain ranges, and proper
``shelf_side`` values.
"""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec, GraphicBandSpec

# ── parametric EQ plugins ──────────────────────────────────────────────────


class TestFil4BandSpecs:
    def test_band_count(self):
        from plugins.fil4.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 8

    def test_all_band_specs(self):
        from plugins.fil4.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert isinstance(b, BandSpec)
            assert b.name
            assert b.freq_sym
            assert b.freq_min > 0
            assert b.freq_max > b.freq_min

    def test_shelf_side_values(self):
        from plugins.fil4.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.shelf_side in (None, "low", "high")

    def test_hp_lp_shelves(self):
        from plugins.fil4.band_spec import BAND_SPECS

        hp = BAND_SPECS[0]
        assert hp.name == "HP"
        assert hp.shelf_side is None
        assert hp.gain_sym is None
        assert hp.q_sym is not None  # HP has Q (HPQ)

        lp = BAND_SPECS[7]
        assert lp.name == "LP"
        assert lp.shelf_side is None
        assert lp.gain_sym is None
        assert lp.q_sym is not None  # LP has Q (LPQ)

        ls = BAND_SPECS[1]
        assert ls.shelf_side == "low"
        assert ls.gain_sym is not None
        assert ls.q_sym is not None  # LS has Q (LSq)

        hs = BAND_SPECS[6]
        assert hs.shelf_side == "high"
        assert hs.gain_sym is not None
        assert hs.q_sym is not None  # HS has Q (HSq)

    def test_peaking_bands_have_q(self):
        from plugins.fil4.band_spec import BAND_SPECS

        for b in BAND_SPECS[2:6]:
            assert b.q_sym is not None
            assert b.q_min > 0
            assert b.q_max > b.q_min

    def test_enable_sym_present(self):
        from plugins.fil4.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.enable_sym is not None

    def test_plugin_enable_sym(self):
        from plugins.fil4.band_spec import PLUGIN_ENABLE_SYM

        assert PLUGIN_ENABLE_SYM == "enable"

    def test_global_gain_sym(self):
        from plugins.fil4.band_spec import GLOBAL_GAIN_SYM

        assert GLOBAL_GAIN_SYM == "gain"


# ── graphic EQ plugins ────────────────────────────────────────────────────


class TestCapsEq10BandSpecs:
    def test_band_count(self):
        from plugins.capseq10.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 10

    def test_all_graphic_band_specs(self):
        from plugins.capseq10.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert isinstance(b, GraphicBandSpec)
            assert b.name
            assert b.freq_hz > 0
            assert b.gain_sym
            assert b.gain_min < b.gain_max

    def test_gain_range(self):
        from plugins.capseq10.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.gain_min == -48.0
            assert b.gain_max == 24.0

    def test_frequencies_ascending(self):
        from plugins.capseq10.band_spec import BAND_SPECS

        freqs = [b.freq_hz for b in BAND_SPECS]
        assert freqs == sorted(freqs)

    def test_colors_match_count(self):
        from plugins.capseq10.band_spec import BAND_SPECS

        assert len({b.color for b in BAND_SPECS}) == len(BAND_SPECS)

    def test_symbol_names(self):
        from plugins.capseq10.band_spec import BAND_SPECS

        expected = [
            "band31hz", "band63hz", "band125hz", "band250hz", "band500hz",
            "band1khz", "band2khz", "band4khz", "band8khz", "band16khz",
        ]
        assert [b.gain_sym for b in BAND_SPECS] == expected


class TestGxGraphicEqBandSpecs:
    def test_band_count(self):
        from plugins.graphiceq.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 11

    def test_sequential_port_naming(self):
        from plugins.graphiceq.band_spec import BAND_SPECS

        # Faust graphiceq.dsp maps g1..g11 to 31 Hz..20 kHz sequentially.
        syms = [b.gain_sym for b in BAND_SPECS]
        assert syms == ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11"]

    def test_gain_range(self):
        from plugins.graphiceq.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.gain_min == -30.0
            assert b.gain_max == 20.0

    def test_frequencies_ascending(self):
        from plugins.graphiceq.band_spec import BAND_SPECS

        freqs = [b.freq_hz for b in BAND_SPECS]
        assert freqs == sorted(freqs)


class TestGxBarkGraphicEqBandSpecs:
    def test_band_count(self):
        from plugins.barkgraphiceq.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 24

    def test_bark_frequencies(self):
        from plugins.barkgraphiceq.band_spec import BAND_SPECS

        freqs = [b.freq_hz for b in BAND_SPECS]
        assert freqs == sorted(freqs)
        assert freqs[0] == 50.0
        assert freqs[-1] == 13500.0

    def test_gain_range(self):
        from plugins.barkgraphiceq.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.gain_min == -30.0
            assert b.gain_max == 20.0

    def test_symbol_names_sequential(self):
        from plugins.barkgraphiceq.band_spec import BAND_SPECS

        expected = [f"G{i+1}" for i in range(24)]
        assert [b.gain_sym for b in BAND_SPECS] == expected


class TestZamGEQ31BandSpecs:
    def test_band_count(self):
        from plugins.zamgeq31.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 29

    def test_gain_range(self):
        from plugins.zamgeq31.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.gain_min == -12.0
            assert b.gain_max == 12.0

    def test_frequencies_ascending(self):
        from plugins.zamgeq31.band_spec import BAND_SPECS

        freqs = [b.freq_hz for b in BAND_SPECS]
        assert freqs == sorted(freqs)

    def test_first_and_last_freq(self):
        from plugins.zamgeq31.band_spec import BAND_SPECS

        assert BAND_SPECS[0].freq_hz == 32.0
        assert BAND_SPECS[-1].freq_hz == 20801.0

    def test_symbol_names_sequential(self):
        from plugins.zamgeq31.band_spec import BAND_SPECS

        expected = [f"band{i+1}" for i in range(29)]
        assert [b.gain_sym for b in BAND_SPECS] == expected


# ── parametric EQ plugins (other) ─────────────────────────────────────────


class TestDistaqBandSpecs:
    def test_band_count(self):
        from plugins.distaq.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 6

    def test_shelf_side(self):
        from plugins.distaq.band_spec import BAND_SPECS

        assert BAND_SPECS[0].shelf_side == "low"
        assert BAND_SPECS[5].shelf_side == "high"
        for b in BAND_SPECS[1:5]:
            assert b.shelf_side is None

    def test_shelves_no_q(self):
        from plugins.distaq.band_spec import BAND_SPECS

        assert BAND_SPECS[0].q_sym is None
        assert BAND_SPECS[5].q_sym is None

    def test_peaking_bands_have_q(self):
        from plugins.distaq.band_spec import BAND_SPECS

        for b in BAND_SPECS[1:5]:
            assert b.q_sym is not None

    def test_all_have_enable(self):
        from plugins.distaq.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.enable_sym is not None


class TestZamEq2BandSpecs:
    def test_band_count(self):
        from plugins.zameq2.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 4

    def test_shelf_side(self):
        from plugins.zameq2.band_spec import BAND_SPECS

        assert BAND_SPECS[0].shelf_side == "low"
        assert BAND_SPECS[3].shelf_side == "high"
        for b in BAND_SPECS[1:3]:
            assert b.shelf_side is None

    def test_shelves_no_q(self):
        from plugins.zameq2.band_spec import BAND_SPECS

        assert BAND_SPECS[0].q_sym is None
        assert BAND_SPECS[3].q_sym is None

    def test_peaking_bands_have_q(self):
        from plugins.zameq2.band_spec import BAND_SPECS

        assert BAND_SPECS[1].q_sym is not None
        assert BAND_SPECS[2].q_sym is not None

    def test_no_per_band_enable(self):
        from plugins.zameq2.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.enable_sym is None


class TestTapeqBandSpecs:
    def test_band_count(self):
        from plugins.tapeq.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 8

    def test_no_q(self):
        from plugins.tapeq.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.q_sym is None

    def test_no_per_band_enable(self):
        from plugins.tapeq.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.enable_sym is None

    def test_shelf_side(self):
        from plugins.tapeq.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.shelf_side is None  # all peak, no shelf designation

    def test_frequencies_ascending(self):
        from plugins.tapeq.band_spec import BAND_SPECS

        freqs = [b.freq_min for b in BAND_SPECS]
        assert freqs == sorted(freqs)


class TestTapeqbwBandSpecs:
    def test_band_count(self):
        from plugins.tapeqbw.band_spec import BAND_SPECS

        assert len(BAND_SPECS) == 8

    def test_has_bandwidth(self):
        from plugins.tapeqbw.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.q_sym is not None

    def test_no_per_band_enable(self):
        from plugins.tapeqbw.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.enable_sym is None

    def test_shelf_side(self):
        from plugins.tapeqbw.band_spec import BAND_SPECS

        for b in BAND_SPECS:
            assert b.shelf_side is None  # all peak, no shelf designation
