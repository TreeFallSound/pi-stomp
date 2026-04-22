"""v2-specific system menu behaviour."""

from unittest.mock import MagicMock, patch

from tests.types import SystemFixture


def test_system_info_load(v2_system: SystemFixture):
    """On v2 (relay present), system_info_load reads bypass from the relay, not the audiocard."""
    handler, hw, _, _, _ = v2_system
    hw.relay = MagicMock()
    hw.relay.get.return_value = False  # relay not engaged → bypass enabled
    handler.audiocard.get_switch_parameter.return_value = True

    with patch("subprocess.check_output", return_value=b"v1.0.0-abc\n"):
        handler.system_info_load()

    assert handler.software_version == "v1.0.0-abc\n"
    assert handler.eq_status is True
    hw.relay.get.assert_called_once()
    handler.audiocard.get_bypass_left.assert_not_called()
    handler.audiocard.get_bypass_right.assert_not_called()
