#!/usr/bin/env python3

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

import os
import socket
import sys
import time
import subprocess
import datetime
import threading
import signal
import argparse
import struct
import zlib

SOCKET_PATH = "/tmp/pistomp-lcd.sock"
WIDTH = 320
HEIGHT = 240
BPP = 4
FRAME_SIZE = WIDTH * HEIGHT * BPP
FPS = 60
STILL_TIMEOUT_S = 30.0


def bind_capture_socket(socket_path: str = SOCKET_PATH) -> socket.socket:
    if os.path.exists(socket_path):
        os.remove(socket_path)
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(socket_path)
    os.chmod(socket_path, 0o666)
    return server_sock


def unlink_socket(socket_path: str) -> None:
    if os.path.exists(socket_path):
        os.remove(socket_path)


def recv_frame(conn: socket.socket) -> bytes:
    data = b""
    while len(data) < FRAME_SIZE:
        chunk = conn.recv(FRAME_SIZE - len(data))
        if not chunk:
            raise RuntimeError(f"connection closed after {len(data)}/{FRAME_SIZE} bytes")
        data += chunk
    return data


_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(bgra: bytes, path: str) -> None:
    if len(bgra) != FRAME_SIZE:
        raise ValueError(f"expected {FRAME_SIZE} bytes, got {len(bgra)}")
    mv = memoryview(bgra)
    rgb = bytearray(WIDTH * HEIGHT * 3)
    rgb[0::3] = mv[2::4]
    rgb[1::3] = mv[1::4]
    rgb[2::3] = mv[0::4]
    stride = WIDTH * 3
    raw = b"".join(b"\x00" + rgb[y * stride : (y + 1) * stride] for y in range(HEIGHT))
    with open(path, "wb") as f:
        f.write(_PNG_SIG)
        f.write(_png_chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)))
        f.write(_png_chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(_png_chunk(b"IEND", b""))


def capture_still(output_path: str, *, socket_path: str = SOCKET_PATH, timeout: float = STILL_TIMEOUT_S) -> None:
    """Listen for one LCD frame and write it as a PNG.

    pi-stomp (device or emulator) connects to ``socket_path`` within a couple of
    seconds of the socket appearing, then sends a full-screen BGRA frame.
    """
    server_sock = bind_capture_socket(socket_path)
    server_sock.listen(1)
    server_sock.settimeout(timeout)
    print(f"Waiting for pi-stomp to connect to {socket_path}...")
    try:
        conn, _ = server_sock.accept()
        with conn:
            conn.settimeout(timeout)
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            print("Connected to pi-stomp")
            frame = recv_frame(conn)
        write_png(frame, output_path)
        print(f"Wrote {output_path}")
    except TimeoutError as e:
        raise TimeoutError(f"Timed out waiting for pi-stomp at {socket_path}") from e
    finally:
        server_sock.close()
        unlink_socket(socket_path)


class LcdRecorder:
    def __init__(self, output_path, lossless=False):
        self.output_path = output_path
        self.running = True
        self.current_frame = bytes(FRAME_SIZE)  # Black frame initially
        self.frame_received = threading.Event()

        # ffmpeg command
        self.ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgra",
            "-video_size",
            f"{WIDTH}x{HEIGHT}",
            "-framerate",
            str(FPS),
            "-i",
            "pipe:",
            "-c:v",
            "libx264",
        ]

        if lossless:
            # Lossless H.264
            self.ffmpeg_cmd.extend(["-preset", "ultrafast", "-qp", "0"])
        else:
            # High quality but compressed
            self.ffmpeg_cmd.extend(["-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"])

        self.ffmpeg_cmd.append(f"file:{self.output_path}")

    def stop(self, signum=None, frame=None):
        print("\nStopping recording...")
        self.running = False

    def socket_listener(self, server_sock):
        print(f"Waiting for pi-stomp to connect to {SOCKET_PATH}...")
        server_sock.listen(1)
        try:
            conn, _ = server_sock.accept()
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            print("Connected to pi-stomp!")
            with conn:
                while self.running:
                    data = b""
                    while len(data) < FRAME_SIZE and self.running:
                        chunk = conn.recv(FRAME_SIZE - len(data))
                        if not chunk:
                            print("Connection closed by pi-stomp")
                            self.running = False
                            break
                        data += chunk

                    if len(data) == FRAME_SIZE:
                        self.current_frame = data
                        self.frame_received.set()
        except Exception as e:
            if self.running:
                print(f"Socket error: {e}")
            self.running = False

    def run(self):
        server_sock = bind_capture_socket(SOCKET_PATH)

        # Handle signals
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        # Start socket thread
        listener_thread = threading.Thread(target=self.socket_listener, args=(server_sock,), daemon=True)
        listener_thread.start()

        # Start ffmpeg
        try:
            process = subprocess.Popen(self.ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print("Error: ffmpeg not found. Please install ffmpeg.")
            server_sock.close()
            unlink_socket(SOCKET_PATH)
            return

        print(f"Recording to {self.output_path}")
        print("Press Ctrl+C to stop.")

        # Wait for the first frame before starting the clock
        while self.running and not self.frame_received.is_set():
            self.frame_received.wait(0.1)

        if not self.running:
            return

        interval = 1.0 / FPS
        next_tick = time.time() + interval

        try:
            while self.running:
                # Write current frame (either new or repeated)
                try:
                    assert process.stdin is not None
                    process.stdin.write(self.current_frame)
                except BrokenPipeError:
                    print("ffmpeg process closed unexpectedly")
                    break

                # Sleep until next tick
                now = time.time()
                sleep_time = next_tick - now
                if sleep_time > 0:
                    time.sleep(sleep_time)

                next_tick += interval
                # If we're falling behind, catch up
                if next_tick < time.time():
                    next_tick = time.time() + interval

        finally:
            self.running = False
            if process.stdin:
                process.stdin.close()
            process.wait()
            server_sock.close()
            unlink_socket(SOCKET_PATH)
            print(f"Recording saved to {self.output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture the live pi-stomp LCD (video, or a still PNG).")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("-l", "--lossless", action="store_true", help="Record in lossless mode (higher disk usage)")
    parser.add_argument("-s", "--still", action="store_true", help="Capture a single PNG and exit")
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=STILL_TIMEOUT_S,
        help=f"Seconds to wait for pi-stomp in --still mode (default {STILL_TIMEOUT_S:g})",
    )
    args = parser.parse_args()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    home = os.path.expanduser("~")
    if args.output:
        output_file = args.output
    else:
        ext = "png" if args.still else "mp4"
        output_file = os.path.join(home, f"pistomp_capture_{timestamp}.{ext}")

    if args.still:
        try:
            capture_still(output_file, timeout=args.timeout)
        except TimeoutError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
    else:
        recorder = LcdRecorder(output_file, lossless=args.lossless)
        recorder.run()
