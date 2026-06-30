"""Unit tests for the per-plugin TTL parsers behind ``extra_data_fn``.

These exercise the pure ``(bundlepath, instance_number) -> PluginExtraData``
path with no LILV: each plugin's parser just reads ``effect-N/effect.ttl`` and
regexes it. The parsers were untestable while tangled into the LILV block loop;
the injected-customizer refactor pulled them into this clean seam.
"""

from __future__ import annotations

from pathlib import Path

from plugins.nam import NamData, _nam_extra_data
from plugins.notes.panel import NotesData, _notes_extra_data


def _write_effect(bundle: Path, instance_number: int, ttl: str) -> None:
    effect_dir = bundle / f"effect-{instance_number}"
    effect_dir.mkdir(parents=True)
    (effect_dir / "effect.ttl").write_text(ttl, encoding="utf-8")


# ── NAM ───────────────────────────────────────────────────────────────────────


def test_nam_extra_data_extracts_model_path(tmp_path: Path) -> None:
    _write_effect(
        tmp_path,
        3,
        '<file://plugin> <http://gareus.org/oss/lv2/nam#model> '
        '<file:///models/Marshall%20JCM800.nam> .\n',
    )
    assert _nam_extra_data(str(tmp_path), 3) == NamData(
        model_path="file:///models/Marshall%20JCM800.nam"
    )


def test_nam_extra_data_missing_file_returns_none(tmp_path: Path) -> None:
    assert _nam_extra_data(str(tmp_path), 7) is None


def test_nam_extra_data_no_model_triple_returns_none(tmp_path: Path) -> None:
    _write_effect(tmp_path, 1, "<file://plugin> a <http://example.com/Plugin> .\n")
    assert _nam_extra_data(str(tmp_path), 1) is None


# ── Notes ───────────────────────────────────────────────────────────────────


def test_notes_extra_data_extracts_text(tmp_path: Path) -> None:
    _write_effect(
        tmp_path,
        2,
        '<file://plugin> <http://open-music-kontrollers.ch/lv2/notes#text> '
        '"""line one\nline two""" .\n',
    )
    assert _notes_extra_data(str(tmp_path), 2) == NotesData(text="line one\nline two")


def test_notes_extra_data_missing_file_returns_none(tmp_path: Path) -> None:
    assert _notes_extra_data(str(tmp_path), 9) is None


def test_notes_extra_data_no_text_triple_returns_none(tmp_path: Path) -> None:
    _write_effect(tmp_path, 0, "<file://plugin> a <http://example.com/Notes> .\n")
    assert _notes_extra_data(str(tmp_path), 0) is None
