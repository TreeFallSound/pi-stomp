import numpy as np
import numpy.typing as npt


class RingBuffer:
    """Lock-free SPSC float32 ring buffer. Power-of-two capacity.

    Contract:
      - Exactly one writer thread (typically the JACK process callback) and
        one reader thread (typically a DSP worker). Multiple readers or
        writers are not safe.
      - ``write`` is RT-safe: no allocation, no blocking, drops oldest on
        overflow and returns the dropped count.
      - ``read_latest`` returns False if not enough data is buffered yet, or
        if the writer trampled our window mid-copy. Callers must handle False
        (typically: skip this DSP frame and try again next tick).

    Implementation notes (not relevant to callers): the read path uses a
    seqlock-style head re-check to detect a writer wrapping over the copied
    window; a transient under-count is possible during writer overflow but
    only ever causes a False return, never wrong data. Relies on CPython
    GIL atomicity for integer load/store and numpy slice-assign; free-
    threaded Python would need explicit acquire/release fences.
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
            self._buf[: n - split] = block[split:]
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
                out[split:] = self._buf[: n - split]
            # If the writer advanced by no more than `slack` samples while we
            # copied, our window cannot have been overwritten.
            if self._head - h1 <= slack:
                return True
        return False
