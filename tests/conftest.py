"""
Shims for Raspberry Pi / CircuitPython hardware modules unavailable on macOS/Windows.
Injected into sys.modules at import time so application code can be imported in tests.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent

_PI_MODULES = [
    "alsaaudio",
    "board",
    "busio",
    "digitalio",
    "gfxhat",
    "gfxhat.backlight",
    "gfxhat.fonts",
    "gfxhat.lcd",
    "gfxhat.touch",
    "gpiozero",
    "neopixel",
    "spidev",
    "lilv",
    "matplotlib",
    "adafruit_mcp3xxx",
    "adafruit_mcp3xxx.analog_in",
    "adafruit_mcp3xxx.mcp3008",
    "adafruit_rgb_display",
    "adafruit_rgb_display.ili9341",
    "adafruit_rgb_display.st7789",
    "adafruit_ssd1306",
]

for _mod in _PI_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

_SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def pytest_addoption(parser):
    parser.addoption("--snapshot-update", action="store_true", default=False,
                     help="Overwrite stored snapshots with current output")


@pytest.fixture
def snapshot_update(request):
    return request.config.getoption("--snapshot-update")


def assert_snapshot(image: Image.Image, name: str, *, update: bool = False):
    path = _SNAPSHOT_DIR / f"{name}.png"
    rgb = image.convert("RGB")
    if update or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(path)
        return
    expected = Image.open(path).convert("RGB")
    assert rgb.tobytes() == expected.tobytes(), (
        f"Snapshot mismatch: {name}  (re-run with --snapshot-update to accept)"
    )


# ---------------------------------------------------------------------------
# FakeLcd — captures rendered frames without touching hardware
# ---------------------------------------------------------------------------

class FakeLcd:
    def __init__(self):
        self.frames: list[Image.Image] = []

    def dimensions(self):
        return (320, 240)

    def default_format(self):
        return "RGB"

    def clear(self):
        pass

    def update(self, image: Image.Image, box=None):
        self.frames.append(image.copy())


@pytest.fixture
def fake_lcd():
    return FakeLcd()
