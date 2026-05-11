"""v3-specific audio behaviour (audiocard bypass)."""

from tests.types import SystemFixture


def test_system_toggle_bypass_audiocard(v3_system: SystemFixture):
    """Without a relay, toggle_bypass flips both L/R audiocard channels."""
    handler = v3_system.handler
    hw = v3_system.hw
    assert hw.relay is None
    handler.settings.get_setting.return_value = None  # pyright: ignore[reportAttributeAccessIssue]
    handler.bypass_left = False
    handler.bypass_right = False

    handler.system_toggle_bypass()

    handler.audiocard.set_bypass_left.assert_called_once_with(True)
    handler.audiocard.set_bypass_right.assert_called_once_with(True)
    assert handler.bypass_left is True
    assert handler.bypass_right is True
