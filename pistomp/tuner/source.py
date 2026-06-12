import math
import threading
import time
from typing import Any, Callable, Protocol

import numpy as np
import numpy.typing as npt


class AudioSource(Protocol):
    @property
    def sample_rate(self) -> int: ...
    def start(self, on_samples: Callable[[npt.NDArray[np.float32]], Any]) -> None: ...
    def stop(self) -> None: ...


class TunerSourceFactory(Protocol):
    def __call__(self, port: str, *, name: str) -> AudioSource: ...


class JackSource:
    """Reads audio from a JACK capture port."""

    def __init__(self, capture_port: str = "system:capture_1", *, name: str = "pistomp-tuner") -> None:
        self._capture_port = capture_port
        self._client_name = name
        self._client = None
        self._on_samples: Callable[[npt.NDArray[np.float32]], None] | None = None
        self._sample_rate: int = 48000  # placeholder; overwritten in start()

    @property
    def sample_rate(self) -> int:
        if self._client is None:
            raise RuntimeError("sample_rate is not available until start() is called")
        return self._sample_rate

    def start(self, on_samples: Callable[[npt.NDArray[np.float32]], None]) -> None:
        import jack  # type: ignore[import-untyped]

        self._on_samples = on_samples
        self._client = jack.Client(self._client_name, no_start_server=True)
        self._sample_rate = self._client.samplerate

        port = self._client.inports.register("in")

        @self._client.set_process_callback
        def process(frames: int) -> None:
            if self._on_samples is not None:
                self._on_samples(port.get_array())  # pyright: ignore[reportAttributeAccessIssue]

        self._client.activate()
        self._client.connect(self._capture_port, port)

    def stop(self) -> None:
        if self._client is not None:
            # Silence the process callback before teardown (prevents deadlock w/JACK)
            self._on_samples = None
            try:
                self._client.deactivate()
                self._client.close()
            except Exception:
                pass
            self._client = None


class _ToneBase:
    """Base for square-wave tone generators. Subclasses implement _freq_at(t)."""

    BLOCK_SIZE = 256

    def __init__(self, sample_rate: int = 48000) -> None:
        self._sample_rate = sample_rate
        self._thread: threading.Thread | None = None
        self._running = False
        self._on_samples: Callable[[npt.NDArray[np.float32]], Any] | None = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _freq_at(self, t_elapsed: float) -> float:
        raise NotImplementedError

    def start(self, on_samples: Callable[[npt.NDArray[np.float32]], Any]) -> None:
        self._on_samples = on_samples
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="tone-source")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        phase = 0.0
        block_dur = self.BLOCK_SIZE / self.sample_rate
        t_elapsed = 0.0

        while self._running:
            t0 = time.monotonic()
            freq = self._freq_at(t_elapsed)
            period = self.sample_rate / freq
            buf = np.empty(self.BLOCK_SIZE, dtype=np.float32)
            for i in range(self.BLOCK_SIZE):
                buf[i] = 1.0 - 4.0 * abs((phase % period) / period - 0.5)
                phase += 1.0
            if self._on_samples is not None:
                self._on_samples(buf)
            elapsed = time.monotonic() - t0
            t_elapsed += block_dur
            sleep = block_dur - elapsed
            if sleep > 0:
                time.sleep(sleep)


class ToneSource(_ToneBase):
    """Fixed-frequency square-wave source."""

    def __init__(self, freq_hz: float, sample_rate: int = 48000) -> None:
        super().__init__(sample_rate)
        self._freq = freq_hz

    def _freq_at(self, t_elapsed: float) -> float:
        return self._freq


class ToneSweepSource(_ToneBase):
    """Square-wave source that ping-pongs linearly over ±SWEEP_CENTS around a centre frequency."""

    SWEEP_CENTS = 60.0
    SWEEP_PERIOD_S = 8.0

    def __init__(self, center_hz: float = 440.0, sample_rate: int = 48000) -> None:
        super().__init__(sample_rate)
        self._center = center_hz

    def _freq_at(self, t_elapsed: float) -> float:
        # triangular wave in [0, 1]: 0 → 1 → 0 over one period
        phase = (t_elapsed % self.SWEEP_PERIOD_S) / self.SWEEP_PERIOD_S
        triangle = 1.0 - abs(2.0 * phase - 1.0)
        cents = self.SWEEP_CENTS * (2.0 * triangle - 1.0)  # -SWEEP → +SWEEP → -SWEEP
        return self._center * math.pow(2.0, cents / 1200.0)


def build_source(spec: str, capture_port: str = "system:capture_1", *, name: str = "pistomp-tuner") -> AudioSource:
    """Parse a source spec string and return an AudioSource.

    Specs: 'jack', 'tone:<hz>', 'sweep:<hz>' (ToneSweepSource centered at hz, default 440).
    """
    if spec == "jack":
        return JackSource(capture_port, name=name)
    if spec.startswith("tone:"):
        hz = float(spec[5:])
        return ToneSource(hz)
    if spec.startswith("sweep"):
        _, _, rest = spec.partition(":")
        center = float(rest) if rest else 440.0
        return ToneSweepSource(center_hz=center)
    raise ValueError(f"Unknown tuner source spec: {spec!r}")
