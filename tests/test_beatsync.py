"""BeatGrid — anchor + tick math for the metronome LED scheduler."""

import pytest

from modalapi.ws_protocol import BEAT_SYNC_NEW_BAR, BEAT_SYNC_TEMPO_CHANGED, BeatSyncMessage
from pistomp.beatsync import FLASH_US, STALE_AFTER_US, BeatGrid, TickState


def _anchor(t_us=0, bpm=120.0, bpb=4.0, beat_in_bar=0.0, flags=BEAT_SYNC_NEW_BAR) -> BeatSyncMessage:
    return BeatSyncMessage(t_us=t_us, bpm=bpm, bpb=bpb, beat_in_bar=beat_in_bar, flags=flags)


def _tempo_change(t_us=0, bpm=120.0, bpb=4.0, beat_in_bar=0.0) -> BeatSyncMessage:
    """A sample that mod-host sends for a bpm or bpb change. Its phase is not
    correct, thus the grid must take the tempo only."""
    return BeatSyncMessage(t_us=t_us, bpm=bpm, bpb=bpb, beat_in_bar=beat_in_bar, flags=BEAT_SYNC_TEMPO_CHANGED)


class TestUnanchored:
    def test_fresh_grid_is_not_anchored(self):
        assert BeatGrid().is_anchored is False

    def test_unanchored_tick_reports_unanchored(self):
        state = BeatGrid().tick(now_us=1_000_000)
        assert state.is_anchored is False
        assert state.is_flashing is False
        assert state.is_bar_start is False

    def test_clear_is_idempotent(self):
        g = BeatGrid()
        g.clear()
        g.clear()
        assert g.is_anchored is False


class TestAnchor:
    def test_anchor_marks_anchored(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        assert g.is_anchored is True

    def test_anchor_on_downbeat_flashes_and_marks_bar_start_immediately(self):
        """The bug fix: a clock sample that *is* a downbeat (beat_in_bar=0)
        must be visible at the anchor's own timestamp — waiting for a later
        crossing would mean is_bar_start never fires (it was already the
        modulo target, never something to cross into)."""
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0, beat_in_bar=0.0))
        state = g.tick(now_us=1_000_000)
        assert state.is_anchored is True
        assert state.is_flashing is True
        assert state.is_bar_start is True

    def test_tempo_change_sample_does_not_flash_immediately(self):
        """A bpm-change sample is not a crossing. It gives no flash until the
        next real beat boundary."""
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + FLASH_US + 1)
        g.on_anchor(_tempo_change(t_us=1_250_000, bpm=140.0, bpb=4.0, beat_in_bar=1.5))
        state = g.tick(now_us=1_250_000)
        assert state.is_anchored is True
        assert state.is_flashing is False

    def test_anchor_at_late_time_does_not_catch_up(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + 4 * 500_000)
        assert state.is_anchored is True
        assert state.is_flashing is True
        # One flash, not four — verify the next tick is past the flash window
        # and the *following* beat boundary fires exactly one more.
        state = g.tick(now_us=1_000_000 + 4 * 500_000 + FLASH_US + 1)
        assert state.is_flashing is False


class TestFlash:
    def test_first_beat_after_anchor_flashes(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + 500_000)
        assert state.is_flashing is True
        assert state.is_bar_start is False

    def test_flash_expires_after_flash_us(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 500_000)
        state = g.tick(now_us=1_000_000 + 500_000 + FLASH_US)
        assert state.is_flashing is False

    def test_late_tick_uses_source_boundary_for_flash_cutoff(self):
        g = BeatGrid()
        boundary = 1_000_000 + 500_000
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))

        state = g.tick(now_us=boundary + 20_000)
        assert state.is_flashing is True

        state = g.tick(now_us=boundary + FLASH_US)
        assert state.is_flashing is False

    def test_bar_start_marked_on_downbeat(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 500_000)
        g.tick(now_us=1_000_000 + 1_000_000)
        g.tick(now_us=1_000_000 + 1_500_000)
        state = g.tick(now_us=1_000_000 + 2_000_000)
        assert state.is_flashing is True
        assert state.is_bar_start is True

    def test_subsequent_beats_flash_in_sequence(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        flashes = []
        for i in range(8):
            t = 1_000_000 + 500_000 * (i + 1)
            state = g.tick(now_us=t)
            flashes.append(state.is_flashing)
        assert flashes == [True] * 8

    def test_subsequent_bar_starts_every_bpb_beats(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=0, bpm=120.0, bpb=4.0))
        bar_starts = []
        for i in range(8):
            t = 500_000 * (i + 1)
            state = g.tick(now_us=t)
            bar_starts.append(state.is_bar_start)
        assert bar_starts == [False, False, False, True, False, False, False, True]


class TestClear:
    def test_clear_after_anchor(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.clear()
        assert g.is_anchored is False
        state = g.tick(now_us=2_000_000)
        assert state.is_anchored is False

    def test_clear_mid_flash(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 500_000)
        g.clear()
        state = g.tick(now_us=1_000_000 + 600_000)
        assert state.is_flashing is False


class TestStaleTimeout:
    def test_stale_anchor_clears_on_tick(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + STALE_AFTER_US + 1)
        assert state.is_anchored is False

    def test_freshly_anchored_is_not_stale(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + STALE_AFTER_US - 1)
        assert state.is_anchored is True


class TestInvalidAnchor:
    def test_zero_bpm_clears_grid(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=0.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + 500_000)
        assert state.is_anchored is False

    def test_zero_bpb_clears_grid(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=0.0))
        state = g.tick(now_us=1_000_000 + 500_000)
        assert state.is_anchored is False


class TestReAnchor:
    def test_re_anchor_resets_beat_counter(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 1_500_000)
        g.on_anchor(_anchor(t_us=10_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=10_000_000 + 500_000)
        assert state.is_flashing is True
        assert state.is_bar_start is False

    def test_re_anchor_skips_missed_beats(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.on_anchor(_anchor(t_us=1_000_000 + 4_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + 4_000_000 + 500_000)
        assert state.is_flashing is True
        # First tick past the new anchor fires for the next live beat
        # (beat 1, not a bar start). The 4 missed beats did not cause a
        # flurry of catches-up.
        assert state.is_bar_start is False


class TestTickState:
    def test_tick_state_is_immutable(self):
        state = TickState(True, True, True, 120.0, 4.0)
        try:
            state.is_flashing = False  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("TickState should be frozen")


class TestBeatPhase:
    """beat_phase remains the normalized [0, 1) within-beat position used
    for loop position; flash brightness is driven by is_flashing."""

    def test_phase_zero_at_beat_boundary(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=0, bpm=120.0, bpb=4.0))  # 120bpm → 500ms/beat
        state = g.tick(now_us=500_000)  # exactly beat 1
        assert state.beat_phase == 0.0

    def test_phase_advances_within_beat(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=0, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=125_000)  # 1/4 of a 500ms beat
        assert 0.0 <= state.beat_phase < 1.0
        assert abs(state.beat_phase - 0.25) < 0.01

    def test_phase_resets_across_beat_boundary(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=0, bpm=120.0, bpb=4.0))
        g.tick(now_us=500_000)  # beat 1
        state = g.tick(now_us=750_000)  # halfway through beat 2
        assert abs(state.beat_phase - 0.5) < 0.01

    def test_phase_in_range_zero_to_one(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=0, bpm=120.0, bpb=4.0))
        for t_us in range(0, 2_000_000, 50_000):
            state = g.tick(now_us=t_us)
            assert 0.0 <= state.beat_phase < 1.0

    def test_phase_is_zero_when_unanchored(self):
        g = BeatGrid()
        state = g.tick(now_us=1_000_000)
        assert state.beat_phase == 0.0


class TestSetTempo:
    """A tempo change that arrives without a beat_sync. mod-ui's `transport`
    path (a tweak knob, a tap, a browser) writes the mod-host globals but
    emits no clock sample, thus the grid must take the new rate directly."""

    def test_set_tempo_changes_the_rate(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000)
        g.set_tempo(240.0, now_us=1_000_000)
        # At 240 BPM a beat is 250ms. The next crossing is at +250ms, not +500ms.
        assert g.tick(now_us=1_000_000 + 249_000).is_flashing is False
        assert g.tick(now_us=1_000_000 + 251_000).is_flashing is True

    def test_set_tempo_keeps_the_phase_continuous(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        half_beat_us = 1_000_000 + 250_000
        assert g.tick(now_us=half_beat_us).beat_phase == pytest.approx(0.5)
        g.set_tempo(240.0, now_us=half_beat_us)
        assert g.tick(now_us=half_beat_us).beat_phase == pytest.approx(0.5)

    def test_set_tempo_reports_the_new_bpm(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.set_tempo(90.0, now_us=1_000_000)
        assert g.tick(now_us=1_000_000).bpm == pytest.approx(90.0)

    def test_set_tempo_does_not_anchor_an_unanchored_grid(self):
        g = BeatGrid()
        g.set_tempo(140.0, now_us=1_000_000)
        assert g.is_anchored is False

    def test_set_tempo_ignores_a_non_positive_bpm(self):
        g = BeatGrid()
        g.on_anchor(_anchor(t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.set_tempo(0.0, now_us=1_000_000)
        assert g.tick(now_us=1_000_000).bpm == pytest.approx(120.0)
        assert g.is_anchored is True
