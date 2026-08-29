"""Unit tests for Audiocard's debounced persist.

`alsactl store` costs ~39 ms and every setter runs on the 10 ms UI thread, so
it must not run per write — but the values still have to reach asound.state.
Callers know nothing about this; they just ask for persistence.
"""

from unittest.mock import patch

import pytest

from pistomp.audiocard import Audiocard


@pytest.fixture
def card() -> Audiocard:
    c = Audiocard(cwd="/nonexistent")
    c.MASTER = "Headphone"
    return c


@pytest.fixture
def amixer():
    """Stub the mixer write so only the persist behaviour is under test."""
    with patch("subprocess.check_output", return_value=b""):
        yield


def test_setter_does_not_store_synchronously(card: Audiocard, amixer):
    with patch.object(Audiocard, "store") as store:
        card.set_volume_parameter(card.MASTER, -8.0)
        card.poll_store()  # debounce has not elapsed
    store.assert_not_called()


def test_store_runs_once_debounce_elapses(card: Audiocard, amixer):
    with patch.object(Audiocard, "store") as store:
        card.set_volume_parameter(card.MASTER, -8.0)
        with patch("time.monotonic", return_value=_later(card)):
            card.poll_store()
        store.assert_called_once()

        # Settled — no repeat store until another write requests one.
        with patch("time.monotonic", return_value=_later(card, 10)):
            card.poll_store()
        store.assert_called_once()


def test_rapid_writes_coalesce_into_one_store(card: Audiocard, amixer):
    """A twist emits many detents; they must collapse to a single store."""
    with patch.object(Audiocard, "store") as store:
        for db in range(20):
            card.set_volume_parameter(card.MASTER, float(-db))
            card.poll_store()
        store.assert_not_called()

        with patch("time.monotonic", return_value=_later(card)):
            card.poll_store()
    store.assert_called_once()


def test_transient_settings_never_persist(card: Audiocard, amixer):
    """store=False means 'must not survive a reboot' (mute), not 'deferred' —
    so it must not arm the debounce either."""
    with patch.object(Audiocard, "store") as store:
        card.set_output_muted(True)
        with patch("time.monotonic", return_value=_later(card)):
            card.poll_store()
    store.assert_not_called()


def test_flush_store_persists_pending_write(card: Audiocard, amixer):
    """Shutdown path: a pending store must not die with the loop."""
    with patch.object(Audiocard, "store") as store:
        card.set_volume_parameter(card.MASTER, -8.0)
        card.flush_store()
    store.assert_called_once()


def test_flush_store_is_a_noop_when_nothing_pending(card: Audiocard):
    with patch.object(Audiocard, "store") as store:
        card.flush_store()
    store.assert_not_called()


def _later(card: Audiocard, multiplier: float = 1) -> float:
    import time

    return time.monotonic() + card.STORE_IDLE_S * multiplier + 1.0
