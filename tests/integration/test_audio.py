# pyright: reportAttributeAccessIssue=false
"""Bypass (relay + audiocard), EQ toggle, audio parameter commit and VU recalibration."""

from unittest.mock import MagicMock, patch

import common.token as Token
from tests.types import SystemFixture


def test_system_toggle_bypass_relay(modhandler_system: SystemFixture):
    """With a relay, toggle_bypass calls relay.update() and skips audiocard."""
    handler = modhandler_system.handler
    hw = modhandler_system.hw
    hw.relay = MagicMock()
    hw.relay.get.return_value = False

    handler.system_toggle_bypass()

    hw.relay.update.assert_called_once_with(True)
    handler.audiocard.set_bypass_left.assert_not_called()


def test_change_bypass_preference(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    handler.change_bypass_preference(Token.LEFT)
    handler.settings.set_setting.assert_called_with(Token.BYPASS, Token.LEFT)


def test_system_toggle_eq_on(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    handler.eq_status = False
    handler.system_toggle_eq(None)
    handler.audiocard.set_switch_parameter.assert_called_once_with(handler.audiocard.DAC_EQ, True)
    assert handler.eq_status is True


def test_system_toggle_eq_off(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    handler.eq_status = True
    handler.system_toggle_eq(None)
    handler.audiocard.set_switch_parameter.assert_called_once_with(handler.audiocard.DAC_EQ, False)
    assert handler.eq_status is False


def test_audio_parameter_commit(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    hw = modhandler_system.hw
    with patch.object(hw, "recalibrateVU_gain") as mock_cal:
        handler.audio_parameter_commit(handler.audiocard.MASTER, -6.0)
    handler.audiocard.set_volume_parameter.assert_called_once_with(handler.audiocard.MASTER, -6.0)
    mock_cal.assert_not_called()


def test_audio_parameter_commit_recalibrates_vu(modhandler_system: SystemFixture):
    """CAPTURE_VOLUME changes also trigger VU recalibration."""
    handler = modhandler_system.handler
    hw = modhandler_system.hw
    with patch.object(hw, "recalibrateVU_gain") as mock_cal:
        handler.audio_parameter_commit(handler.audiocard.CAPTURE_VOLUME, 3.0)
    handler.audiocard.set_volume_parameter.assert_called_once_with(handler.audiocard.CAPTURE_VOLUME, 3.0)
    mock_cal.assert_called_once_with(3.0)
