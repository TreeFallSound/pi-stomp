"""
Shims for Raspberry Pi / CircuitPython hardware modules unavailable on macOS/Windows.
Injected into sys.modules at import time so application code can be imported in tests.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Run pygame headlessly in tests so the emulator suite doesn't pop a window.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

# Initialize pygame headlessly before any uilib import so SDL is ready.
from uilib.pygame_init import init as _pg_init
_pg_init()
import pygame

from uilib.panel import LcdBase

PROJECT_ROOT = Path(__file__).parent.parent
_TESTS_DIR = Path(__file__).parent
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
    parser.addoption(
        "--snapshot-update", action="store_true", default=False, help="Overwrite stored snapshots with current output"
    )


@pytest.fixture
def snapshot_update(request):
    return request.config.getoption("--snapshot-update")


def _surface_to_rgb_bytes(surface) -> tuple[bytes, tuple[int, int]]:
    # v3 LCDs render to pygame Surfaces; v1/v2 hardware renders to PIL Images.
    if isinstance(surface, pygame.Surface):
        return pygame.image.tobytes(surface, "RGB"), surface.get_size()
    rgb = surface.convert("RGB")
    return rgb.tobytes(), rgb.size


def assert_snapshot(surface: pygame.Surface, name: str, *, update: bool = False):
    path = _SNAPSHOT_DIR / f"{name}.png"
    rgb_bytes, size = _surface_to_rgb_bytes(surface)
    if update or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # Use pygame to write the PNG so reads and writes share the same encoder.
        rgb_surface = pygame.image.frombytes(rgb_bytes, size, "RGB")
        pygame.image.save(rgb_surface, str(path))
        return
    expected_surface = pygame.image.load(str(path)).convert(24)
    expected_bytes = pygame.image.tobytes(expected_surface, "RGB")
    assert rgb_bytes == expected_bytes, (
        f"Snapshot mismatch: {name}  (re-run with --snapshot-update to accept)"
    )


@pytest.fixture
def snapshot(request, fake_lcd, snapshot_update):
    """Assert the latest LCD frame matches a stored PNG snapshot.

    Path is auto-derived from the test file and function name.
    """
    counter = [0]
    rel = Path(request.fspath).relative_to(_TESTS_DIR)
    module = str(rel.with_suffix(""))
    test = request.node.name

    def _assert(suffix=None):
        if suffix is None:
            suffix = str(counter[0])
            counter[0] += 1
        assert_snapshot(fake_lcd.frames[-1], f"{module}/{test}/{suffix}", update=snapshot_update)

    return _assert


# ---------------------------------------------------------------------------
# FakeWebSocketBridge — captures outbound messages, injects inbound
# ---------------------------------------------------------------------------


class FakeWebSocketBridge:
    def __init__(self):
        self.sent: list[str] = []
        self._inbox: list[str] = []

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def send_parameter(self, instance_id: str, symbol: str, value: float) -> bool:
        self.sent.append(f"param_set /graph/{instance_id}/{symbol} {value}")
        return True

    def send_bpm(self, bpm: float) -> bool:
        self.sent.append(f"transport-bpm {bpm}")
        return True

    def clear_queue(self) -> int:
        return 0

    def get_received_messages(self) -> list[str]:
        msgs, self._inbox = self._inbox, []
        return msgs

    def inject(self, raw: str) -> None:
        self._inbox.append(raw)

    def sent_values_for(self, instance_id: str, symbol: str) -> list[float]:
        prefix = f"param_set /graph/{instance_id}/{symbol} "
        return [float(m[len(prefix):]) for m in self.sent if m.startswith(prefix)]


@pytest.fixture
def fake_ws_bridge():
    return FakeWebSocketBridge()


# ---------------------------------------------------------------------------
# FakeLcd — captures rendered frames without touching hardware
# ---------------------------------------------------------------------------


class FakeLcd(LcdBase):
    def __init__(self):
        self.frames: list[pygame.Surface] = []

    def dimensions(self):
        return (320, 240)

    def default_format(self):
        return "RGB"

    def clear(self):
        pass

    def update(self, surface: pygame.Surface, box=None):
        # Always capture a 24-bit RGB snapshot so per-frame format never drifts.
        size = surface.get_size()
        rgb_bytes = pygame.image.tobytes(surface, "RGB")
        snap = pygame.image.frombytes(rgb_bytes, size, "RGB")
        self.frames.append(snap)

    def update_bypass(self, enabled: bool, latched: bool):
        pass


@pytest.fixture
def fake_lcd():
    return FakeLcd()


# ---------------------------------------------------------------------------
# Shared factory fixtures (available to all test directories)
# ---------------------------------------------------------------------------


@pytest.fixture
def make_plugin():
    from modalapi.plugin import Plugin
    from modalapi.parameter import Parameter

    def _make(instance_id, category="Distortion", bypassed=False, has_footswitch=False, parameters=None):
        if parameters is None:
            parameters = {}
        bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
        bypass_param = Parameter(bypass_info, bypassed, None, instance_id)
        parameters[":bypass"] = bypass_param
        p = Plugin(instance_id, parameters, {}, category)
        p.has_footswitch = has_footswitch
        return p

    return _make


@pytest.fixture
def make_parameter():
    from modalapi.parameter import Parameter

    def _make(name, instance_id, value=0.5, minimum=0.0, maximum=1.0):
        info = {"shortName": name, "symbol": name.lower(), "ranges": {"minimum": minimum, "maximum": maximum}}
        return Parameter(info, value, None, instance_id)

    return _make


@pytest.fixture
def get_urls():
    """Return a helper that extracts called URLs from a mock's call history."""

    def _get(mock_obj):
        return [call.args[0] for call in mock_obj.call_args_list]

    return _get
