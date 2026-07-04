"""BeatGrid — anchor + tick math for the metronome LED scheduler."""

from modalapi.ws_protocol import BeatSyncMessage
from pistomp.beatsync import FLASH_US, STALE_AFTER_US, BeatGrid, TickState


def _anchor(bar=0, t_us=0, bpm=120.0, bpb=4.0) -> BeatSyncMessage:
    return BeatSyncMessage(bar=bar, t_us=t_us, bpm=bpm, bpb=bpb)


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
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        assert g.is_anchored is True

    def test_anchor_does_not_flash_immediately(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000)
        assert state.is_anchored is True
        assert state.is_flashing is False

    def test_anchor_at_late_time_does_not_catch_up(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
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
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + 500_000)
        assert state.is_flashing is True
        assert state.is_bar_start is False

    def test_flash_expires_after_flash_us(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 500_000)
        state = g.tick(now_us=1_000_000 + 500_000 + FLASH_US)
        assert state.is_flashing is False

    def test_bar_start_marked_on_downbeat(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 500_000)
        g.tick(now_us=1_000_000 + 1_000_000)
        g.tick(now_us=1_000_000 + 1_500_000)
        state = g.tick(now_us=1_000_000 + 2_000_000)
        assert state.is_flashing is True
        assert state.is_bar_start is True

    def test_subsequent_beats_flash_in_sequence(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        flashes = []
        for i in range(8):
            t = 1_000_000 + 500_000 * (i + 1)
            state = g.tick(now_us=t)
            flashes.append(state.is_flashing)
        assert flashes == [True] * 8

    def test_subsequent_bar_starts_every_bpb_beats(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=0, bpm=120.0, bpb=4.0))
        bar_starts = []
        for i in range(8):
            t = 500_000 * (i + 1)
            state = g.tick(now_us=t)
            bar_starts.append(state.is_bar_start)
        assert bar_starts == [False, False, False, True, False, False, False, True]


class TestClear:
    def test_clear_after_anchor(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.clear()
        assert g.is_anchored is False
        state = g.tick(now_us=2_000_000)
        assert state.is_anchored is False

    def test_clear_mid_flash(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 500_000)
        g.clear()
        state = g.tick(now_us=1_000_000 + 600_000)
        assert state.is_flashing is False


class TestStaleTimeout:
    def test_stale_anchor_clears_on_tick(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + STALE_AFTER_US + 1)
        assert state.is_anchored is False

    def test_freshly_anchored_is_not_stale(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + STALE_AFTER_US - 1)
        assert state.is_anchored is True


class TestInvalidAnchor:
    def test_zero_bpm_clears_grid(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=0.0, bpb=4.0))
        state = g.tick(now_us=1_000_000 + 500_000)
        assert state.is_anchored is False

    def test_zero_bpb_clears_grid(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=0.0))
        state = g.tick(now_us=1_000_000 + 500_000)
        assert state.is_anchored is False


class TestReAnchor:
    def test_re_anchor_resets_beat_counter(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.tick(now_us=1_000_000 + 1_500_000)
        g.on_anchor(_anchor(bar=5, t_us=10_000_000, bpm=120.0, bpb=4.0))
        state = g.tick(now_us=10_000_000 + 500_000)
        assert state.is_flashing is True
        assert state.is_bar_start is False

    def test_re_anchor_skips_missed_beats(self):
        g = BeatGrid()
        g.on_anchor(_anchor(bar=0, t_us=1_000_000, bpm=120.0, bpb=4.0))
        g.on_anchor(_anchor(bar=0, t_us=1_000_000 + 4_000_000, bpm=120.0, bpb=4.0))
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
