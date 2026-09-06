# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""
Async WebSocket bridge for parameter setting.

Provides a thread-safe bridge between the synchronous main loop and
async WebSocket communication with mod-ui.
"""

import os
import asyncio
import logging
import queue
import sys
import threading
from typing import Optional

import websockets
import uvloop
from common.parameter import Symbol
from common.util import TEARDOWN_JOIN_S

# Service will restart after this
MAX_RECONNECT_ATTEMPTS = 4

# Protocol-level pings are responded to in-sequence with other events,
# so their round trips are a direct measure of how far behind mod-ui is
PING_INTERVAL_S = 5.0
STATS_INTERVAL_S = 60.0


class WebSocketWorker:
    """
    Async worker that owns the WebSocket connection lifecycle.

    Runs inside a dedicated background thread's event loop. Reads from a
    shared queue and forwards messages to mod-ui, with exponential-backoff
    reconnection. Owns the connection state the send path reads.
    """

    def __init__(self, ws_url: str, command_queue: queue.Queue, received_queue: queue.Queue):
        self.ws_url = ws_url
        self.command_queue = command_queue
        self.received_queue = received_queue
        self.running = False
        self.ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._wakeup: asyncio.Event = asyncio.Event()

        # Metrics
        self.messages_sent = 0
        self.messages_received = 0
        self.peak_latency = 0.0
        self.reconnects = 0

    def run(self):
        """Entry point for the background thread."""
        logging.info("Using uvloop for WebSocket bridge")

        try:
            uvloop.run(self._async_worker())
        except Exception as e:
            # uvloop.run raises if the loop was cancelled or crashed
            if self.running:
                logging.error(f"WebSocket worker crashed: {e}", exc_info=True)
            else:
                logging.debug(f"WebSocket worker stopped: {e}")

    def signal_stop(self):
        """Thread-safe: interrupt any sleeping reconnect wait or active receive loop."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._stop_event.set)
        self._loop.call_soon_threadsafe(self._wakeup.set)
        ws = self.ws
        if ws is not None:
            asyncio.run_coroutine_threadsafe(ws.close(), self._loop)

    def notify(self):
        """Thread-safe: wake the send loop after a message is enqueued."""
        loop = self._loop
        if loop is None:
            return  # worker not started; connect-time flush covers these
        try:
            loop.call_soon_threadsafe(self._wakeup.set)
        except RuntimeError:
            pass  # loop closed during shutdown

    async def _interruptible_sleep(self, delay: float) -> bool:
        """Sleep for delay seconds; returns True if stop was signaled before the delay elapsed."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            return True
        except asyncio.TimeoutError:
            return False

    async def _async_worker(self):
        """Connects and drives the message loop, with exponential-backoff reconnection."""
        self._loop = asyncio.get_event_loop()
        retry_delay = 1.0
        reconnect_attempts = 0

        while self.running:
            try:
                async with websockets.connect(
                    self.ws_url,
                    max_queue=32,
                    write_limit=65536,
                    ping_interval=PING_INTERVAL_S,
                    ping_timeout=None,  # a pedalboard load blocks mod-ui for seconds; never drop the socket for it
                    close_timeout=1.0,
                ) as ws:
                    self.ws = ws
                    self.reconnects += 1
                    logging.info(f"WebSocket connected to {self.ws_url}")
                    retry_delay = 1.0  # Reset on successful connect
                    reconnect_attempts = 0  # Reset attempts on success

                    try:
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

                        # FIRST_COMPLETED, not gather: the send loop parks on _wakeup and
                        # cannot notice a closed socket on its own. Whichever loop exits
                        # first cancels the other so we fall through to reconnect.
                        tasks = {
                            asyncio.create_task(self._process_queue(ws)),
                            asyncio.create_task(self._receive_messages(ws)),
                            asyncio.create_task(self._monitor_latency(ws)),
                            asyncio.create_task(self._report_stats()),
                        }
                        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        for task in done:
                            task.result()  # re-raise so the reconnect handler sees it
                    finally:
                        # _process_queue can return without raising, so the scope alone
                        # must clear the handle; otherwise `connected` reads a dead socket.
                        self.ws = None

            except (websockets.exceptions.WebSocketException, OSError, ConnectionRefusedError) as e:
                logging.error(f"WebSocket connection error: {e}")

                reconnect_attempts += 1
                if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                    logging.critical(
                        f"WebSocket failed to reconnect after {MAX_RECONNECT_ATTEMPTS} attempts. Restarting service..."
                    )
                    os._exit(1)

                if self.running:
                    logging.info(f"Reconnecting ({reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS}) in {retry_delay}s...")
                    if await self._interruptible_sleep(retry_delay):
                        return
                    retry_delay = min(retry_delay * 2, 30.0)
            except Exception as e:
                logging.error(f"Unexpected WebSocket error: {e}", exc_info=True)
                if await self._interruptible_sleep(retry_delay):
                    return

    async def _process_queue(self, ws):
        """Drain the queue and send messages; exits on connection close."""
        while self.running:
            msg = None
            try:
                try:
                    msg = self.command_queue.get_nowait()
                except queue.Empty:
                    # Clear before re-checking: a producer that enqueues between the
                    # failed get and the clear would otherwise have its wakeup erased.
                    self._wakeup.clear()
                    if self.command_queue.empty():
                        await self._wakeup.wait()
                    continue

                await ws.send(msg)
                self.messages_sent += 1
                self.command_queue.task_done()

            except websockets.exceptions.ConnectionClosed as e:
                logging.warning(f"WebSocket connection closed: {e}")
                break
            except Exception as e:
                if msg:
                    logging.error(f"Error sending message: {msg[:50]}...'", exc_info=True)
                else:
                    logging.error(f"Error in WebSocket worker: {e}", exc_info=True)

    async def _report_stats(self):
        """Print the period, then start a new one."""
        while self.running:
            if await self._interruptible_sleep(STATS_INTERVAL_S):
                return
            logging.info(
                f"WebSocket stats: sent={self.messages_sent}, received={self.messages_received}, "
                f"queue={self.command_queue.qsize()}, peak_latency={self.peak_latency * 1000:.0f}ms"
            )
            self.messages_sent = 0
            self.messages_received = 0
            self.peak_latency = 0.0

    async def _monitor_latency(self, ws):
        """Sample the keepalive round trip."""
        while self.running:
            if await self._interruptible_sleep(PING_INTERVAL_S):
                return
            self.peak_latency = max(self.peak_latency, ws.latency)

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
                elif message.startswith("output_set "):
                    continue  # audio-meter flood; nothing consumes it, drop before it floods the queue
                self.received_queue.put(message)
                self.messages_received += 1
                logging.debug(f"Received message from server: {message[:100]}")
        except websockets.exceptions.ConnectionClosed:
            logging.debug("WebSocket receive loop closed")
        except Exception as e:
            logging.error(f"Error receiving message: {e}")


class AsyncWebSocketBridge:
    """
    Thread-safe bridge between the synchronous main loop and a WebSocketWorker.

    Queues messages from the main thread; the worker drains them asynchronously.
    """

    def __init__(self, ws_url: str = "ws://localhost:80/websocket"):
        self.ws_url = ws_url
        self.command_queue: queue.Queue = queue.Queue()  # Unbounded - never drop blend mode messages
        self.received_queue: queue.Queue = queue.Queue()
        self._worker = WebSocketWorker(ws_url, self.command_queue, self.received_queue)
        self._thread: Optional[threading.Thread] = None

    def get_reconnects_since_last_call(self) -> int:
        count, self._worker.reconnects = self._worker.reconnects, 0
        return count

    @property
    def connected(self) -> bool:
        """True while the worker holds a live connection. The connect scope owns the
        handle, so this cannot latch."""
        return self._worker.ws is not None

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
        self._worker.signal_stop()
        if self._thread and not sys.is_finalizing():
            self._thread.join(timeout=TEARDOWN_JOIN_S)
        logging.info("WebSocket worker stopped")

    def send_bpm(self, bpm: float) -> bool:
        """Queue a BPM change. Returns False if there is no connection to send it over."""
        if not self.connected:
            return False
        self.command_queue.put_nowait(f"transport-bpm {bpm}")
        self._worker.notify()
        return True

    def send_parameter(self, instance_id: str, symbol: Symbol, value: float) -> bool:
        """Queue a parameter update. instance_id should be canonical (no leading slash).
        Returns False if there is no connection to send it over."""
        if not self.connected:
            return False
        self.command_queue.put_nowait(f"param_set /graph/{instance_id}/{symbol} {value}")
        self._worker.notify()
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
