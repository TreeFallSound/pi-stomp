import numpy as np
import numpy.typing as npt


class RingBuffer:
    """Lock-free SPSC fixed-capacity float32 ring buffer.

    The JACK process callback is the sole writer; the DSP thread is the sole
    reader. The writer mutates both ``_head`` and ``_tail`` (the latter only on
    overflow); the reader is read-only. The writer publishes new samples by
    incrementing ``_head`` *after* the buffer copy, so any reader that observes
    a given ``_head`` value also observes the samples behind it.

    ``read_latest`` uses a seqlock-style re-check: it snapshots ``_head``,
    copies, then verifies the writer hasn't advanced far enough to wrap over
    the copied region. This is necessary because between the size check and
    the copy completing, the writer can overwrite the bytes we're reading.

    GIL safety: under CPython's GIL, integer attribute load/store is atomic
    and numpy slice assignment of small float32 blocks does not release the
    GIL, so we don't need explicit barriers. Free-threaded Python would
    require atomics and acquire/release fences.
    """

    def __init__(self, capacity: int = 16384) -> None:
        assert capacity > 0 and (capacity & (capacity - 1)) == 0, "capacity must be a power of two"
        self._buf: npt.NDArray[np.float32] = np.zeros(capacity, dtype=np.float32)
        self._cap = capacity
        self._mask = capacity - 1
        self._head = 0  # write position (monotonic, writer only)
        self._tail = 0  # read position (monotonic, writer advances on overflow)

    @property
    def _size(self) -> int:
        return self._head - self._tail

    def write(self, block: npt.NDArray[np.float32]) -> int:
        """Write samples; drops oldest on overflow. Returns dropped sample count.

        Called from the JACK process callback — must not block.
        """
        n = len(block)
        overflow = max(0, self._size + n - self._cap)
        self._tail += overflow
        start = self._head & self._mask
        end = start + n
        if end <= self._cap:
            self._buf[start:end] = block
        else:
            split = self._cap - start
            self._buf[start:] = block[:split]
            self._buf[:n - split] = block[split:]
        self._head += n
        return overflow

    def read_latest(self, n: int, out: npt.NDArray[np.float32], max_retries: int = 2) -> bool:
        """Copy the most-recent n samples into *out*. Returns False if fewer than n
        available, or if the writer wrapped over our window faster than we could
        retry.

        Called from the DSP thread — must not block.
        """
        assert n <= self._cap, "read size exceeds buffer capacity"
        slack = self._cap - n
        for _ in range(max_retries + 1):
            h1 = self._head
            if h1 - self._tail < n:
                return False
            start = (h1 - n) & self._mask
            end = start + n
            if end <= self._cap:
                out[:] = self._buf[start:end]
            else:
                split = self._cap - start
                out[:split] = self._buf[start:]
                out[split:] = self._buf[:n - split]
            # If the writer advanced by no more than `slack` samples while we
            # copied, our window cannot have been overwritten.
            if self._head - h1 <= slack:
                return True
        return False
