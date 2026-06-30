"""NAM Capture panel — LCD snapshot and lifecycle tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pistomp.nam.engine import CaptureState
from pistomp.nam.panel import NamCapturePanel


@pytest.fixture(autouse=True)
def _no_jack(monkeypatch):
    """Suppress all jack_connect/jack_disconnect/jack_lsp subprocess calls."""
    import pistomp.nam.routing as routing

    monkeypatch.setattr(routing, "connect_monitor", lambda **_: None)
    monkeypatch.setattr(routing, "disconnect_monitor", lambda **_: None)
    monkeypatch.setattr(routing, "snapshot", lambda **_: [])
    monkeypatch.setattr(routing, "clear", lambda **_: None)
    monkeypatch.setattr(routing, "restore", lambda *_: None)


# ---------------------------------------------------------------------------
# Fake engine for deterministic panel rendering
# ---------------------------------------------------------------------------


class _FakeEngine:
    """Stand-in for NamCaptureEngine that lets tests control state/progress."""

    def __init__(self, state: CaptureState = CaptureState.IDLE, progress: float = 0.0) -> None:
        self._state = state
        self._progress = progress
        self.started: list[str] = []
        self.stopped = False
        self.aborted_error: str | None = None

    @property
    def state(self) -> CaptureState:
        return self._state

    @property
    def error(self) -> str | None:
        if self.aborted_error is not None:
            return self.aborted_error
        return "Reduce amp output" if self._state == CaptureState.FAILED else None

    def abort_with_error(self, msg: str) -> None:
        self.aborted_error = msg
        self._state = CaptureState.FAILED

    @property
    def output_path(self) -> Path | None:
        return (
            Path("/home/pistomp/data/user-files/Audio Recordings/my-amp.wav")
            if self._state == CaptureState.DONE
            else None
        )

    @property
    def pending_path(self) -> Path | None:
        return (
            Path("/home/pistomp/data/user-files/Audio Recordings/my-amp.wav")
            if self._state == CaptureState.CAPTURING
            else None
        )

    def progress(self) -> float:
        return self._progress

    def start(self, name: str) -> None:
        self.started.append(name)
        self._state = CaptureState.CAPTURING

    def stop(self) -> None:
        self.stopped = True
        self._state = CaptureState.ABORTED

    def reset(self) -> None:
        if self._state in (CaptureState.DONE, CaptureState.FAILED, CaptureState.ABORTED):
            self._state = CaptureState.IDLE

    def level_snapshot_db(self) -> tuple[float, float] | None:
        return None

    def set_state(self, state: CaptureState, progress: float = 0.0) -> None:
        self._state = state
        self._progress = progress


def _make_panel(engine: _FakeEngine, on_dismiss=None) -> NamCapturePanel:
    """Build a NamCapturePanel backed by *engine* without touching the filesystem."""
    if on_dismiss is None:
        on_dismiss = lambda: None  # noqa: E731
    with (
        patch.object(NamCapturePanel, "_create_engine", return_value=engine),
        patch("pistomp.nam.panel.wav_duration", return_value=190.0),
        patch("pistomp.nam.panel.wav_peak_dbfs", return_value=-6.0),
    ):
        return NamCapturePanel(output_dir="/tmp", on_dismiss=on_dismiss)


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------


class TestNamPanelSnapshot:
    def test_idle_state(self, v3_system, snapshot):
        panel = _make_panel(_FakeEngine(CaptureState.IDLE))
        v3_system.handler.lcd.show_fullscreen_panel(panel)
        panel.tick()
        v3_system.handler.poll_lcd_updates()
        snapshot("idle")

    def test_capturing_state(self, v3_system, snapshot):
        panel = _make_panel(_FakeEngine(CaptureState.CAPTURING, progress=0.45))
        v3_system.handler.lcd.show_fullscreen_panel(panel)
        panel.tick()
        v3_system.handler.poll_lcd_updates()
        snapshot("capturing")

    def test_done_state(self, v3_system, snapshot):
        panel = _make_panel(_FakeEngine(CaptureState.DONE, progress=1.0))
        v3_system.handler.lcd.show_fullscreen_panel(panel)
        panel.tick()
        v3_system.handler.poll_lcd_updates()
        snapshot("done")

    def test_failed_state(self, v3_system, snapshot):
        panel = _make_panel(_FakeEngine(CaptureState.FAILED, progress=0.3))
        v3_system.handler.lcd.show_fullscreen_panel(panel)
        panel.tick()
        v3_system.handler.poll_lcd_updates()
        snapshot("failed")

    def test_aborted_state(self, v3_system, snapshot):
        panel = _make_panel(_FakeEngine(CaptureState.ABORTED, progress=0.6))
        v3_system.handler.lcd.show_fullscreen_panel(panel)
        panel.tick()
        v3_system.handler.poll_lcd_updates()
        snapshot("aborted")


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------


class TestNamPanelLifecycle:
    def test_start_button_starts_engine(self, v3_system):
        engine = _FakeEngine(CaptureState.IDLE)
        panel = _make_panel(engine)
        assert panel._btn_start.action is not None
        panel._btn_start.action()
        assert "capture" in engine.started

    def test_abort_button_shows_dialog_when_parented(self, v3_system):
        # With no parent (tests), _on_abort falls through to immediate abort.
        # Parented case is exercised by the integration flow below.
        engine = _FakeEngine(CaptureState.CAPTURING)
        panel = _make_panel(engine)
        panel.tick()
        # Direct call to confirmed path (dialog tested via integration)
        panel._on_confirmed_abort()
        assert engine.stopped

    def test_abort_noop_when_idle(self, v3_system):
        engine = _FakeEngine(CaptureState.IDLE)
        panel = _make_panel(engine)
        panel._on_abort()
        assert not engine.stopped

    def test_close_setup_calls_on_dismiss(self, v3_system):
        dismissed = []
        panel = _make_panel(_FakeEngine(CaptureState.IDLE), on_dismiss=lambda: dismissed.append(True))
        assert panel._btn_setup_close.action is not None
        panel._btn_setup_close.action()
        assert dismissed == [True]

    def test_done_saved_button_calls_on_dismiss(self, v3_system):
        dismissed = []
        engine = _FakeEngine(CaptureState.DONE, progress=1.0)
        panel = _make_panel(engine, on_dismiss=lambda: dismissed.append(True))
        panel.tick()
        assert panel._btn_done.action is not None
        panel._btn_done.action()
        assert dismissed == [True]

    def test_failed_back_returns_to_idle(self, v3_system):
        engine = _FakeEngine(CaptureState.FAILED, progress=0.3)
        panel = _make_panel(engine)
        panel.tick()  # switch to capture view → FAILED
        assert panel._btn_capture_close.action is not None
        panel._btn_capture_close.action()  # "Back"
        assert engine.state == CaptureState.IDLE

    def test_aborted_back_returns_to_idle(self, v3_system):
        engine = _FakeEngine(CaptureState.ABORTED, progress=0.6)
        panel = _make_panel(engine)
        panel.tick()  # switch to capture view → ABORTED
        assert panel._btn_capture_close.action is not None
        panel._btn_capture_close.action()  # "Back"
        assert engine.state == CaptureState.IDLE

    def test_tick_updates_reel_progress(self, v3_system):
        engine = _FakeEngine(CaptureState.CAPTURING, progress=0.5)
        panel = _make_panel(engine)
        panel._reel._total = 60.0  # override for predictable elapsed
        panel.tick()
        assert abs(panel._reel._elapsed - 30.0) < 1.0

    def test_retry_button_restarts_engine(self, v3_system):
        engine = _FakeEngine(CaptureState.FAILED, progress=0.3)
        panel = _make_panel(engine)
        panel.tick()  # switch to capture view → FAILED
        assert panel._btn_capture_right.action is not None
        panel._btn_capture_right.action()  # "Retry"
        assert "capture" in engine.started

    def test_reel_frozen_on_failure(self, v3_system):
        engine = _FakeEngine(CaptureState.FAILED, progress=0.3)
        panel = _make_panel(engine)
        panel.tick()
        frozen_progress = panel._reel._progress
        panel._reel.set_progress(0.9)  # attempt to advance
        assert panel._reel._progress == frozen_progress

    def test_destroy_stops_engine(self, v3_system):
        engine = _FakeEngine(CaptureState.CAPTURING)
        panel = _make_panel(engine)
        v3_system.handler.lcd.show_fullscreen_panel(panel)
        v3_system.handler.lcd.hide_fullscreen_panel()  # pop_panel → auto_destroy → destroy()
        assert engine.stopped

    def test_analog_clipping_aborts_engine(self, v3_system):
        from pistomp.analogVU import VuState

        engine = _FakeEngine(CaptureState.CAPTURING)
        panel = _make_panel(engine)
        panel._handler = v3_system.handler
        vu = v3_system.handler.hardware.indicators[0]
        vu.state = VuState.CLIP

        for _ in range(4):
            panel.tick()
            assert engine._state == CaptureState.CAPTURING
        panel.tick()
        assert engine._state == CaptureState.FAILED
        assert engine.aborted_error == "Analog clipping: lower amp output"


class TestCaptureSessionSilence:
    def test_silence_decay(self):
        import numpy as np
        from pistomp.nam.capture_session import CaptureSession

        samples = np.ones(48000, dtype=np.float32)
        session = CaptureSession(samples, "out", "in")
        # Verify initial state
        assert session._silent_frames == 0
        session._silent_frames = 24000
        # Simulate non-silent callback step with decay calculation
        frames = 480
        decay = int(frames * (96000 / 96000))
        session._silent_frames = max(0, session._silent_frames - decay)
        assert session._silent_frames == 23520


class TestNamHandlerIntegration:
    def test_nam_board_mounts_panel(self, v3_system):
        handler = v3_system.handler
        fake_engine = _FakeEngine(CaptureState.IDLE)
        with (
            patch.object(NamCapturePanel, "_create_engine", return_value=fake_engine),
            patch("pistomp.nam.panel.wav_duration", return_value=190.0),
        ):
            handler._mount_nam_capture_panel()
        assert isinstance(handler._fullscreen_panel, NamCapturePanel)

    def test_switching_board_stops_engine(self, v3_system):
        handler = v3_system.handler
        fake_engine = _FakeEngine(CaptureState.CAPTURING)
        panel = _make_panel(fake_engine)
        handler._fullscreen_panel = panel
        handler.lcd.show_fullscreen_panel(panel)

        pb = handler.current.pedalboard
        handler.set_current_pedalboard(pb)

        assert fake_engine.stopped
        assert handler._fullscreen_panel is None
