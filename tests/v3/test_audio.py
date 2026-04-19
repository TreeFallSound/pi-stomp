"""Bypass (relay + audiocard), EQ toggle, audio parameter commit and VU recalibration."""

from unittest.mock import MagicMock, patch

import common.token as Token


def test_v3_system_toggle_bypass_audiocard(v3_system):
    """Without a relay, toggle_bypass flips both L/R audiocard channels."""
    handler, hw, _, _, _ = v3_system
    assert hw.relay is None
    handler.settings.get_setting.return_value = None  # no preference → both sides
    handler.bypass_left  = False
    handler.bypass_right = False

    handler.system_toggle_bypass()

    handler.audiocard.set_bypass_left.assert_called_once_with(True)
    handler.audiocard.set_bypass_right.assert_called_once_with(True)
    assert handler.bypass_left  is True
    assert handler.bypass_right is True


def test_v3_system_toggle_bypass_relay(v3_system):
    """With a relay, toggle_bypass calls relay.update() and skips audiocard."""
    handler, hw, _, _, _ = v3_system
    hw.relay = MagicMock()
    hw.relay.get.return_value = False  # currently off → toggling enables it

    handler.system_toggle_bypass()

    hw.relay.update.assert_called_once_with(True)
    handler.audiocard.set_bypass_left.assert_not_called()


def test_v3_change_bypass_preference(v3_system):
    """change_bypass_preference() persists the preference to settings."""
    handler, _, _, _, _ = v3_system
    handler.change_bypass_preference(Token.LEFT)
    handler.settings.set_setting.assert_called_with(Token.BYPASS, Token.LEFT)


def test_v3_system_toggle_eq_on(v3_system):
    """system_toggle_eq() enables EQ when currently off."""
    handler, _, _, _, _ = v3_system
    handler.eq_status = False

    handler.system_toggle_eq(None)

    handler.audiocard.set_switch_parameter.assert_called_once_with(handler.audiocard.DAC_EQ, True)
    assert handler.eq_status is True


def test_v3_system_toggle_eq_off(v3_system):
    """system_toggle_eq() disables EQ when currently on."""
    handler, _, _, _, _ = v3_system
    handler.eq_status = True

    handler.system_toggle_eq(None)

    handler.audiocard.set_switch_parameter.assert_called_once_with(handler.audiocard.DAC_EQ, False)
    assert handler.eq_status is False


def test_v3_audio_parameter_commit(v3_system):
    """audio_parameter_commit() calls set_volume_parameter; does NOT recalibrate VU."""
    handler, hw, _, _, _ = v3_system

    with patch.object(hw, "recalibrateVU_gain") as mock_cal:
        handler.audio_parameter_commit(handler.audiocard.MASTER, -6.0)

    handler.audiocard.set_volume_parameter.assert_called_once_with(handler.audiocard.MASTER, -6.0)
    mock_cal.assert_not_called()


def test_v3_audio_parameter_commit_recalibrates_vu(v3_system):
    """audio_parameter_commit() with CAPTURE_VOLUME also triggers VU recalibration."""
    handler, hw, _, _, _ = v3_system

    with patch.object(hw, "recalibrateVU_gain") as mock_cal:
        handler.audio_parameter_commit(handler.audiocard.CAPTURE_VOLUME, 3.0)

    handler.audiocard.set_volume_parameter.assert_called_once_with(handler.audiocard.CAPTURE_VOLUME, 3.0)
    mock_cal.assert_called_once_with(3.0)
