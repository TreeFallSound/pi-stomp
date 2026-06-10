from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from PIL import Image
    from modalapi.mod import Mod  # noqa: F401  (forward ref in SystemFixtureLegacy)
    from modalapi.modhandler import Modhandler  # noqa: F401  (forward ref in SystemFixture)
    from pistomp.handler import Handler
    from pistomp.hardware import Hardware
    from tests.conftest import FakeWebSocketBridge

HandlerT = TypeVar("HandlerT", bound="Handler")


class CapturedLcd(Protocol):
    """Test-double LCDs that record rendered frames (FakeLcd, FakeMonoLcd)."""

    frames: list[Image.Image]


@dataclass
class SystemFixtureBase(Generic[HandlerT]):
    handler: HandlerT
    hw: Hardware
    lcd: CapturedLcd
    mock_get: MagicMock
    mock_post: MagicMock
    ws_bridge: FakeWebSocketBridge


class SystemFixture(SystemFixtureBase["Modhandler"]):
    """v2/v3 stack (Modhandler)."""


class SystemFixtureLegacy(SystemFixtureBase["Mod"]):
    """v1 stack (Mod)."""
