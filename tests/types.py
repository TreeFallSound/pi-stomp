from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from modalapi.modhandler import Modhandler
    from pistomp.hardware import Hardware
    from tests.conftest import FakeLcd, FakeWebSocketBridge


@dataclass
class SystemFixture:
    handler:   Modhandler
    hw:        Hardware
    lcd:       FakeLcd
    mock_get:  MagicMock
    mock_post: MagicMock
    ws_bridge: FakeWebSocketBridge
