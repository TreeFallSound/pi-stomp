"""Unit tests for pistomp/config_overrides.py."""

from pathlib import Path

import pytest
import yaml

from pistomp.config_overrides import NULL, UNSET, get_effective, load_override, set_field, write_override


# ---------------------------------------------------------------------------
# load_override
# ---------------------------------------------------------------------------


def test_load_override_missing(tmp_path: Path):
    assert load_override(tmp_path) is None


def test_load_override_exists(tmp_path: Path):
    (tmp_path / "config.yml").write_text(
        "hardware:\n  footswitches:\n  - id: 0\n    longpress: next_snapshot\n"
    )
    doc = load_override(tmp_path)
    assert doc is not None
    assert doc["hardware"]["footswitches"][0]["longpress"] == "next_snapshot"


# ---------------------------------------------------------------------------
# write_override
# ---------------------------------------------------------------------------


def test_write_override_creates_file(tmp_path: Path):
    doc = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot"}]}}
    write_override(tmp_path, doc)
    assert (tmp_path / "config.yml").exists()


def test_write_override_roundtrip(tmp_path: Path):
    doc = {"hardware": {"footswitches": [{"id": 0, "color": "Red"}]}}
    write_override(tmp_path, doc)
    loaded = load_override(tmp_path)
    assert loaded is not None
    assert loaded["hardware"]["footswitches"][0]["color"] == "Red"


def test_write_override_deletes_when_empty_doc(tmp_path: Path):
    (tmp_path / "config.yml").write_text("hardware: {}\n")
    write_override(tmp_path, {})
    assert not (tmp_path / "config.yml").exists()


def test_write_override_deletes_when_none(tmp_path: Path):
    (tmp_path / "config.yml").write_text("hardware: {}\n")
    write_override(tmp_path, None)
    assert not (tmp_path / "config.yml").exists()


def test_write_override_no_error_deleting_nonexistent(tmp_path: Path):
    write_override(tmp_path, None)  # file never existed — should not raise


# ---------------------------------------------------------------------------
# set_field — value
# ---------------------------------------------------------------------------


def test_set_field_creates_entry():
    doc: dict = {}
    set_field(doc, "footswitch", 0, "longpress", "next_snapshot")
    assert doc["hardware"]["footswitches"][0]["longpress"] == "next_snapshot"
    assert doc["hardware"]["footswitches"][0]["id"] == 0


def test_set_field_updates_existing_entry():
    doc: dict = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot"}]}}
    set_field(doc, "footswitch", 0, "longpress", "toggle_bypass")
    assert doc["hardware"]["footswitches"][0]["longpress"] == "toggle_bypass"


def test_set_field_adds_key_to_existing_entry():
    doc: dict = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot"}]}}
    set_field(doc, "footswitch", 0, "color", "Red")
    entry = doc["hardware"]["footswitches"][0]
    assert entry["longpress"] == "next_snapshot"
    assert entry["color"] == "Red"


def test_set_field_encoder_uses_encoders_list():
    doc: dict = {}
    set_field(doc, "encoder", 2, "longpress", "previous_snapshot")
    entry = doc["hardware"]["encoders"][0]
    assert entry["id"] == 2
    assert entry["longpress"] == "previous_snapshot"


def test_set_field_does_not_overwrite_other_ids():
    doc: dict = {"hardware": {"footswitches": [{"id": 1, "color": "Blue"}]}}
    set_field(doc, "footswitch", 0, "color", "Red")
    entries = doc["hardware"]["footswitches"]
    assert len(entries) == 2
    assert next(e for e in entries if e["id"] == 1)["color"] == "Blue"
    assert next(e for e in entries if e["id"] == 0)["color"] == "Red"


# ---------------------------------------------------------------------------
# set_field — UNSET
# ---------------------------------------------------------------------------


def test_set_field_unset_removes_key():
    doc: dict = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot", "color": "Red"}]}}
    set_field(doc, "footswitch", 0, "longpress", UNSET)
    assert "longpress" not in doc["hardware"]["footswitches"][0]
    assert doc["hardware"]["footswitches"][0]["color"] == "Red"


def test_set_field_unset_prunes_empty_entry():
    doc: dict = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot"}]}}
    set_field(doc, "footswitch", 0, "longpress", UNSET)
    assert doc.get("hardware", {}).get("footswitches", []) == []


def test_set_field_unset_prunes_hardware_when_last_list_empty():
    doc: dict = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot"}]}}
    set_field(doc, "footswitch", 0, "longpress", UNSET)
    assert "hardware" not in doc


def test_set_field_unset_leaves_other_id_intact():
    doc: dict = {"hardware": {"footswitches": [
        {"id": 0, "color": "Red"},
        {"id": 1, "color": "Blue"},
    ]}}
    set_field(doc, "footswitch", 0, "color", UNSET)
    entries = doc["hardware"]["footswitches"]
    assert len(entries) == 1
    assert entries[0]["id"] == 1


def test_set_field_unset_missing_key_is_noop():
    doc: dict = {"hardware": {"footswitches": [{"id": 0, "color": "Red"}]}}
    set_field(doc, "footswitch", 0, "longpress", UNSET)
    assert doc["hardware"]["footswitches"][0] == {"id": 0, "color": "Red"}


# ---------------------------------------------------------------------------
# set_field — NULL
# ---------------------------------------------------------------------------


def test_set_field_null_sets_none():
    doc: dict = {}
    set_field(doc, "footswitch", 0, "disable", NULL)
    assert doc["hardware"]["footswitches"][0]["disable"] is None


# ---------------------------------------------------------------------------
# get_effective
# ---------------------------------------------------------------------------


def test_get_effective_override_wins():
    default = {"hardware": {"footswitches": [{"id": 0, "longpress": "toggle_bypass"}]}}
    override = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot"}]}}
    assert get_effective(default, override, "footswitch", 0, "longpress") == "next_snapshot"


def test_get_effective_falls_back_to_default():
    default = {"hardware": {"footswitches": [{"id": 0, "longpress": "toggle_bypass"}]}}
    assert get_effective(default, None, "footswitch", 0, "longpress") == "toggle_bypass"


def test_get_effective_none_when_absent_everywhere():
    assert get_effective({}, None, "footswitch", 0, "longpress") is None


def test_get_effective_override_none_wins_over_default():
    """Explicit null in override should suppress the default value."""
    default = {"hardware": {"footswitches": [{"id": 0, "longpress": "toggle_bypass"}]}}
    override = {"hardware": {"footswitches": [{"id": 0, "longpress": None}]}}
    assert get_effective(default, override, "footswitch", 0, "longpress") is None


def test_get_effective_key_absent_from_override_entry_falls_back():
    default = {"hardware": {"footswitches": [{"id": 0, "color": "Blue"}]}}
    override = {"hardware": {"footswitches": [{"id": 0, "longpress": "next_snapshot"}]}}
    assert get_effective(default, override, "footswitch", 0, "color") == "Blue"
