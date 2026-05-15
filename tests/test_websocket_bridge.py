"""Unit tests for AsyncWebSocketBridge — pins the wire format produced by send_*."""

from modalapi.websocket_bridge import AsyncWebSocketBridge


def _drain(bridge: AsyncWebSocketBridge) -> list[str]:
    out = []
    while not bridge.command_queue.empty():
        out.append(bridge.command_queue.get_nowait())
    return out


def test_send_bpm_wire_format():
    bridge = AsyncWebSocketBridge()
    bridge.send_bpm(120)
    assert _drain(bridge) == ["transport-bpm 120"]


def test_send_bpm_float():
    bridge = AsyncWebSocketBridge()
    bridge.send_bpm(123.5)
    assert _drain(bridge) == ["transport-bpm 123.5"]


def test_send_parameter_wire_format():
    bridge = AsyncWebSocketBridge()
    bridge.send_parameter("fuzz", ":bypass", 1.0)
    assert _drain(bridge) == ["param_set /graph/fuzz/:bypass 1.0"]


def test_send_parameter_float_value():
    bridge = AsyncWebSocketBridge()
    bridge.send_parameter("delay", "gain", 0.75)
    assert _drain(bridge) == ["param_set /graph/delay/gain 0.75"]


def test_send_parameter_small_value_uses_repr_not_e_notation():
    # Floats like 0.001 should serialize as "0.001", not "1e-3". str(float) is OK here;
    # if MOD-UI ever rejects scientific notation, this test will catch a regression.
    bridge = AsyncWebSocketBridge()
    bridge.send_parameter("delay", "gain", 0.001)
    sent = _drain(bridge)
    assert sent == ["param_set /graph/delay/gain 0.001"], sent


def test_send_parameter_strips_leading_slash_and_warns(caplog):
    bridge = AsyncWebSocketBridge()
    with caplog.at_level("WARNING"):
        bridge.send_parameter("/fuzz", ":bypass", 1.0)
    assert _drain(bridge) == ["param_set /graph/fuzz/:bypass 1.0"]
    assert any("non-canonical" in r.message for r in caplog.records)


def test_multiple_sends_preserve_order():
    bridge = AsyncWebSocketBridge()
    bridge.send_parameter("a", "x", 1.0)
    bridge.send_bpm(60)
    bridge.send_parameter("b", "y", 2.0)
    assert _drain(bridge) == [
        "param_set /graph/a/x 1.0",
        "transport-bpm 60",
        "param_set /graph/b/y 2.0",
    ]
