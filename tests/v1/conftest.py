"""v1-specific fixtures — delegates stack construction to integration/conftest.

v1 uses the monochrome lcdgfx LCD, so it provides its own ``snapshot`` fixture
backed by the captured FakeMonoLcd frames rather than the color ``fake_lcd``.
"""
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.conftest import assert_snapshot, _TESTS_DIR
from tests.integration.conftest import _v1_stack
from tests.types import SystemFixtureLegacy


@pytest.fixture
def v1_system(tmp_path) -> Generator[SystemFixtureLegacy, None, None]:
    yield from _v1_stack(tmp_path)


@pytest.fixture
def snapshot(request, v1_system, snapshot_update):
    """Assert the latest mono LCD frame matches a stored PNG snapshot.

    Mirrors the root color snapshot fixture but reads from the v1 system's
    captured FakeMonoLcd frames."""
    counter = [0]
    rel = Path(request.fspath).relative_to(_TESTS_DIR)
    module = str(rel.with_suffix(""))
    test = request.node.name

    def _assert(suffix=None):
        if suffix is None:
            suffix = str(counter[0])
            counter[0] += 1
        assert_snapshot(v1_system.lcd.frames[-1], f"{module}/{test}/{suffix}", update=snapshot_update)

    return _assert
