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
import threading
from typing import Optional

try:
    import websockets
except ImportError:
    logging.error("websockets library not installed. Run: pip install websockets")
    raise

def should_log_message(message: str) -> bool:
    """Filter out high-frequency messages to reduce log spam."""
    if message == "ping":
        return False
    return not message.startswith(('output_set ', 'stats ', 'sys_stats '))


class AsyncWebSocketBridge:
    """
    Bridge between sync main loop and async WebSocket.

    Queues messages from main thread, sends via async worker in background.
    Monitors WebSocket write buffer for backpressure detection (logging only,
    no functional changes to timing).
    """

    def __init__(self, ws_url: str = 'ws://localhost:80/websocket', max_queue_size: int = 100, backpressure_threshold: int = 8192):
        """
        Initialize WebSocket bridge.

        Args:
            ws_url: WebSocket URL to connect to
            max_queue_size: Maximum number of messages to queue (backpressure threshold)
            backpressure_threshold: TCP write buffer size (bytes) to trigger backpressure warning (default: 8KB)
        """
        self.ws_url = ws_url
        self.backpressure_threshold = backpressure_threshold
        self.command_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self.received_queue: queue.Queue = queue.Queue()  # Thread-safe queue for incoming messages
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False

        # Metrics
        self.messages_sent = 0
        self.messages_dropped = 0
        self.messages_received = 0
        self.backpressure_events = 0
        self.backpressure_active = False  # Track if we're currently in backpressure state

    def start(self):
        """Start background async worker thread."""
        if self.running:
            logging.warning("WebSocket bridge already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="WebSocketWorker")
        self.thread.start()
        logging.info(f"WebSocket worker started, connecting to {self.ws_url}")

    def stop(self):
        """Stop background worker and cleanup."""
        if not self.running:
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logging.info(f"WebSocket worker stopped (sent={self.messages_sent}, dropped={self.messages_dropped})")

    def send_parameter(self, instance_id: str, symbol: str, value: float) -> bool:
        """
        Send parameter update (non-blocking, called from main thread).

        Args:
            instance_id: Plugin instance ID (e.g., "xfade", "/CollisionDrive")
            symbol: Parameter symbol (e.g., "DRIVE")
            value: Parameter value

        Returns:
            True if queued successfully, False if queue full (backpressure)
        """
        # Strip leading slash if present (instance_id may be "/StompBox_fuzz" or "StompBox_fuzz")
        instance_id = instance_id.lstrip('/')
        msg = f"param_set /graph/{instance_id}/{symbol} {value}"

        try:
            # Non-blocking put - fails immediately if queue full
            self.command_queue.put_nowait(msg)
            return True
        except queue.Full:
            # Queue full = backpressure!
            self.messages_dropped += 1
            if self.messages_dropped % 10 == 1:  # Log every 10th drop to avoid spam
                logging.warning(
                    f"WebSocket queue full ({self.command_queue.qsize()})! "
                    f"Dropped {self.messages_dropped} messages total"
                )
            return False

    def get_queue_depth(self) -> int:
        """Get current queue depth (for monitoring)."""
        return self.command_queue.qsize()

    def get_stats(self) -> dict:
        """Get performance statistics."""
        stats = {
            'queue_depth': self.get_queue_depth(),
            'messages_sent': self.messages_sent,
            'messages_dropped': self.messages_dropped,
            'backpressure_events': self.backpressure_events,
            'backpressure_active': self.backpressure_active,
        }

        # Add write buffer size if available
        if self.ws:
            stats['write_buffer_bytes'] = self._get_write_buffer_size(self.ws)

        return stats

    def get_received_messages(self) -> list:
        """
        Get all pending received messages from server (non-blocking).

        Called from main thread to process server messages.
        Returns list of message strings.
        """
        messages = []
        try:
            while True:
                messages.append(self.received_queue.get_nowait())
        except queue.Empty:
            pass
        return messages

    def clear_queue(self) -> int:
        """
        Clear all pending messages from the queue.

        Useful when switching contexts (e.g., pedalboard changes) to prevent
        stale parameter updates from being sent.

        Returns:
            Number of messages that were cleared
        """
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

    # --- Background thread methods ---

    def _run_loop(self):
        """Background thread - runs asyncio event loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._async_worker())
        except Exception as e:
            logging.error(f"WebSocket worker crashed: {e}", exc_info=True)
        finally:
            self.loop.close()

    async def _async_worker(self):
        """Async worker - connects and processes queue."""
        retry_delay = 1.0

        while self.running:
            try:
                # Connect to WebSocket
                async with websockets.connect(
                    self.ws_url,
                    max_queue=32,       # Allow 32 messages queued in websockets lib
                    write_limit=65536,  # 64 KiB write buffer
                    ping_interval=None, # Disable automatic pings (we'll use manual ping for backpressure)
                    close_timeout=1.0,  # Quick close on shutdown
                ) as ws:
                    self.ws = ws
                    logging.info(f"WebSocket connected to {self.ws_url}")
                    retry_delay = 1.0  # Reset retry delay on successful connect

                    # Run send and receive tasks concurrently
                    await asyncio.gather(
                        self._send_messages(ws),
                        self._receive_messages(ws)
                    )

            except (websockets.exceptions.WebSocketException, OSError, ConnectionRefusedError) as e:
                logging.error(f"WebSocket connection error: {e}")
                self.ws = None
                if self.running:
                    logging.info(f"Reconnecting in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30.0)  # Exponential backoff, max 30s
            except Exception as e:
                logging.error(f"Unexpected WebSocket error: {e}", exc_info=True)
                self.ws = None
                await asyncio.sleep(retry_delay)

    async def _send_messages(self, ws):
        """Send messages from queue to WebSocket."""
        while self.running:
            try:
                # Get message from thread-safe queue (non-blocking)
                try:
                    msg = self.command_queue.get_nowait()
                except queue.Empty:
                    # No messages - yield to event loop
                    await asyncio.sleep(0.001)  # 1ms
                    continue

                # Send message (returns when buffered locally, NOT when ACKed)
                await ws.send(msg)
                self.messages_sent += 1

                # Mark queue task done
                self.command_queue.task_done()

                # Check for backpressure (monitoring only, no functional changes)
                buffer_size = self._get_write_buffer_size(ws)

                # Log when crossing threshold in either direction
                if buffer_size > self.backpressure_threshold and not self.backpressure_active:
                    # Rising edge - entering backpressure
                    self.backpressure_active = True
                    self.backpressure_events += 1
                    logging.warning(
                        f"WebSocket backpressure START: {buffer_size} bytes buffered, "
                        f"queue={self.get_queue_depth()}, threshold={self.backpressure_threshold}"
                    )
                elif buffer_size <= self.backpressure_threshold and self.backpressure_active:
                    # Falling edge - exiting backpressure
                    self.backpressure_active = False
                    logging.info(
                        f"WebSocket backpressure CLEAR: {buffer_size} bytes buffered, "
                        f"queue={self.get_queue_depth()}"
                    )

                # Periodically log stats
                if self.messages_sent % 1000 == 0:
                    stats = self.get_stats()
                    stats['write_buffer_bytes'] = buffer_size
                    logging.debug(f"WebSocket stats: {stats}")

            except websockets.exceptions.ConnectionClosed as e:
                logging.warning(f"WebSocket connection closed: {e}")
                break  # Exit to reconnect
            except Exception as e:
                logging.error(f"Error sending message '{msg[:50]}...': {e}")
                # Continue processing other messages

    async def _receive_messages(self, ws):
        """Receive messages from WebSocket and queue them for main thread."""
        try:
            async for message in ws:

                # We must respond to pings and data_ready immediately
                # Otherwise, other websocket clients break
                if message == "ping":
                    await ws.send("pong")
                    continue
                elif message.startswith("data_ready "):
                    await ws.send(message)
                    continue

                self.received_queue.put(message)
                self.messages_received += 1
                if should_log_message(message):
                    logging.debug(f"Received message from server: {message[:100]}")
        except websockets.exceptions.ConnectionClosed:
            logging.debug("WebSocket receive loop closed")
        except Exception as e:
            logging.error(f"Error receiving message: {e}")

    def _get_write_buffer_size(self, ws) -> int:
        """
        Get the WebSocket's TCP write buffer size.

        Returns the number of bytes waiting to be sent on the socket.
        This is the real backpressure indicator - if this grows large,
        we're sending faster than mod-ui can process.

        Args:
            ws: WebSocket connection

        Returns:
            Number of bytes in write buffer, or 0 if unavailable
        """
        try:
            if hasattr(ws, 'transport') and ws.transport:
                return ws.transport.get_write_buffer_size()
            return 0
        except Exception:
            return 0
