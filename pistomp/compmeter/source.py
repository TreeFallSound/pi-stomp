"""Audio sources for the compressor GR meter.

A source delivers paired (input, output) sample blocks — the compressor's dry
input and processed output — to a callback. ``DualJackSource`` taps two JACK
ports; ``PairedToneSource`` synthesises a known in/out pair for headless tests.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Protocol

import numpy as np
import numpy.typing as npt

# on_samples(in_block, out_block); both float32, equal length.
SampleCallback = Callable[[npt.NDArray[np.float32], npt.NDArray[np.float32]], Any]


class PairedAudioSource(Protocol):
    @property
    def sample_rate(self) -> int: ...
    def start(self, on_samples: SampleCallback) -> None: ...
    def stop(self) -> None: ...


class DualJackSource:
    """Reads the compressor's input and output audio from two JACK ports."""

    def __init__(
        self,
        in_port: str,
        out_port: str,
        *,
        name: str = "pistomp-compmeter",
    ) -> None:
        self._in_port = in_port
        self._out_port = out_port
        self._client_name = name
        self._client = None
        self._on_samples: SampleCallback | None = None
        self._sample_rate: int = 48000  # overwritten in start()

    @property
    def sample_rate(self) -> int:
        if self._client is None:
            raise RuntimeError("sample_rate is not available until start() is called")
        return self._sample_rate

    def start(self, on_samples: SampleCallback) -> None:
        import jack  # type: ignore[import-untyped]

        self._on_samples = on_samples
        self._client = jack.Client(self._client_name, no_start_server=True)
        self._sample_rate = self._client.samplerate

        p_in = self._client.inports.register("comp_in")
        p_out = self._client.inports.register("comp_out")

        @self._client.set_process_callback
        def process(frames: int) -> None:
            cb = self._on_samples
            if cb is not None:
                cb(p_in.get_array(), p_out.get_array())  # pyright: ignore[reportAttributeAccessIssue]

        self._client.activate()
        self._client.connect(self._resolve_source(self._in_port), p_in)
        self._client.connect(self._resolve_source(self._out_port), p_out)

    def stop(self) -> None:
        if self._client is not None:
            self._on_samples = None  # silence callback before teardown (JACK deadlock guard)
            try:
                self._client.deactivate()
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _resolve_source(self, port_name: str) -> str:
        """JACK connections only run output→input. ``port_name`` (e.g. a plugin's
        own audio-in port) may itself be an input, so tap whatever feeds it instead.
        """
        assert self._client is not None
        port = self._client.get_port_by_name(port_name)
        if port.is_input:
            # Not our own port, so OwnPort.connections isn't available —
            # get_all_connections works for any port, foreign or not.
            upstream = self._client.get_all_connections(port)
            if upstream:
                return upstream[0].name
        return port_name


class PairedToneSource:
    """Synthesises an in/out pair: a sine input and an attenuated output.

    ``out_gain_db`` is the fixed gain the fake "compressor" applies, so tests can
    assert the engine recovers a known gain reduction.
    """

    BLOCK_SIZE = 256

    def __init__(
        self,
        freq_hz: float = 220.0,
        in_amp: float = 0.5,
        out_gain_db: float = -6.0,
        sample_rate: int = 48000,
    ) -> None:
        self._freq = freq_hz
        self._in_amp = in_amp
        self._out_lin = 10.0 ** (out_gain_db / 20.0)
        self._sample_rate = sample_rate
        self._thread: threading.Thread | None = None
        self._running = False
        self._on_samples: SampleCallback | None = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def start(self, on_samples: SampleCallback) -> None:
        self._on_samples = on_samples
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="compmeter-tone")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        phase = 0.0
        step = 2.0 * np.pi * self._freq / self._sample_rate
        block_dur = self.BLOCK_SIZE / self._sample_rate
        while self._running:
            t0 = time.monotonic()
            idx = np.arange(self.BLOCK_SIZE, dtype=np.float32)
            in_block = (self._in_amp * np.sin(phase + step * idx)).astype(np.float32)
            phase += step * self.BLOCK_SIZE
            out_block = (in_block * self._out_lin).astype(np.float32)
            if self._on_samples is not None:
                self._on_samples(in_block, out_block)
            sleep = block_dur - (time.monotonic() - t0)
            if sleep > 0:
                time.sleep(sleep)


def build_source(
    spec: str,
    in_port: str,
    out_port: str,
    *,
    name: str = "pistomp-compmeter",
) -> PairedAudioSource:
    """Parse a source spec. ``jack`` taps the ports; ``tone[:gain_db]`` synthesises."""
    if spec == "jack":
        return DualJackSource(in_port, out_port, name=name)
    if spec.startswith("tone"):
        _, _, rest = spec.partition(":")
        gain_db = float(rest) if rest else -6.0
        return PairedToneSource(out_gain_db=gain_db)
    raise ValueError(f"Unknown compmeter source spec: {spec!r}")
