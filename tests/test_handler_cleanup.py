"""cleanup() closes external MIDI exactly once. The handler no longer has
a __del__ — Python's GC is non-deterministic, and the previous __del__
that deleted self.wifi_manager caused spurious AttributeError on
interpreter teardown after cleanup() had run."""

from unittest.mock import MagicMock

from modalapi.modhandler import Modhandler


class TestModhandlerCleanup:
    def test_cleanup_closes_external_midi(self):
        h = object.__new__(Modhandler)
        h._tuner_muted = False
        h._lcd = None
        h._hardware = None
        h.external_midi = MagicMock()
        h.ethernet_manager = MagicMock()
        h.ws_bridge = MagicMock()
        h.cleanup()
        h.external_midi.close.assert_called_once()
