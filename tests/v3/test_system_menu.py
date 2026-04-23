"""v3-specific system menu behaviour."""

from unittest.mock import patch

from tests.types import SystemFixture


def test_system_info_load(v3_system: SystemFixture):
    """On v3 (no relay), system_info_load reads bypass state from the audiocard."""
    handler = v3_system.handler
    handler.audiocard.get_switch_parameter.return_value = True
    handler.audiocard.get_bypass_left.return_value = False
    handler.audiocard.get_bypass_right.return_value = True

    with patch("subprocess.check_output", return_value=b"v1.0.0-abc\n"):
        handler.system_info_load()

    assert handler.software_version == "v1.0.0-abc\n"
    assert handler.eq_status is True
    assert handler.bypass_left is False
    assert handler.bypass_right is True
