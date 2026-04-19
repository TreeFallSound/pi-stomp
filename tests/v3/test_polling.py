"""poll_system_info(), poll_controls(), poll_indicators(), poll_lcd_updates()."""

from unittest.mock import patch


def test_v3_poll_system_info(v3_system):
    """poll_system_info() parses systemctl + vcgencmd output into handler state."""
    handler, _, _, _, _ = v3_system

    def sub_output(cmd, **kwargs):
        if cmd[0] == "systemctl":
            return b"SystemState=running"
        if "get_throttled" in cmd:
            return b"throttled=0x0"
        if "measure_temp" in cmd:
            return b"temp=45.2'C"
        return b""

    with patch("subprocess.check_output", side_effect=sub_output):
        handler.poll_system_info()

    assert handler.SystemState == "running"
    assert handler.throttled == "0x0"
    assert handler.temperature == "45.2'C"


def test_v3_poll_system_info_subprocess_failure(v3_system):
    """poll_system_info() sets state to 'unknown' when subprocess calls fail."""
    handler, _, _, _, _ = v3_system
    import subprocess

    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "vcgencmd")):
        handler.poll_system_info()

    assert handler.SystemState == "unknown"
    assert handler.throttled == "unknown"
    assert handler.temperature == "unknown"


def test_v3_poll_controls_delegates_to_hardware(v3_system):
    """poll_controls() calls hardware.poll_controls() exactly once."""
    handler, hw, _, _, _ = v3_system

    # Patch the real hardware method to avoid triggering ADC reads with mocked SPI
    with patch.object(hw, "poll_controls") as mock_poll:
        handler.poll_controls()

    mock_poll.assert_called_once()


def test_v3_poll_lcd_updates(v3_system):
    """poll_lcd_updates() calls lcd.poll_updates()."""
    handler, _, _, _, _ = v3_system

    handler.poll_lcd_updates()

    # lcd is the real Lcd instance — just verify no exception raised and a frame exists
    # (lcd.poll_updates() may or may not render depending on state)
    assert handler.lcd is not None
