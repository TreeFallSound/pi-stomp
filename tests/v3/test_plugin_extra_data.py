"""Unit tests for the per-plugin TTL parsers registered as `extra_data_fn`.

These exercise the pure `ttl -> PluginExtraData` path: each plugin just
regexes a TTL string. The I/O (path resolution, file read) lives in the
registry's `lookup` and is covered by integration tests.
"""

from __future__ import annotations

from plugins.nam import NamData, _parse_nam
from plugins.notes.panel import NotesData, _parse_notes


# ── NAM ───────────────────────────────────────────────────────────────────────


def test_nam_parser_extracts_model_path() -> None:
    ttl = "<file://plugin> <http://gareus.org/oss/lv2/nam#model> <file:///models/Marshall%20JCM800.nam> .\n"
    assert _parse_nam(ttl) == NamData(model_path="file:///models/Marshall%20JCM800.nam")


def test_nam_parser_returns_none_when_no_model_triple() -> None:
    assert _parse_nam("<file://plugin> a <http://example.com/Plugin> .\n") is None


def test_nam_parser_returns_none_for_empty_ttl() -> None:
    assert _parse_nam("") is None


# ── Notes ───────────────────────────────────────────────────────────────────


def test_notes_parser_extracts_text() -> None:
    ttl = '<file://plugin> <http://open-music-kontrollers.ch/lv2/notes#text> """line one\nline two""" .\n'
    assert _parse_notes(ttl) == NotesData(text="line one\nline two")


def test_notes_parser_returns_none_when_no_text_triple() -> None:
    assert _parse_notes("<file://plugin> a <http://example.com/Notes> .\n") is None


def test_notes_parser_returns_none_for_empty_ttl() -> None:
    assert _parse_notes("") is None
