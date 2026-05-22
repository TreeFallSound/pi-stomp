# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""
Async WebSocket bridge for parameter setting.

Provides a thread-safe bridge between the synchronous main loop and
async WebSocket communication with mod-ui.
"""

import asyncio
import logging
import queue
import sys
import threading
from typing import Optional

try:
    import websockets
except ImportError:
    logging.error("websockets library not installed. Run: pip install websockets")
    raise


class WebSocketWorker:
    """
    Async worker that owns the WebSocket connection lifecycle.

    Runs inside a dedicated background thread's event loop. Reads from a
    shared queue and forwards messages to mod-ui, with exponential-backoff
    reconnection and backpressure monitoring.
    """

    def __init__(self, ws_url: str, backpressure_threshold: int, command_queue: queue.Queue, received_queue: queue.Queue):
        self.ws_url = ws_url
        self.backpressure_threshold = backpressure_threshold
        self.command_queue = command_queue
        self.received_queue = received_queue
        self.running = False
        self.ws = None

        # Metrics
        self.messages_sent = 0
        self.messages_received = 0
        self.backpressure_events = 0
        self.backpressure_active = False

    def run(self):
        """Entry point for the background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_worker())
        except Exception as e:
            logging.error(f"WebSocket worker crashed: {e}", exc_info=True)
        finally:
            loop.close()

    async def _async_worker(self):
        """Connects and drives the message loop, with exponential-backoff reconnection."""
        retry_delay = 1.0

        while self.running:
            try:
                async with websockets.connect(
                    self.ws_url,
                    max_queue=32,
                    write_limit=65536,
                    ping_interval=None,
                    close_timeout=1.0,
                ) as ws:
                    self.ws = ws
                    logging.info(f"WebSocket connected to {self.ws_url}")
                    retry_delay = 1.0  # Reset on successful connect

                    # Flush stale messages from before the disconnect.
                    # After a reconnect, mod-ui sends a fresh loading_end which re-syncs state.
                    flushed = 0
                    while not self.command_queue.empty():
                        try:
                            self.command_queue.get_nowait()
                            flushed += 1
                        except queue.Empty:
                            break
                    if flushed:
                        logging.info(f"Flushed {flushed} stale messages from queue after reconnect")

                    await asyncio.gather(self._process_queue(ws), self._receive_messages(ws))

            except (websockets.exceptions.WebSocketException, OSError, ConnectionRefusedError) as e:
                logging.error(f"WebSocket connection error: {e}")
                self.ws = None
                if self.running:
                    logging.info(f"Reconnecting in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30.0)
            except Exception as e:
                logging.error(f"Unexpected WebSocket error: {e}", exc_info=True)
                self.ws = None
                await asyncio.sleep(retry_delay)

    async def _process_queue(self, ws):
        """Drain the queue and send messages; exits on connection close."""
        while self.running:
            msg = None
            try:
                try:
                    msg = self.command_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.001)  # 1ms yield
                    continue

                await ws.send(msg)
                self.messages_sent += 1
                self.command_queue.task_done()

                buffer_size = self._get_write_buffer_size(ws)

                if buffer_size > self.backpressure_threshold and not self.backpressure_active:
                    self.backpressure_active = True
                    self.backpressure_events += 1
                    logging.warning(
                        f"WebSocket backpressure START: {buffer_size} bytes buffered, "
                        f"queue={self.command_queue.qsize()}, threshold={self.backpressure_threshold}"
                    )
                elif buffer_size <= self.backpressure_threshold and self.backpressure_active:
                    self.backpressure_active = False
                    logging.info(
                        f"WebSocket backpressure CLEAR: {buffer_size} bytes buffered, "
                        f"queue={self.command_queue.qsize()}"
                    )

                if self.messages_sent % 1000 == 0:
                    logging.debug(
                        f"WebSocket stats: sent={self.messages_sent}, "
                        f"buffer={buffer_size}, queue={self.command_queue.qsize()}"
                    )

            except websockets.exceptions.ConnectionClosed as e:
                logging.warning(f"WebSocket connection closed: {e}")
                break
            except Exception as e:
                if msg:
                    logging.error(f"Error sending message: {msg[:50]}...'", exc_info=True)
                else:
                    logging.error(f"Error in WebSocket worker: {e}", exc_info=True)

    async def _receive_messages(self, ws):
        """Receive messages from WebSocket and queue them for the main thread."""
        try:
            async for message in ws:
                if message == "ping":
                    await ws.send("pong")
                    continue
                elif message.startswith("data_ready "):
                    await ws.send(message)
                    continue
                self.received_queue.put(message)
                self.messages_received += 1
                logging.debug(f"Received message from server: {message[:100]}")
        except websockets.exceptions.ConnectionClosed:
            logging.debug("WebSocket receive loop closed")
        except Exception as e:
            logging.error(f"Error receiving message: {e}")

    def _get_write_buffer_size(self, ws) -> int:
        """Return bytes waiting in the TCP write buffer, or 0 if unavailable."""
        try:
            return ws.transport.get_write_buffer_size()
        except Exception:
            return 0


class AsyncWebSocketBridge:
    """
    Thread-safe bridge between the synchronous main loop and a WebSocketWorker.

    Queues messages from the main thread; the worker drains them asynchronously.
    """

    def __init__(self, ws_url: str = "ws://localhost:80/websocket", backpressure_threshold: int = 8192):
        self.ws_url = ws_url
        self.command_queue: queue.Queue = queue.Queue()  # Unbounded - never drop blend mode messages
        self.received_queue: queue.Queue = queue.Queue()
        self._worker = WebSocketWorker(ws_url, backpressure_threshold, self.command_queue, self.received_queue)
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start background async worker thread."""
        if self._worker.running:
            logging.warning("WebSocket bridge already running")
            return

        self._worker.running = True
        self._thread = threading.Thread(target=self._worker.run, daemon=True, name="WebSocketWorker")
        self._thread.start()
        logging.info(f"WebSocket worker started, connecting to {self.ws_url}")

    def stop(self):
        """Stop background worker and cleanup."""
        if not self._worker.running:
            return

        self._worker.running = False
        if self._thread and not sys.is_finalizing():
            self._thread.join(timeout=2.0)
        logging.info(f"WebSocket worker stopped (sent={self._worker.messages_sent})")

    def send_parameter(self, instance_id: str, symbol: str, value: float) -> bool:
        """
        Queue a parameter update (non-blocking).

        Args:
            instance_id: Plugin instance ID (e.g., "xfade", "/CollisionDrive")
            symbol: Parameter symbol (e.g., "DRIVE")
            value: Parameter value

        Returns:
            True if queued successfully
        """
        instance_id = instance_id.lstrip("/")
        msg = f"param_set /graph/{instance_id}/{symbol} {value}"
        self.command_queue.put_nowait(msg)
        return True

    def get_received_messages(self) -> list:
        """Drain all pending inbound messages (non-blocking). Called from main thread."""
        messages = []
        try:
            while True:
                messages.append(self.received_queue.get_nowait())
        except queue.Empty:
            pass
        return messages

    def get_queue_depth(self) -> int:
        return self.command_queue.qsize()

    def get_stats(self) -> dict:
        stats = {
            "queue_depth": self.get_queue_depth(),
            "messages_sent": self._worker.messages_sent,
            "messages_received": self._worker.messages_received,
            "backpressure_events": self._worker.backpressure_events,
            "backpressure_active": self._worker.backpressure_active,
        }
        if self._worker.ws:
            stats["write_buffer_bytes"] = self._worker._get_write_buffer_size(self._worker.ws)
        return stats

    def clear_queue(self) -> int:
        """Clear all pending messages from the queue, returning num cleared."""
        cleared_count = 0
        try:
            while True:
                self.command_queue.get_nowait()
                self.command_queue.task_done()
                cleared_count += 1
        except queue.Empty:
            pass

        if cleared_count > 0:
            logging.debug(f"Cleared {cleared_count} pending messages from WebSocket queue")

        return cleared_count
