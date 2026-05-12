"""v3-specific polling: poll_controls() requires patching the real Pistomptre hardware."""

from unittest.mock import patch

from tests.types import SystemFixture


def test_v3_poll_controls_delegates_to_hardware(v3_system: SystemFixture):
    """poll_controls() calls hardware.poll_controls() exactly once."""
    handler = v3_system.handler
    hw = v3_system.hw

    with patch.object(hw, "poll_controls") as mock_poll:
        handler.poll_controls()

    mock_poll.assert_called_once()
