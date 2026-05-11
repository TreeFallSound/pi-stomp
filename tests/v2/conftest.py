"""v2-specific fixtures — delegates stack construction to integration/conftest."""
from collections.abc import Generator

import pytest

from tests.integration.conftest import _v2_stack
from tests.types import SystemFixture


@pytest.fixture
def v2_system(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    yield from _v2_stack(fake_lcd, tmp_path)
