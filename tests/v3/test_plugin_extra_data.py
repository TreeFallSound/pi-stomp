"""Unit tests for the per-plugin TTL parsers registered as `extra_data_fn`.

These exercise the pure `ttl -> PluginExtraData` path: each plugin just
regexes a TTL string. The I/O (path resolution, file read) lives in the
registry's `lookup` and is covered by integration tests.
"""

from __future__ import annotations

from plugins.nam import NamData, _parse_nam, _patch_nam
from plugins.notes.panel import NotesData, _parse_notes, _patch_notes


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


def test_notes_parser_accepts_single_line_short_quotes() -> None:
    # Turtle only long-quotes when it has to; mod-ui writes one-liners plain.
    ttl = '<file://plugin> <http://open-music-kontrollers.ch/lv2/notes#text> "Abc123" .\n'
    assert _parse_notes(ttl) == NotesData(text="Abc123")


def test_notes_parser_unescapes_short_quoted_text() -> None:
    ttl = r'<x> <http://open-music-kontrollers.ch/lv2/notes#text> "say \"hi\"\nbye" .' + "\n"
    assert _parse_notes(ttl) == NotesData(text='say "hi"\nbye')


# ── patch_set parsers ─────────────────────────────────────────────────────────


def test_nam_patch_parser_takes_model_path() -> None:
    assert _patch_nam(
        "http://github.com/mikeoliphant/neural-amp-modeler-lv2#model",
        "/home/pistomp/data/user-files/NAM Models/Clean (G1 L0 B1 T1).nam",
    ) == NamData(model_path="/home/pistomp/data/user-files/NAM Models/Clean (G1 L0 B1 T1).nam")


def test_nam_patch_parser_ignores_other_properties() -> None:
    assert _patch_nam("http://example.com/other", "/models/x.nam") is None


def test_nam_patch_parser_ignores_empty_model() -> None:
    # An unloaded NAM slot patches "" — keep the generic tile name.
    assert _patch_nam("http://github.com/mikeoliphant/neural-amp-modeler-lv2#model", "") is None


def test_notes_patch_parser_takes_text_verbatim() -> None:
    # Wire values are unquoted already — no Turtle escaping to undo.
    assert _patch_notes("http://open-music-kontrollers.ch/lv2/notes#text", "Abc123") == NotesData(
        text="Abc123"
    )


def test_notes_patch_parser_ignores_other_properties() -> None:
    assert _patch_notes("http://open-music-kontrollers.ch/lv2/notes#fontHeight", "25") is None
