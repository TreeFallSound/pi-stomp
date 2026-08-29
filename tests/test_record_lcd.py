"""LCD still-capture: BGRA → PNG, and the unix-socket handshake."""

import importlib.util
import os
import socket
import threading
import time
import uuid
from pathlib import Path

import pytest
from PIL import Image

_SPEC = importlib.util.spec_from_file_location(
    "record_lcd", Path(__file__).resolve().parent.parent / "util" / "record_lcd.py"
)
assert _SPEC is not None and _SPEC.loader is not None
record_lcd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(record_lcd)

W, H = record_lcd.WIDTH, record_lcd.HEIGHT
RED_BGRA = bytes((0, 0, 255, 255)) * (W * H)


def _short_sock() -> str:
    # AF_UNIX sun_path is 104 bytes on macOS; pytest tmp_path overruns it.
    return f"/tmp/pistomp-lcd-test-{uuid.uuid4().hex}.sock"


def test_write_png_decodes_bgra_red(tmp_path):
    path = tmp_path / "red.png"
    record_lcd.write_png(RED_BGRA, str(path))
    img = Image.open(path)
    assert img.size == (W, H)
    assert img.getpixel((0, 0)) == (255, 0, 0)
    assert img.getpixel((W - 1, H - 1)) == (255, 0, 0)


def test_write_png_rejects_short_buffer(tmp_path):
    with pytest.raises(ValueError, match="expected"):
        record_lcd.write_png(b"\x00\x01\x02", str(tmp_path / "x.png"))


def _connect_when_ready(path: str, timeout: float = 2.0) -> socket.socket:
    deadline = time.time() + timeout
    last_err: OSError | None = None
    while time.time() < deadline:
        if os.path.exists(path):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(path)
                return sock
            except OSError as e:
                last_err = e
        time.sleep(0.01)
    raise TimeoutError(last_err)


def test_capture_still_writes_one_frame(tmp_path):
    sock_path = _short_sock()
    out = str(tmp_path / "lcd.png")
    errors: list[BaseException] = []

    def _run():
        try:
            record_lcd.capture_still(out, socket_path=sock_path, timeout=5.0)
        except BaseException as e:
            errors.append(e)

    t = threading.Thread(target=_run)
    t.start()
    try:
        client = _connect_when_ready(sock_path)
        try:
            client.sendall(RED_BGRA)
        finally:
            client.close()
        t.join(timeout=5)
        assert not t.is_alive()
        assert errors == []
        img = Image.open(out)
        assert img.getpixel((10, 10)) == (255, 0, 0)
    finally:
        t.join(timeout=1)
        if os.path.exists(sock_path):
            os.remove(sock_path)


def test_capture_still_times_out(tmp_path):
    sock_path = _short_sock()
    try:
        with pytest.raises(TimeoutError, match="Timed out"):
            record_lcd.capture_still(str(tmp_path / "lcd.png"), socket_path=sock_path, timeout=0.15)
        assert not os.path.exists(sock_path)
    finally:
        if os.path.exists(sock_path):
            os.remove(sock_path)
