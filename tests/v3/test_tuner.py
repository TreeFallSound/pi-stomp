"""Tuner panel — snapshot and integration tests with synthetic audio source."""

import time
from typing import Any, Callable

import numpy as np
import numpy.typing as npt
import pytest

from pistomp.tuner.source import ToneSource


class SilenceSource:
    """AudioSource that emits no samples — used to render the 'no signal' panel state."""

    def __init__(self, sample_rate: int = 48000) -> None:
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def start(self, on_samples: Callable[[npt.NDArray[np.float32]], Any]) -> None:
        pass

    def stop(self) -> None:
        pass


@pytest.fixture
def v3_tuner(v3_system):
    handler = v3_system.handler
    handler.set_tuner_source_factory(lambda port, *, name: ToneSource(440.0))
    return v3_system


@pytest.fixture
def v3_tuner_silence(v3_system):
    handler = v3_system.handler
    handler.set_tuner_source_factory(lambda port, *, name: SilenceSource())
    return v3_system


class TestTunerPanelSnapshot:
    def test_tuner_panel_with_signal(self, v3_tuner, snapshot):
        handler = v3_tuner.handler
        handler.toggle_tuner_enable()
        time.sleep(2.0)
        for _ in range(5):
            handler._tuner_panel.tick()
            handler.poll_lcd_updates()
        snapshot("signal")

    def test_tuner_panel_no_signal(self, v3_tuner_silence, snapshot):
        handler = v3_tuner_silence.handler
        handler.toggle_tuner_enable()
        time.sleep(0.2)  # give the DSP loop a few ticks to confirm no reading
        for _ in range(3):
            handler._tuner_panel.tick()
            handler.poll_lcd_updates()
        snapshot("no_signal")


class TestTunerDismiss:
    def test_tuner_dismiss_via_close_button(self, v3_tuner, get_urls):
        handler = v3_tuner.handler
        handler.toggle_tuner_enable()
        assert handler._tuner_engine is not None
        handler._tuner_panel._btn_close.action()
        assert handler._tuner_engine is None
        assert handler._tuner_panel is None

    def test_tuner_dismiss_restores_mute(self, v3_tuner):
        handler = v3_tuner.handler
        handler._tuner_muted = True
        handler.toggle_tuner_enable()
        handler.toggle_tuner_enable()
        handler.audiocard.set_output_muted.assert_called_with(False)
        assert handler._tuner_muted is False

    def test_preset_change_leaves_tuner_up(self, v3_tuner, get_urls):
        handler = v3_tuner.handler
        handler.toggle_tuner_enable()
        assert handler._tuner_engine is not None
        engine = handler._tuner_engine
        handler.preset_change(1)
        assert handler._tuner_engine is engine  # tuner stays up; user dismisses via footswitch longpress
        assert any("snapshot/load" in u for u in get_urls(v3_tuner.mock_get))

    def test_mute_toggle_persists(self, v3_tuner):
        handler = v3_tuner.handler
        handler.toggle_tuner_enable()
        handler._toggle_tuner_mute()
        handler.settings.set_setting.assert_called()
        handler.toggle_tuner_enable()

    def test_input_toggle_uses_unique_jack_client_name(self, v3_system):
        """The whole point of the per-port `name=` plumbing in _tuner_factory:
        when switching capture ports, the new JackSource must get a different
        client name so the new engine can connect before the old is torn down
        without a name collision."""
        handler = v3_system.handler
        names: list[str] = []

        def factory(port, *, name="pistomp-tuner"):
            names.append(name)
            return SilenceSource()

        handler.set_tuner_source_factory(factory)
        handler.toggle_tuner_enable()
        old_engine = handler._tuner_engine
        handler._toggle_tuner_input()
        assert handler._tuner_engine is not old_engine
        assert len(names) == 2
        assert names[0] != names[1]

    def test_cleanup_stops_tuner(self, v3_tuner_silence):
        handler = v3_tuner_silence.handler
        handler._tuner_muted = True
        handler.toggle_tuner_enable()
        engine = handler._tuner_engine
        assert engine is not None
        handler.cleanup()
        assert handler._tuner_engine is None
        assert handler._tuner_panel is None
        handler.audiocard.set_output_muted.assert_any_call(False)


