import threading
import numpy as np
import numpy.typing as npt


class RingBuffer:
    """SPSC fixed-capacity float32 ring buffer."""

    def __init__(self, capacity: int = 16384) -> None:
        assert capacity > 0 and (capacity & (capacity - 1)) == 0, "capacity must be a power of two"
        self._buf: npt.NDArray[np.float32] = np.zeros(capacity, dtype=np.float32)
        self._cap = capacity
        self._mask = capacity - 1
        self._head = 0  # write position
        self._tail = 0  # read position (oldest sample)
        self._lock = threading.Lock()

    @property
    def _size(self) -> int:
        return self._head - self._tail

    def write(self, block: npt.NDArray[np.float32]) -> int:
        """Write samples; drops oldest on overflow. Returns dropped sample count."""
        n = len(block)
        with self._lock:
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

    def read_latest(self, n: int, out: npt.NDArray[np.float32]) -> bool:
        """Copy the most-recent n samples into out. Returns False if fewer than n available."""
        with self._lock:
            if self._size < n:
                return False
            start = (self._head - n) & self._mask
            end = start + n
            if end <= self._cap:
                out[:] = self._buf[start:end]
            else:
                split = self._cap - start
                out[:split] = self._buf[start:]
                out[split:] = self._buf[:n - split]
        return True
