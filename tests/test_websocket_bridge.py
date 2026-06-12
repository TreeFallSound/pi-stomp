"""Unit tests for AsyncWebSocketBridge and WebSocketWorker."""

import asyncio
import queue

from modalapi.websocket_bridge import AsyncWebSocketBridge, WebSocketWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bridge() -> AsyncWebSocketBridge:
    """Construct a bridge without starting the background thread."""
    return AsyncWebSocketBridge(ws_url="ws://localhost/test", backpressure_threshold=8192)


def _make_worker() -> WebSocketWorker:
    """Construct a worker with fresh queues, not running."""
    return WebSocketWorker(
        ws_url="ws://localhost/test",
        backpressure_threshold=8192,
        command_queue=queue.Queue(),
        received_queue=queue.Queue(),
    )


def _drain(bridge: AsyncWebSocketBridge) -> list[str]:
    out = []
    while not bridge.command_queue.empty():
        out.append(bridge.command_queue.get_nowait())
    return out


class _FakeWs:
    """Minimal WebSocket stand-in for _receive_messages tests."""

    def __init__(self, messages: list[str], *, close_after: bool = True):
        self._messages = messages
        self._sent: list[str] = []
        self._close_after = close_after

    async def send(self, msg: str) -> None:
        self._sent.append(msg)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            if self._close_after:
                import websockets.exceptions

                raise websockets.exceptions.ConnectionClosed(None, None)
            raise StopAsyncIteration
        return self._messages.pop(0)


# ---------------------------------------------------------------------------
# Tier 1: sync queue methods
# ---------------------------------------------------------------------------


def test_send_parameter_formats_message():
    bridge = _make_bridge()
    bridge.send_parameter("CollisionDrive", "DRIVE", 0.5)
    assert bridge.command_queue.get_nowait() == "param_set /graph/CollisionDrive/DRIVE 0.5"


def test_clear_queue_returns_count_and_empties():
    bridge = _make_bridge()
    bridge.send_parameter("a", "x", 0.1)
    bridge.send_parameter("b", "y", 0.2)
    bridge.send_parameter("c", "z", 0.3)
    assert bridge.clear_queue() == 3
    assert bridge.command_queue.empty()


def test_clear_queue_on_empty_returns_zero():
    bridge = _make_bridge()
    assert bridge.clear_queue() == 0


def test_get_queue_depth_reflects_sends():
    bridge = _make_bridge()
    assert bridge.get_queue_depth() == 0
    bridge.send_parameter("a", "x", 0.0)
    bridge.send_parameter("b", "y", 0.0)
    assert bridge.get_queue_depth() == 2


def test_get_received_messages_drains_queue():
    bridge = _make_bridge()
    bridge.received_queue.put("loading_end 0")
    bridge.received_queue.put("pedal_snapshot 1 Lead")
    msgs = bridge.get_received_messages()
    assert msgs == ["loading_end 0", "pedal_snapshot 1 Lead"]
    assert bridge.get_received_messages() == []


# ---------------------------------------------------------------------------
# Tier 2: _receive_messages async path
# ---------------------------------------------------------------------------


def test_receive_normal_messages_go_to_queue():
    worker = _make_worker()
    worker.running = True
    ws = _FakeWs(["loading_end 0", "pedal_snapshot 1 Lead"])

    asyncio.run(worker._receive_messages(ws))

    msgs = []
    while not worker.received_queue.empty():
        msgs.append(worker.received_queue.get_nowait())

    assert msgs == ["loading_end 0", "pedal_snapshot 1 Lead"]
    assert worker.messages_received == 2


def test_receive_ping_sends_pong_and_does_not_queue():
    worker = _make_worker()
    worker.running = True
    ws = _FakeWs(["ping"])

    asyncio.run(worker._receive_messages(ws))

    assert ws._sent == ["pong"]
    assert worker.received_queue.empty()
    assert worker.messages_received == 0


def test_receive_data_ready_echoes_and_does_not_queue():
    worker = _make_worker()
    worker.running = True
    ws = _FakeWs(["data_ready sometoken"])

    asyncio.run(worker._receive_messages(ws))

    assert ws._sent == ["data_ready sometoken"]
    assert worker.received_queue.empty()
    assert worker.messages_received == 0


def test_receive_output_set_is_dropped():
    worker = _make_worker()
    worker.running = True
    ws = _FakeWs(["output_set /graph/Delay/meter 0.5", "output_set /graph/Amp/out 0.9"])

    asyncio.run(worker._receive_messages(ws))

    assert worker.received_queue.empty()
    assert worker.messages_received == 0
    assert ws._sent == []


def test_receive_mixed_messages_routes_correctly():
    worker = _make_worker()
    worker.running = True
    ws = _FakeWs(["ping", "loading_end 0", "output_set /graph/Amp/out 0.9", "data_ready x", "pedal_snapshot 2 Fuzz"])

    asyncio.run(worker._receive_messages(ws))

    msgs = []
    while not worker.received_queue.empty():
        msgs.append(worker.received_queue.get_nowait())

    assert msgs == ["loading_end 0", "pedal_snapshot 2 Fuzz"]
    assert ws._sent == ["pong", "data_ready x"]
    assert worker.messages_received == 2


def test_receive_connection_closed_exits_cleanly():
    worker = _make_worker()
    worker.running = True
    # ConnectionClosed raised immediately (empty list + close_after=True)
    ws = _FakeWs([])

    # Should not raise
    asyncio.run(worker._receive_messages(ws))

    assert worker.received_queue.empty()


# ---------------------------------------------------------------------------
# Tier 3: wire format — pins the exact strings produced by send_*
# ---------------------------------------------------------------------------


def test_send_bpm_wire_format():
    bridge = _make_bridge()
    bridge.send_bpm(120)
    assert _drain(bridge) == ["transport-bpm 120"]


def test_send_bpm_float():
    bridge = _make_bridge()
    bridge.send_bpm(123.5)
    assert _drain(bridge) == ["transport-bpm 123.5"]


def test_send_parameter_wire_format():
    bridge = _make_bridge()
    bridge.send_parameter("fuzz", ":bypass", 1.0)
    assert _drain(bridge) == ["param_set /graph/fuzz/:bypass 1.0"]


def test_send_parameter_float_value():
    bridge = _make_bridge()
    bridge.send_parameter("delay", "gain", 0.75)
    assert _drain(bridge) == ["param_set /graph/delay/gain 0.75"]


def test_send_parameter_small_value_uses_repr_not_e_notation():
    # Floats like 0.001 should serialize as "0.001", not "1e-3". str(float) is OK here;
    # if MOD-UI ever rejects scientific notation, this test will catch a regression.
    bridge = _make_bridge()
    bridge.send_parameter("delay", "gain", 0.001)
    sent = _drain(bridge)
    assert sent == ["param_set /graph/delay/gain 0.001"], sent


def test_multiple_sends_preserve_order():
    bridge = _make_bridge()
    bridge.send_parameter("a", "x", 1.0)
    bridge.send_bpm(60)
    bridge.send_parameter("b", "y", 2.0)
    assert _drain(bridge) == [
        "param_set /graph/a/x 1.0",
        "transport-bpm 60",
        "param_set /graph/b/y 2.0",
    ]
