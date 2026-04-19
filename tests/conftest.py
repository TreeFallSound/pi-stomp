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
_TESTS_DIR   = Path(__file__).parent
_SNAPSHOT_DIR = _TESTS_DIR / "snapshots"

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


@pytest.fixture
def snapshot(request, fake_lcd, snapshot_update):
    """Assert the latest LCD frame matches a stored PNG snapshot.

    Path is auto-derived from the test file and function name so no manual
    string is needed.  Call snapshot() for an auto-numbered frame or
    snapshot("label") for a named one.  Re-use the same label to assert the
    screen returned to an earlier state.
    """
    counter = [0]
    rel    = Path(request.fspath).relative_to(_TESTS_DIR)
    module = str(rel.with_suffix(""))   # e.g. "v3/test_startup"
    test   = request.node.name

    def _assert(suffix=None):
        if suffix is None:
            suffix = str(counter[0])
            counter[0] += 1
        assert_snapshot(fake_lcd.frames[-1], f"{module}/{test}/{suffix}",
                        update=snapshot_update)

    return _assert


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
