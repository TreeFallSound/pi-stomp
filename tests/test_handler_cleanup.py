"""External MIDI must be closed exactly once, in cleanup() — not also in __del__.

Closing in both leads to a double-close: cleanup() runs at shutdown, then __del__
fires again at GC/interpreter teardown on the same (already-closed) manager.
"""

from unittest.mock import MagicMock

from modalapi.mod import Mod
from modalapi.modhandler import Modhandler


class TestModCleanup:
    def test_del_does_not_close_external_midi(self):
        h = object.__new__(Mod)
        h.wifi_manager = None
        h.external_midi = MagicMock()
        h.ws_bridge = None
        h.__del__()
        h.external_midi.close.assert_not_called()

    def test_cleanup_closes_external_midi(self):
        h = object.__new__(Mod)
        h.wifi_manager = None
        h.lcd = None
        h.external_midi = MagicMock()
        h.ws_bridge = None
        h.cleanup()
        h.external_midi.close.assert_called_once()


class TestModhandlerCleanup:
    def test_del_does_not_close_external_midi(self):
        h = object.__new__(Modhandler)
        h.wifi_manager = None
        h.external_midi = MagicMock()
        h.__del__()
        h.external_midi.close.assert_not_called()

    def test_cleanup_closes_external_midi(self):
        h = object.__new__(Modhandler)
        h.wifi_manager = None
        h._tuner_engine = None
        h._lcd = None
        h._hardware = None
        h.external_midi = MagicMock()
        h.ws_bridge = None
        h.cleanup()
        h.external_midi.close.assert_called_once()
