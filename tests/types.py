from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from modalapi.modhandler import Modhandler
    from pistomp.hardware import Hardware
    from tests.conftest import FakeLcd


class SystemFixture(NamedTuple):
    handler:   Modhandler
    hw:        Hardware
    lcd:       FakeLcd
    mock_get:  MagicMock
    mock_post: MagicMock
