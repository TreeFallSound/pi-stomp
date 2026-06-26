"""Unit tests for pistomp/nam/wavio.py — 24-bit WAV decoding."""

from __future__ import annotations

import io
import struct
import wave

import numpy as np
import pytest

from pistomp.nam.wavio import load_wav_float32


def _write_wav_24bit_mono(samples_int24: list[int], sample_rate: int = 48000) -> bytes:
    """Encode a list of signed 24-bit integers into a WAV byte-string."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(3)
        wf.setframerate(sample_rate)
        raw = b"".join(
            struct.pack("<i", v)[: 3]  # little-endian int32, take lower 3 bytes
            for v in samples_int24
        )
        wf.writeframes(raw)
    return buf.getvalue()


def _tmp_wav(tmp_path, samples_int24: list[int], sample_rate: int = 48000):
    path = tmp_path / "test.wav"
    path.write_bytes(_write_wav_24bit_mono(samples_int24, sample_rate))
    return path


class TestLoadWavFloat32:
    def test_silence_is_zero(self, tmp_path):
        path = _tmp_wav(tmp_path, [0] * 64)
        out = load_wav_float32(path)
        assert np.all(out == 0.0)

    def test_positive_full_scale(self, tmp_path):
        # int24 max = 0x7FFFFF = 8388607
        path = _tmp_wav(tmp_path, [0x7FFFFF])
        out = load_wav_float32(path)
        # After left-shift by 8, int32 value = 0x7FFFFF00 = 2147483392
        expected = 2147483392 / (2**31)
        assert abs(float(out[0]) - expected) < 1e-6

    def test_negative_full_scale(self, tmp_path):
        # int24 min = -8388608 = 0x800000 (two's complement)
        path = _tmp_wav(tmp_path, [-8388608])
        out = load_wav_float32(path)
        # After sign-extension to int32: 0x80000000 = -2^31
        assert abs(float(out[0]) - (-1.0)) < 1e-6

    def test_round_trip_sign_extension(self, tmp_path):
        # Values that cross the sign boundary
        vals = [0, 1, -1, 8388607, -8388608, 100, -100]
        path = _tmp_wav(tmp_path, vals)
        out = load_wav_float32(path)
        assert len(out) == len(vals)
        # Each value should be proportional to its int24 value / 2^23
        for i, v in enumerate(vals):
            expected = (v << 8) / (2**31)
            assert abs(float(out[i]) - expected) < 1e-6, f"idx={i} val={v}"

    def test_returns_float32(self, tmp_path):
        path = _tmp_wav(tmp_path, [0, 1, -1])
        out = load_wav_float32(path)
        assert out.dtype == np.float32

    def test_wrong_sampwidth_raises(self, tmp_path):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(48000)
            wf.writeframes(b"\x00\x00")
        path = tmp_path / "bad.wav"
        path.write_bytes(buf.getvalue())
        with pytest.raises(ValueError, match="24-bit"):
            load_wav_float32(path)

    def test_wrong_channels_raises(self, tmp_path):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(2)  # stereo
            wf.setsampwidth(3)
            wf.setframerate(48000)
            wf.writeframes(b"\x00\x00\x00" * 2)
        path = tmp_path / "stereo.wav"
        path.write_bytes(buf.getvalue())
        with pytest.raises(ValueError, match="mono"):
            load_wav_float32(path)

    def test_wrong_samplerate_raises(self, tmp_path):
        path = _tmp_wav(tmp_path, [0], sample_rate=44100)
        with pytest.raises(ValueError, match="48000"):
            load_wav_float32(path)
