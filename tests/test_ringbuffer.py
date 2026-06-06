"""Lock-free SPSC ring buffer — unit tests."""

import sys
import threading
import time

import numpy as np
import pytest

from pistomp.tuner.ringbuffer import RingBuffer


@pytest.fixture
def fast_thread_switching():
    """Force CPython to switch threads aggressively, so the writer can
    actually preempt the reader mid-copy. With the default 5ms interval,
    a fast read_latest can complete entirely between switches and the
    concurrency hazards we want to test never manifest."""
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


class TestRingBufferWriteRead:
    def test_write_then_read_latest(self):
        rb = RingBuffer(1024)
        block = np.arange(256, dtype=np.float32)
        rb.write(block)
        out = np.zeros(256, dtype=np.float32)
        assert rb.read_latest(256, out)
        np.testing.assert_array_equal(out, block)

    def test_read_latest_insufficient_data(self):
        rb = RingBuffer(1024)
        rb.write(np.arange(100, dtype=np.float32))
        out = np.zeros(200, dtype=np.float32)
        assert not rb.read_latest(200, out)

    def test_multiple_writes_read_most_recent(self):
        rb = RingBuffer(1024)
        rb.write(np.zeros(256, dtype=np.float32))
        block2 = np.arange(256, dtype=np.float32) + 100
        rb.write(block2)
        out = np.zeros(512, dtype=np.float32)
        assert rb.read_latest(512, out)
        np.testing.assert_array_equal(out[:256], np.zeros(256, dtype=np.float32))
        np.testing.assert_array_equal(out[256:], block2)


class TestRingBufferWrapAround:
    def test_wrap_around_read(self):
        rb = RingBuffer(512)
        for i in range(3):
            rb.write(np.full(256, float(i + 1), dtype=np.float32))
        out = np.zeros(512, dtype=np.float32)
        assert rb.read_latest(512, out)
        assert out[0] == 2.0
        assert out[256] == 3.0


class TestRingBufferOverflow:
    def test_overflow_drops_oldest(self):
        rb = RingBuffer(256)
        rb.write(np.full(256, 1.0, dtype=np.float32))
        overflow = rb.write(np.full(128, 2.0, dtype=np.float32))
        assert overflow == 128
        out = np.zeros(256, dtype=np.float32)
        assert rb.read_latest(256, out)
        assert out[0] == 1.0
        assert out[128] == 2.0

    def test_overflow_all_dropped(self):
        rb = RingBuffer(256)
        rb.write(np.full(256, 1.0, dtype=np.float32))
        overflow = rb.write(np.full(512, 2.0, dtype=np.float32))
        assert overflow == 512
        out = np.zeros(256, dtype=np.float32)
        assert rb.read_latest(256, out)
        np.testing.assert_array_equal(out, np.full(256, 2.0, dtype=np.float32))


class TestRingBufferCapacityValidation:
    def test_non_power_of_two_raises(self):
        with pytest.raises(AssertionError, match="power of two"):
            RingBuffer(100)

    def test_zero_raises(self):
        with pytest.raises(AssertionError):
            RingBuffer(0)


class TestRingBufferReadLatestValidation:
    def test_read_exceeds_capacity_raises(self):
        rb = RingBuffer(256)
        rb.write(np.ones(256, dtype=np.float32))
        out = np.zeros(512, dtype=np.float32)
        with pytest.raises(AssertionError):
            rb.read_latest(512, out)


class TestRingBufferSize:
    def test_empty(self):
        rb = RingBuffer(1024)
        assert rb._size == 0

    def test_after_write(self):
        rb = RingBuffer(1024)
        rb.write(np.ones(256, dtype=np.float32))
        assert rb._size == 256

    def test_after_overflow(self):
        rb = RingBuffer(256)
        rb.write(np.ones(256, dtype=np.float32))
        rb.write(np.ones(256, dtype=np.float32))
        assert rb._size == 256


class TestRingBufferConcurrency:
    """The SPSC contract: one writer thread, one reader thread, read-only peek."""

    def test_spsc_no_torn_reads_under_concurrent_load(self, fast_thread_switching):
        """Writer pushes a strictly-increasing int counter; reader continuously
        read_latests. Every successful read must contain a contiguous run of
        consecutive integers (each adjacent pair differs by exactly 1.0). A
        torn read would show a mid-buffer discontinuity."""
        rb = RingBuffer(4096)
        n = 1024
        block_size = 256
        num_blocks = 50_000  # 12.8M samples — safely within float32 integer precision

        writer_done = threading.Event()
        torn_reads: list[np.ndarray] = []
        successful_reads = 0

        def writer():
            for k in range(num_blocks):
                block = np.arange(k * block_size, (k + 1) * block_size, dtype=np.float32)
                rb.write(block)
            writer_done.set()

        wt = threading.Thread(target=writer, daemon=True, name="rb-writer")
        wt.start()

        out = np.zeros(n, dtype=np.float32)
        while not writer_done.is_set():
            if rb.read_latest(n, out):
                diffs = np.diff(out)
                if not np.all(diffs == 1.0):
                    torn_reads.append(out.copy())
                successful_reads += 1

        wt.join(timeout=5.0)
        assert not wt.is_alive(), "writer did not finish in time"
        assert successful_reads > 0, "reader never observed a successful read"
        assert not torn_reads, (
            f"saw {len(torn_reads)} torn reads out of {successful_reads} successful — "
            f"SPSC integrity violated. first sample: {torn_reads[0][:8]} … {torn_reads[0][-8:]}"
        )

    def test_validation_rejects_overrun(self, monkeypatch):
        """Deterministic test of the seqlock validation: if the writer advances
        by more than slack = cap - n between the reader's snapshot of _head and
        its post-copy re-read, read_latest must return False. We script the two
        _head reads inside one read_latest call so the result doesn't depend on
        scheduling — important for catching regressions on free-threaded Python
        where real concurrent overruns are observable rather than rare."""
        rb = RingBuffer(256)
        rb.write(np.arange(256, dtype=np.float32))
        n = 128
        slack = 256 - n  # 128

        # read_latest reads self._head exactly twice per iteration: snapshot, then validate.
        scripted = iter([256, 256 + slack + 1])  # validate sees writer overran
        monkeypatch.setattr(RingBuffer, "_head", property(lambda self: next(scripted)), raising=False)

        out = np.zeros(n, dtype=np.float32)
        assert rb.read_latest(n, out, max_retries=0) is False

    def test_validation_accepts_within_slack(self, monkeypatch):
        """Mirror of the above: when the writer advanced by exactly `slack`
        samples between snapshot and validate, the reader's window is still
        untouched and read_latest must return True."""
        rb = RingBuffer(256)
        rb.write(np.arange(256, dtype=np.float32))
        n = 128
        slack = 256 - n

        scripted = iter([256, 256 + slack])  # exactly at the boundary — still safe
        monkeypatch.setattr(RingBuffer, "_head", property(lambda self: next(scripted)), raising=False)

        out = np.zeros(n, dtype=np.float32)
        assert rb.read_latest(n, out, max_retries=0) is True

    def test_retry_recovers_after_one_overrun(self, monkeypatch):
        """First attempt sees an overrun; retry sees a quiet writer and succeeds."""
        rb = RingBuffer(256)
        rb.write(np.arange(256, dtype=np.float32))
        n = 128
        slack = 256 - n

        scripted = iter(
            [
                # attempt 1: snapshot, validate → fail
                256,
                256 + slack + 1,
                # attempt 2: snapshot, validate → pass
                256,
                256,
            ]
        )
        monkeypatch.setattr(RingBuffer, "_head", property(lambda self: next(scripted)), raising=False)

        out = np.zeros(n, dtype=np.float32)
        assert rb.read_latest(n, out, max_retries=1) is True
