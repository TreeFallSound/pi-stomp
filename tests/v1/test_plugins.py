"""Basic v1/v2 (mod.py) coverage for source-of-truth bypass.

Drives Mod.toggle_plugin_bypass directly with a hand-wired handler (no hardware,
no ws thread) to confirm the non-footswitch branch emits only and lets the
inbound echo own state + LCD — matching the v3 (modhandler) behavior."""

from unittest.mock import MagicMock

from modalapi.mod import Mod
from tests.conftest import FakeWebSocketBridge


def _make_handler(selected_plugin):
    handler = Mod.__new__(Mod)  # skip heavy __init__ (audio card, ws thread, ...)
    handler.wifi_manager = None  # __del__ touches it
    handler.ws_bridge = FakeWebSocketBridge()
    handler.lcd = MagicMock()
    handler.get_selected_instance = lambda: selected_plugin
    return handler


def test_v1_toggle_non_footswitch_plugin_emits_only(make_plugin):
    plugin = make_plugin("fuzz", bypassed=False, has_footswitch=False)
    handler = _make_handler(plugin)

    handler.toggle_plugin_bypass()

    # Emits the intended value; state stays put until the echo arrives.
    assert handler.ws_bridge.sent_values_for("fuzz", ":bypass") == [1.0]
    assert not plugin.is_bypassed()
