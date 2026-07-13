"""v2-specific fixtures — delegates stack construction to integration/conftest."""
from collections.abc import Generator

import pytest

from tests.integration.conftest import _v2_stack
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_step


@pytest.fixture
def v2_system(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    yield from _v2_stack(fake_lcd, tmp_path)


@pytest.fixture
def nav_handler(v2_system):
    """nav_handler(d) — step the NAV selector by ``d`` detents, then poll.

    v2 hardware has no Tweak encoders at all, so NAV is the only input;
    mirrors tests/v3/conftest.py's fixture of the same name."""
    handler = v2_system.handler

    def _nav(d: int) -> None:
        nav_step(handler, d)
        handler.poll_lcd_updates()

    return _nav
