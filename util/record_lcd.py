#!/usr/bin/env python3
import os
import socket
import time
import subprocess
import datetime
import threading
import signal
import argparse

SOCKET_PATH = "/tmp/pistomp-lcd.sock"
WIDTH = 320
HEIGHT = 240
BPP = 4
FRAME_SIZE = WIDTH * HEIGHT * BPP
FPS = 60


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
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)

        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)  # Ensure pi-stomp can connect

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
            os.remove(SOCKET_PATH)
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
            if os.path.exists(SOCKET_PATH):
                os.remove(SOCKET_PATH)
            print(f"Recording saved to {self.output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record pi-stomp LCD to a video file.")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("-l", "--lossless", action="store_true", help="Record in lossless mode (higher disk usage)")
    args = parser.parse_args()

    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        home = os.path.expanduser("~")
        output_file = os.path.join(home, f"pistomp_capture_{timestamp}.mp4")

    recorder = LcdRecorder(output_file, lossless=args.lossless)
    recorder.run()
