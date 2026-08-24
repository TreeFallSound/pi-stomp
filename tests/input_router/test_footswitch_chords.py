"""Unit tests for FootswitchChords — the instance-scoped longpress/chord resolver.

Resolution is synchronous: a chord is decided at the first member's longpress
delivery by reading physical hold state, so both chords and lone longpresses
fire at the stomp with no deferral. Covers registration, solo firing, chord
admission (all members held and unspent), the spent-group rule that silences
the remaining members, and release clearing.
"""

from types import SimpleNamespace

import pytest

import pistomp.switchstate as switchstate
from pistomp.footswitch_chords import FootswitchChords

RELEASED = switchstate.Value.RELEASED
PRESSED = switchstate.Value.PRESSED
LONGPRESSED = switchstate.Value.LONGPRESSED


def _fs(id, groups, press_state=RELEASED):
    """Minimal stand-in for a Footswitch: id, longpress_groups, press_state."""
    return SimpleNamespace(id=id, longpress_groups=list(groups), press_state=press_state)


def _deliver(chords, fs):
    """A longpress delivery: the switch itself is LONGPRESSED by the time its
    callback runs (both detectors set state before dispatching)."""
    fs.press_state = LONGPRESSED
    return chords.observe(fs)


@pytest.fixture
def chords():
    ch = FootswitchChords()
    ch.rebuild(
        {
            "next_snapshot": lambda: None,
            "previous_snapshot": lambda: None,
            "toggle_bypass": lambda: None,
            "previous_pedalboard": lambda: None,
        }
    )
    return ch


class TestRegister:
    def test_known_group_registers_one_member(self, chords):
        fs0 = _fs(0, ["next_snapshot"])
        chords.register(fs0)
        assert set(chords.groups) == {"next_snapshot"}
        assert chords.groups["next_snapshot"].members == [fs0]

    def test_unknown_group_is_ignored_and_warns(self, chords, caplog):
        chords.register(_fs(0, ["next_pedalboad"]))
        assert chords.groups == {}
        assert "next_pedalboad" in caplog.text

    def test_two_members_both_recorded(self, chords):
        fs0, fs1 = _fs(0, ["toggle_bypass"]), _fs(1, ["toggle_bypass"])
        chords.register(fs0)
        chords.register(fs1)
        assert chords.groups["toggle_bypass"].members == [fs0, fs1]

    def test_rebuild_clears_groups_and_swaps_callbacks(self, chords):
        chords.register(_fs(0, ["next_snapshot"]))
        new_callbacks = {"next_snapshot": lambda: None}
        chords.rebuild(new_callbacks)
        assert chords.groups == {}
        assert chords.callbacks is new_callbacks


class TestSolo:
    def test_lone_member_fires_at_the_stomp(self, chords):
        fs0 = _fs(0, ["next_snapshot"])
        chords.register(fs0)
        assert _deliver(chords, fs0) == ["next_snapshot"]

    def test_chord_member_with_no_partner_held_fires_its_solo(self, chords):
        # The bug report's shape: fs0 owns a solo action and shares a chord
        # group with fs1. Stomped alone, only the solo action fires.
        fs0 = _fs(0, ["previous_snapshot", "previous_pedalboard"])
        fs1 = _fs(1, ["next_snapshot", "previous_pedalboard"])
        chords.register(fs0)
        chords.register(fs1)
        assert _deliver(chords, fs0) == ["previous_snapshot"]

    def test_partner_already_longpressed_is_not_a_chord(self, chords):
        # A foot parked on fs1 since long ago already spent its longpress;
        # it must not turn a later fs0 stomp into a chord.
        fs0 = _fs(0, ["previous_snapshot", "previous_pedalboard"])
        fs1 = _fs(1, ["next_snapshot", "previous_pedalboard"], press_state=LONGPRESSED)
        chords.register(fs0)
        chords.register(fs1)
        assert _deliver(chords, fs0) == ["previous_snapshot"]


class TestChord:
    def test_chord_fires_at_first_delivery_and_suppresses_solo(self, chords):
        # Both held; fs0 matures first. The chord resolves there — fs1's own
        # longpress has not been delivered yet and is not waited for.
        fs0 = _fs(0, ["previous_snapshot", "previous_pedalboard"])
        fs1 = _fs(1, ["next_snapshot", "previous_pedalboard"], press_state=PRESSED)
        chords.register(fs0)
        chords.register(fs1)
        assert _deliver(chords, fs0) == ["previous_pedalboard"]

    def test_remaining_member_delivery_is_silent(self, chords):
        fs0 = _fs(0, ["previous_snapshot", "previous_pedalboard"])
        fs1 = _fs(1, ["next_snapshot", "previous_pedalboard"], press_state=PRESSED)
        chords.register(fs0)
        chords.register(fs1)
        assert _deliver(chords, fs0) == ["previous_pedalboard"]
        # fs1 matures ~50ms later; the chord already fired, so nothing more.
        assert _deliver(chords, fs1) == []

    def test_spent_clears_once_all_members_release(self, chords):
        fs0 = _fs(0, ["previous_snapshot", "previous_pedalboard"])
        fs1 = _fs(1, ["next_snapshot", "previous_pedalboard"], press_state=PRESSED)
        chords.register(fs0)
        chords.register(fs1)
        assert _deliver(chords, fs0) == ["previous_pedalboard"]
        fs0.press_state = RELEASED
        fs1.press_state = RELEASED
        chords.poll()  # the 10ms loop re-arms the group once every foot is up
        # A fresh lone stomp on fs0 is unaffected by the previous chord.
        assert _deliver(chords, fs0) == ["previous_snapshot"]

    def test_group_stays_spent_while_any_member_is_still_held(self, chords):
        # Lifting fs0 right after the chord fired must not let fs1's own
        # longpress land as a solo action — one gesture, one action.
        fs0 = _fs(0, ["previous_snapshot", "previous_pedalboard"])
        fs1 = _fs(1, ["next_snapshot", "previous_pedalboard"], press_state=PRESSED)
        chords.register(fs0)
        chords.register(fs1)
        assert _deliver(chords, fs0) == ["previous_pedalboard"]
        fs0.press_state = RELEASED
        chords.poll()
        assert _deliver(chords, fs1) == []


class TestAllMembersRequired:
    def _three(self, chords):
        fs0 = _fs(0, ["previous_snapshot", "toggle_bypass"])
        fs1 = _fs(1, ["next_snapshot", "toggle_bypass"])
        fs2 = _fs(2, ["previous_pedalboard", "toggle_bypass"])
        for fs in (fs0, fs1, fs2):
            chords.register(fs)
        return fs0, fs1, fs2

    def test_partial_group_does_not_fire_the_chord(self, chords):
        fs0, fs1, _ = self._three(chords)
        fs1.press_state = PRESSED  # fs2 not held
        assert _deliver(chords, fs0) == ["previous_snapshot"]

    def test_all_members_held_fires_the_chord(self, chords):
        fs0, fs1, fs2 = self._three(chords)
        fs1.press_state = PRESSED
        fs2.press_state = PRESSED
        assert _deliver(chords, fs0) == ["toggle_bypass"]
        assert _deliver(chords, fs1) == []
        assert _deliver(chords, fs2) == []

    def test_larger_satisfied_group_wins(self, chords):
        # fs0/fs1 share a pair group; all three share a triple. Everything
        # held → the most specific (largest) satisfied group fires.
        fs0 = _fs(0, ["previous_pedalboard", "toggle_bypass"])
        fs1 = _fs(1, ["previous_pedalboard", "toggle_bypass"], press_state=PRESSED)
        fs2 = _fs(2, ["toggle_bypass"], press_state=PRESSED)
        for fs in (fs0, fs1, fs2):
            chords.register(fs)
        assert _deliver(chords, fs0) == ["toggle_bypass"]
