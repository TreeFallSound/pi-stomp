# pyright: reportAttributeAccessIssue=false
"""Basic v1/v2 (mod.py) coverage for source-of-truth bypass.

Drives Mod.toggle_plugin_bypass directly with a hand-wired handler (no hardware,
no ws thread) to confirm the non-footswitch branch emits only and lets the
inbound echo own state + LCD — matching the v3 (modhandler) behavior."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from modalapi.mod import Mod
from tests.conftest import FakeWebSocketBridge


def _make_handler(selected_plugin):
    handler = Mod.__new__(Mod)  # skip heavy __init__ (audio card, ws thread, ...)
    handler.wifi_manager = None  # __del__ touches it
    handler.ws_bridge = FakeWebSocketBridge()
    handler.lcd = MagicMock()
    handler.get_selected_instance = lambda: selected_plugin
    handler._is_pedalboard_loading = False
    return handler


def _make_drain_handler(plugins):
    """Hand-wired handler with a current pedalboard, for inbound-drain tests."""
    handler = Mod.__new__(Mod)
    handler.wifi_manager = None
    handler.ws_bridge = FakeWebSocketBridge()
    handler.lcd = MagicMock()
    handler.current = SimpleNamespace(pedalboard=SimpleNamespace(plugins=plugins))
    handler._is_pedalboard_loading = False
    return handler


def test_v1_toggle_non_footswitch_plugin_emits_only(make_plugin):
    plugin = make_plugin("fuzz", bypassed=False, has_footswitch=False)
    handler = _make_handler(plugin)

    handler.toggle_plugin_bypass()

    # Emits the intended value; state stays put until the echo arrives.
    assert handler.ws_bridge.sent_values_for("fuzz", ":bypass") == [1.0]
    assert not plugin.is_bypassed()


def test_v1_inbound_bypass_echo_drains(make_plugin):
    """mod.py's drain owns bypass state: an inbound param_set :bypass flips it."""
    plugin = make_plugin("fuzz", bypassed=False, has_footswitch=False)
    handler = _make_drain_handler([plugin])

    handler.ws_bridge.inject("param_set /graph/fuzz :bypass 1.0")
    handler.poll_ws_messages()

    assert plugin.is_bypassed()


def test_v1_add_dump_reseeds_bypass_on_reconnect(make_plugin):
    """Connect/reconnect dump reseeds bypass via the add line (field 4)."""
    plugin = make_plugin("fuzz", bypassed=False, has_footswitch=False)
    handler = _make_drain_handler([plugin])

    handler.ws_bridge.inject("add fuzz http://uri 0.0 0.0 1 1 1")
    handler.poll_ws_messages()

    assert plugin.is_bypassed()



def test_v1_outbound_ws_suppressed_during_pedalboard_change(make_plugin):
    """While a pedalboard change is in flight, outbound param_set messages are dropped."""
    plugin = make_plugin("fuzz", bypassed=False, has_footswitch=False)
    handler = _make_handler(plugin)
    handler.current = SimpleNamespace(pedalboard=SimpleNamespace(plugins=[plugin]))
    handler._is_pedalboard_loading = True

    handler.toggle_plugin_bypass()

    # mod.py uses emit-only semantics (state unchanged until echo arrives).
    # The key assertion is that NO ws message was sent while suppressed.
    assert not plugin.is_bypassed()
    assert handler.ws_bridge.sent_values_for("fuzz", ":bypass") == []


def test_v1_loading_start_suppresses_outbound_ws():
    """Receiving loading_start from MOD-UI sets the suppression flag."""
    handler = _make_drain_handler([])
    assert not getattr(handler, "_is_pedalboard_loading", False)
    handler.ws_bridge.inject("loading_start 0")
    handler.poll_ws_messages()
    assert handler._is_pedalboard_loading is True
