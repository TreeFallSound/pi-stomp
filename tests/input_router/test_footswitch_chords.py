"""Unit tests for FootswitchChords — the instance-scoped longpress/chord resolver.

Covers registration (membership counting, unknown-group rejection, rebuild),
singleton timeout firing, and pair (chord) resolution within / outside the
window. Time is driven deterministically via the module's time.monotonic.
"""

from types import SimpleNamespace

import pytest

from pistomp.footswitch_chords import FootswitchChords


def _fs(id, groups):
    """Minimal stand-in for a Footswitch: only id + longpress_groups are read."""
    return SimpleNamespace(id=id, longpress_groups=list(groups))


def _clock(monkeypatch, value):
    monkeypatch.setattr("pistomp.footswitch_chords.time.monotonic", lambda: value)


@pytest.fixture
def chords():
    ch = FootswitchChords()
    ch.rebuild(
        {
            "next_snapshot": lambda: None,
            "previous_snapshot": lambda: None,
            "toggle_bypass": lambda: None,
        }
    )
    return ch


class TestRegister:
    def test_known_group_registers_with_membership_one(self, chords):
        chords.register(["next_snapshot"])
        assert set(chords.groups) == {"next_snapshot"}
        assert chords.groups["next_snapshot"].number_in_group == 1

    def test_unknown_group_is_ignored(self, chords):
        chords.register(["not_a_real_group"])
        assert chords.groups == {}

    def test_two_members_increment_membership(self, chords):
        chords.register(["toggle_bypass"])
        chords.register(["toggle_bypass"])
        assert chords.groups["toggle_bypass"].number_in_group == 2

    def test_rebuild_clears_groups_and_swaps_callbacks(self, chords):
        chords.register(["next_snapshot"])
        new_callbacks = {"next_snapshot": lambda: None}
        chords.rebuild(new_callbacks)
        assert chords.groups == {}
        assert chords.callbacks is new_callbacks


class TestSingleton:
    def test_lone_member_does_not_fire_within_window(self, chords, monkeypatch):
        chords.register(["next_snapshot"])
        _clock(monkeypatch, 100.0)
        chords.observe(_fs(0, ["next_snapshot"]), timestamp=100.0)
        # Still inside the chord window — hold for a possible partner.
        assert chords.tick() == []

    def test_lone_member_fires_after_window(self, chords, monkeypatch):
        chords.register(["next_snapshot"])
        chords.observe(_fs(0, ["next_snapshot"]), timestamp=100.0)
        _clock(monkeypatch, 100.0 + FootswitchChords.WINDOW + 0.01)
        assert chords.tick() == ["next_snapshot"]

    def test_singleton_cleared_after_firing(self, chords, monkeypatch):
        chords.register(["next_snapshot"])
        chords.observe(_fs(0, ["next_snapshot"]), timestamp=100.0)
        _clock(monkeypatch, 101.0)
        assert chords.tick() == ["next_snapshot"]
        # A second tick has nothing pending.
        assert chords.tick() == []

    def test_member_of_two_group_never_singleton_fires(self, chords, monkeypatch):
        # Two footswitches share the group; a single longpress must wait for a
        # partner (chord), never resolve as a singleton.
        chords.register(["toggle_bypass"])
        chords.register(["toggle_bypass"])
        chords.observe(_fs(0, ["toggle_bypass"]), timestamp=100.0)
        _clock(monkeypatch, 101.0)
        assert chords.tick() == []


class TestChord:
    def test_two_members_within_window_fire(self, chords):
        chords.register(["toggle_bypass"])
        chords.register(["toggle_bypass"])
        chords.observe(_fs(0, ["toggle_bypass"]), timestamp=100.0)
        chords.observe(_fs(1, ["toggle_bypass"]), timestamp=100.0 + FootswitchChords.WINDOW / 2)
        assert chords.tick() == ["toggle_bypass"]

    def test_two_members_outside_window_do_not_fire(self, chords):
        chords.register(["toggle_bypass"])
        chords.register(["toggle_bypass"])
        chords.observe(_fs(0, ["toggle_bypass"]), timestamp=100.0)
        chords.observe(_fs(1, ["toggle_bypass"]), timestamp=100.0 + FootswitchChords.WINDOW + 0.1)
        assert chords.tick() == []
        # Both pending timestamps were consumed regardless.
        assert chords.groups["toggle_bypass"].timestamps == {}
